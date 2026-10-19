"""Real server TTL expiry in an owned loopback API/worker pair; no mocked HTTP response."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:5178')
    parser.add_argument('--api-port', type=int, default=18420)
    parser.add_argument('--worker-port', type=int, default=18421)
    parser.add_argument('--browser-executable', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('work/case-real-expiry'))
    args = parser.parse_args()
    parsed = urlsplit(args.base)
    if parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise SystemExit('This fixture accepts only a local frontend; never change public service TTL.')
    args.output.mkdir(parents=True, exist_ok=True)
    api = f'http://127.0.0.1:{args.api_port}'
    worker = f'http://127.0.0.1:{args.worker_port}'
    processes, handles = [], []
    with tempfile.TemporaryDirectory(prefix='recheck-expiry-') as scratch:
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'backend'), DATABASE_URL=f'sqlite:///{scratch}/case.db',
                   MODEL_SERVICE_URL=worker, RECHECK_SESSION_TTL_SECONDS='2',
                   RECHECK_CORS_ORIGINS=f'{parsed.scheme}://{parsed.netloc}', RECHECK_MODEL_BUNDLE=str(ROOT / 'backend/model_artifacts'))
        try:
            for name, port in [('worker', args.worker_port), ('api', args.api_port)]:
                handle = (args.output / f'{name}.log').open('w')
                handles.append(handle)
                processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', f'recheck.{name}:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT))
            with httpx.Client(trust_env=False, timeout=2) as client:
                for _ in range(100):
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError('Owned local fixture failed to start; inspect logs')
                    try:
                        if client.get(api + '/health').status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError('Local fixture did not become healthy')
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=args.browser_executable, args=['--no-sandbox', '--disable-dev-shm-usage'])
                page = browser.new_page(viewport={'width':390,'height':844})
                page.set_default_timeout(15000)
                requests = []
                page.on('request', lambda r: requests.append(r.url) if r.url.startswith(api) else None)
                page.add_init_script('localStorage.setItem("recheck-api-base", ' + json.dumps(api) + ')')
                page.goto(args.base, wait_until='networkidle')
                page.get_by_test_id('case-next').click()
                page.wait_for_function("document.querySelector('[data-testid=case-study]').dataset.step === '1'")
                def download(name):
                    with page.expect_download() as item:
                        page.get_by_role('button', name='사건 기록 JSON', exact=True).click()
                    target = args.output / name
                    item.value.save_as(target)
                    return json.loads(target.read_text())
                before = download('before-expiry.json')
                page.wait_for_timeout(2200)
                with page.expect_response('**/evidence/events') as response:
                    page.get_by_test_id('case-next').click()
                assert response.value.status == 404
                assert response.value.json()['detail'] == 'session_missing_or_expired'
                page.get_by_role('alert').filter(has_text='세션 만료').wait_for()
                expired = download('expired.json')
                assert expired['snapshot']['sessionExpired']
                assert before['session_id'] == expired['session_id']
                assert before['events'] == expired['events']
                count = len(requests)
                page.get_by_role('button', name='세 방식 비교', exact=True).click()
                page.get_by_role('navigation', name='화면 선택').get_by_role('button', name='상담 기록').click()
                assert page.get_by_test_id('case-next').is_disabled()
                assert page.get_by_test_id('case-run-all').is_disabled()
                assert download('after-navigation.json') == expired
                navigation_requests = len(requests) - count
                assert navigation_requests == 0
                page.screenshot(path=str(args.output / 'real-expiry-mobile.png'), full_page=True)
                page.get_by_test_id('case-reset').click()
                page.get_by_test_id('case-next').click()
                page.wait_for_function("document.querySelector('[data-testid=case-study]').dataset.step === '1'")
                restarted = download('after-restart.json')
                assert restarted['session_id'] != before['session_id']
                assert not restarted['snapshot']['sessionExpired']
                report = {'scope':'real loopback server TTL expiry; SQLite; no route mocks or clock patch',
                          'ttl_seconds':2, 'response_status':response.value.status,
                          'old_session':before['session_id'], 'new_session':restarted['session_id'],
                          'historical_events_preserved':True, 'navigation_requests':navigation_requests,
                          'explicit_restart_verified':True}
                (args.output / 'real-expiry.json').write_text(json.dumps(report, indent=2)+'\n')
                print('PASS real server TTL expiry, historical evidence, zero navigation requests and explicit restart')
                browser.close()
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            for handle in handles:
                handle.close()


if __name__ == '__main__':
    main()
