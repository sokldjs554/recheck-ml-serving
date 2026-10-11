#!/usr/bin/env python3
"""Exercise the default guided case against an actual API, plus real HTTP failure and delayed reset."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:5175')
    parser.add_argument('--api', default='http://127.0.0.1:8013')
    parser.add_argument('--browser-executable', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('work/case-browser'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser_executable, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1050})
        page.set_default_timeout(15000)
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.goto(args.base, wait_until='networkidle')
        case = page.get_by_test_id('case-study')
        assert case.count() == 1, 'Guided case must be the default entry'
        def step(number):
            page.wait_for_function('(n) => document.querySelector("[data-testid=case-study]")?.dataset.step === String(n)', arg=number, timeout=110000)
        def next_step(number):
            page.get_by_test_id('case-next').click()
            step(number)
        def configure(base):
            details = page.locator('.case-connection-config')
            if not details.evaluate('(el) => el.open'):
                details.locator('summary').click()
            page.get_by_test_id('case-api-base').fill(base)
            page.get_by_role('button', name='주소 적용', exact=True).click()
            details.locator('summary').click()
        configure(args.api)
        page.screenshot(path=str(args.output / 'case-initial-desktop.png'), full_page=True)
        page.get_by_test_id('case-run-all').click()
        step(6)
        assert '300만 원' in page.get_by_test_id('case-old-draft').inner_text()
        assert '100만 원' in page.get_by_test_id('case-draft').inner_text()
        assert '실행 차단' in page.get_by_test_id('case-outcomes').inner_text()
        with page.expect_download() as automatic_download:
            page.get_by_role('button', name='사건 기록 JSON', exact=True).click()
        automatic_file = args.output / 'automatic-case.json'
        automatic_download.value.save_as(automatic_file)
        automatic_data = json.loads(automatic_file.read_text())
        automatic_actions = page.request.get(f"{args.api}/api/sessions/{automatic_data['session_id']}/evidence/actions").json()['actions']
        assert len(automatic_actions) == 1
        assert automatic_actions[0]['action_id'] == page.get_by_test_id('case-action').locator('code').inner_text()
        checks.append('one-click actual HTTP run preserves old/new answers and produces exactly one persisted task')
        page.get_by_test_id('case-reset').click()
        step(0)
        next_step(1)
        assert '300만 원' in page.get_by_test_id('case-source').inner_text()
        assert '300만 원' in page.get_by_test_id('case-draft').inner_text()
        next_step(2)
        assert '100만 원' in page.get_by_test_id('case-source').inner_text()
        assert '300만 원' in page.get_by_test_id('case-draft').inner_text()
        next_step(3)
        assert 'source_changed' in page.get_by_test_id('case-status').inner_text()
        page.screenshot(path=str(args.output / 'case-blocked-desktop.png'), full_page=True)
        next_step(4)
        assert '100만 원' in page.get_by_test_id('case-draft').inner_text()
        assert '유효기간' in page.locator('.case-expiry').inner_text()
        rejected_keys = []
        def malformed_success(route):
            rejected_keys.append(route.request.post_data_json['idempotency_key'])
            committed = route.fetch()
            assert committed.status == 200
            route.fulfill(response=committed, body='{}')
        page.route('**/evidence/receipts/*/execute', malformed_success)
        page.get_by_test_id('case-next').click()
        page.get_by_role('alert').filter(has_text='응답').wait_for()
        assert case.get_attribute('data-step') == '4'
        assert page.get_by_test_id('case-action').count() == 0
        page.unroute('**/evidence/receipts/*/execute', malformed_success)
        with page.expect_request('**/evidence/receipts/*/execute') as retried:
            next_step(5)
        assert retried.value.post_data_json['idempotency_key'] == rejected_keys[0]
        checks.append('lost commit response cannot claim success; retry retains original key and displays replay')
        assert '200 / replayed' in page.locator('.replay-gate-code').inner_text(), 'A lost commit response must display the actual replay result on retry'
        original_action = page.get_by_test_id('case-action').locator('code').inner_text()
        next_step(6)
        assert original_action == page.get_by_test_id('case-action').locator('code').inner_text()
        assert '과거' in page.get_by_test_id('case-status').inner_text()
        with page.expect_download() as download:
            page.get_by_role('button', name='사건 기록 JSON', exact=True).click()
        filename = args.output / download.value.suggested_filename
        download.value.save_as(filename)
        data = json.loads(filename.read_text())
        assert any(e['data'].get('detail') == 'source_changed' for e in data['events'] if isinstance(e['data'], dict))
        actions = page.request.get(f"{args.api}/api/sessions/{data['session_id']}/evidence/actions").json()['actions']
        assert len(actions) == 1 and actions[0]['action_id'] == original_action
        checks.append('actual HTTP: old answer blocked, fresh task recorded, replay returns one historical action, JSON contains actual responses')
        page.screenshot(path=str(args.output / 'case-complete-desktop.png'), full_page=True)
        for width, height in [(390, 844), (768, 1024), (844, 390)]:
            page.set_viewport_size({'width': width, 'height': height})
            assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth'), f'Horizontal overflow {width}x{height}'
            page.get_by_test_id('case-reset').focus()
            assert page.get_by_test_id('case-reset').evaluate('(el) => el.getBoundingClientRect().top >= 0')
            if width <= 760:
                page.keyboard.press('Tab')
                assert page.get_by_test_id('case-next').evaluate('(el) => document.activeElement === el'), 'Mobile focus must follow visible transport before old-answer details'
            page.screenshot(path=str(args.output / f'case-complete-{width}x{height}.png'), full_page=True)
        checks.append('390 portrait, 768 tablet, 844 landscape: no horizontal overflow and reset reachable')
        page.set_viewport_size({'width': 1440, 'height': 1050})
        page.get_by_test_id('case-reset').click()
        step(0)
        next_step(1)
        def fail_event(route):
            route.abort('connectionrefused')
        page.route('**/evidence/events', fail_event)
        page.get_by_test_id('case-next').click()
        page.get_by_role('alert').filter(has_text='요청 실패').wait_for()
        assert case.get_attribute('data-step') == '1', (case.get_attribute('data-step'), page.get_by_test_id('case-status').inner_text())
        assert '준비했습니다' not in page.get_by_test_id('case-status').inner_text()
        page.unroute('**/evidence/events', fail_event)
        next_step(2)
        checks.append('network failure clears success and same-step retry completes with actual HTTP')
        page.get_by_test_id('case-reset').click()
        held = []
        def hold_session(route):
            held.append(route)
        page.route('**/api/sessions', hold_session)
        page.get_by_test_id('case-next').click()
        deadline = time.monotonic() + 100
        while not held and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        assert held and page.get_by_test_id('case-next').is_disabled()
        assert page.get_by_test_id('case-api-base').is_disabled()
        page.get_by_test_id('case-reset').click()
        with page.expect_response('**/api/sessions') as late_response:
            held[0].continue_()
        assert late_response.value.json()["session_id"]
        page.unroute('**/api/sessions', hold_session)
        page.wait_for_timeout(150)
        assert case.get_attribute('data-step') == '0'
        assert page.get_by_test_id('case-events').count() == 0
        assert page.get_by_test_id('case-draft').locator('.case-answer-text').count() == 0
        checks.append('pending controls locked; late session completion after reset does not restore old state')
        assert not errors, errors
        (args.output / 'case-browser.json').write_text(json.dumps({'frontend': args.base, 'api': args.api, 'checks': checks, 'page_errors': errors}, ensure_ascii=False, indent=2) + '\n')
        for check in checks:
            print('PASS', check)
        browser.close()


if __name__ == '__main__':
    main()
