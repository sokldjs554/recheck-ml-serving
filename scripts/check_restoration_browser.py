"""Reload actual API evidence in Chromium or Playwright WebKit (not device Safari)."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--api', required=True)
    parser.add_argument('--engine', choices=['chromium', 'webkit'], default='chromium')
    parser.add_argument('--browser-executable')
    parser.add_argument('--output', type=Path, default=Path('work/restoration-browser'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks, errors, requests, failures = [], [], [], []
    key = 'recheck-case-checkpoint-v1'
    with sync_playwright() as p:
        options = {'executable_path': args.browser_executable} if args.browser_executable else {}
        browser = getattr(p, args.engine).launch(**options)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: requests.append((r.method, r.url)) if r.url.startswith(args.api.rstrip('/') + '/') else None)
        page.set_default_timeout(15000)
        def step(n):
            page.wait_for_function('(n) => document.querySelector("[data-testid=case-study]")?.dataset.step === String(n)', arg=n, timeout=110000)
        def snapshot():
            return page.evaluate('(key) => JSON.parse(sessionStorage.getItem(key))', key)
        def reset():
            page.get_by_test_id('case-reset').click()
            assert page.evaluate('(key) => sessionStorage.getItem(key)', key) is None
        def configure():
            details = page.locator('.case-connection-config')
            details.locator('summary').click()
            page.get_by_test_id('case-api-base').fill(args.api)
            page.get_by_role('button', name='주소 적용', exact=True).click()
            details.locator('summary').click()
        page.goto(args.base, wait_until='networkidle')
        configure()
        page.get_by_test_id('case-run-top').click(); step(6)
        before = snapshot(); count = len(requests)
        page.reload(wait_until='networkidle'); step(6)
        assert len(requests) == count, 'Reload must not send API requests'
        assert page.get_by_test_id('case-restored').is_visible()
        assert page.get_by_test_id('case-api-base').input_value() == args.api
        assert page.get_by_test_id('case-action').locator('code').inner_text() == before['snapshot']['action']['action_id']
        for field in ['session', 'events', 'oldReceipt', 'freshReceipt', 'action']:
            assert snapshot()['snapshot'][field] == before['snapshot'][field]
        page.get_by_role('navigation', name='실험 선택').get_by_role('link', name='모델 부하', exact=True).click()
        page.get_by_role('navigation', name='실험 선택').get_by_role('button', name='실행 재현', exact=True).click()
        assert len(requests) == count
        checks.append('completed reload and navigation preserve session, drafts, action and exact logs without API requests')
        # Decode media before injecting/aborting a real request. WebKit's media
        # loading must not inherit the deliberately interrupted route harness.
        page.set_viewport_size({'width': 320, 'height': 960})
        media_details = page.get_by_test_id('recorded-demo')
        media_details.locator('summary').click()
        video = page.locator('video')
        # WebKit applies visibility rules to muted playback. Record the initial
        # state, then bring the actual player into view as a person would.
        media_state = '(v) => ({source:v.currentSrc,ready:v.readyState,network:v.networkState,paused:v.paused,time:v.currentTime,width:v.videoWidth,error:v.error ? {code:v.error.code,message:v.error.message}:null,rect:{top:v.getBoundingClientRect().top,bottom:v.getBoundingClientRect().bottom},viewport:innerHeight,webm:v.canPlayType(\'video/webm; codecs="vp9"\'),mp4:v.canPlayType(\'video/mp4; codecs="avc1.640028"\')})'
        print('MEDIA_BEFORE ' + json.dumps(video.evaluate(media_state)), flush=True)
        video.scroll_into_view_if_needed()
        playback = video.evaluate("async (v) => { v.muted = true; return await Promise.race([v.play().then(() => 'playing').catch(e => e.name + ': ' + e.message), new Promise(r => setTimeout(() => r('pending'), 5000))]); }")
        print('MEDIA_PLAY ' + json.dumps({'engine':args.engine,'play':playback,'state':video.evaluate(media_state)}), flush=True)
        try:
            page.wait_for_function('document.querySelector("video").currentTime > .2 && document.querySelector("video").videoWidth === 1280', timeout=20000)
        except Exception as exc:
            state = video.evaluate(media_state)
            failures.append({'check': 'stored recording playback', 'error': str(exc), 'state': state})
            print("MEDIA_FAILURE " + json.dumps(state), flush=True)
            # A plain, fresh page separates the asset/engine from React and the
            # restoration flow. Diagnostic only: it cannot erase the UI failure.
            probe = browser.new_page(viewport={'width':320,'height':960})
            probe.set_content('<video controls muted playsinline style="width:280px"></video>')
            probe.locator('video').evaluate('(v, src) => { v.src = src; v.play().catch(() => {}); }', state['source'])
            try:
                probe.wait_for_function('document.querySelector("video").currentTime > .2 && document.querySelector("video").videoWidth === 1280', timeout=20000)
                probe_passed = True
            except Exception:
                probe_passed = False
            failures[-1]['plain_page_probe'] = {'passed':probe_passed,'state':probe.locator('video').evaluate(media_state)}
            print('MEDIA_PLAIN_PAGE ' + json.dumps(failures[-1]['plain_page_probe']), flush=True)
            probe.close()
        else:
            checks.append('stored real recording decodes in the selected engine and remains separate from restored API evidence')
        media = video.evaluate('(v) => ({source:v.currentSrc,width:v.videoWidth,height:v.videoHeight,duration:v.duration})')
        video.evaluate('(v) => v.pause()')
        media_details.locator('summary').click()
        page.set_viewport_size({'width': 1440, 'height': 1000})
        reset(); page.reload(wait_until='networkidle'); step(0)
        assert page.get_by_test_id('case-restored').count() == 0
        configure()
        checks.append('explicit reset clears the same-tab checkpoint across reload')
        # Stop after preparing the fresh answer, then let the server commit while
        # deliberately withholding its HTTP response from the browser.
        for n in range(1, 5):
            page.get_by_test_id('case-next').click(); step(n)
        pending = []
        def hold_committed_response(route):
            response = route.fetch()
            assert response.status == 200
            pending.append((route, response.json(), route.request.post_data_json))
        page.route('**/evidence/receipts/*/execute', hold_committed_response)
        page.get_by_test_id('case-next').click()
        page.wait_for_function('(key) => JSON.parse(sessionStorage.getItem(key)).snapshot.busy', arg=key)
        # Pump Playwright events until route.fetch has really completed.
        for _ in range(150):
            if pending: break
            page.wait_for_timeout(100)
        assert len(pending) == 1
        interrupted = snapshot()
        assert interrupted['snapshot']['step'] == 4 and interrupted['snapshot']['canReprepare'] is False
        count = len(requests)
        page.reload(wait_until='networkidle'); step(4)
        print('RESTORE_INTERRUPTION ' + json.dumps({'before': {k: interrupted['snapshot'][k] for k in ['step', 'busy', 'error', 'canReprepare']}, 'saved_after': {k: snapshot()['snapshot'][k] for k in ['step', 'busy', 'error', 'canReprepare']}, 'displayed_status': page.get_by_test_id('case-status').inner_text()}, ensure_ascii=False), flush=True)
        assert len(requests) == count
        assert '중단' in page.get_by_test_id('case-status').inner_text()
        assert page.get_by_test_id('case-run-top').is_enabled()
        page.unroute_all(behavior='ignoreErrors')
        try: pending[0][0].abort()
        except Exception: pass  # Reload may already have closed the old route.
        assert snapshot()['actionKey'] == pending[0][2]['idempotency_key']
        page.get_by_test_id('case-run-top').click(); step(6)
        after = snapshot()['snapshot']
        assert after['action']['action_id'] == pending[0][1]['action_id']
        assert after['action']['replayed'] is True
        actions = page.request.get(f"{args.api}/api/sessions/{after['session']}/evidence/actions").json()['actions']
        assert len(actions) == 1 and actions[0]['action_id'] == after['action']['action_id']
        assert after['events'][:len(interrupted['snapshot']['events'])] == interrupted['snapshot']['events']
        checks.append('reload with a real committed response held preserves its key; explicit resume returns one SQL-backed action')
        for width in [1440, 768, 390, 320]:
            page.set_viewport_size({'width': width, 'height': 960})
            page.reload(wait_until='networkidle'); step(6)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(args.output / f'case-restored-{width}.png'), full_page=True)
        checks.append('restored historical labels and action remain readable without document overflow at four widths')
        reset(); page.get_by_test_id('case-next').click(); step(1)
        old = snapshot()['snapshot']; page.reload(wait_until='networkidle')
        page.route('**/api/sessions/*/evidence', lambda r: r.fulfill(status=404, content_type='application/json', body='{"detail":"session_missing_or_expired"}'))
        page.get_by_test_id('case-run-top').click()
        page.wait_for_function('document.querySelector("[data-testid=case-status]").textContent.includes("세션 만료")')
        assert snapshot()['snapshot']['events'] == old['events']
        assert snapshot()['snapshot']['sessionExpired'] is True
        assert page.get_by_test_id('case-run-top').is_disabled()
        page.unroute('**/api/sessions/*/evidence')
        checks.append('injected session-expiry preflight stops continuation while preserving historical evidence')
        page.evaluate('(key) => sessionStorage.setItem(key, "{broken")', key)
        page.reload(wait_until='networkidle'); step(0)
        assert page.get_by_test_id('case-storage-warning').is_visible()
        checks.append('damaged checkpoint is rejected without breaking the page')
        # Existing stored evidence controls in the other engine too.
        for route, selector in [('serving','sustained-review'), ('recovery','failure-review')]:
            page.goto(args.base.rstrip('/') + '/#' + route, wait_until='networkidle')
            page.get_by_test_id(selector).wait_for()
            if route == 'serving':
                page.get_by_role('button', name='저장 후 응답 실패 1건').click()
                assert page.get_by_test_id('commit-exception').get_attribute('open') is not None
                assert 'deadline_exceeded_after_commit' in page.get_by_test_id('commit-exception').inner_text()
            for width in [1440, 390, 320]:
                page.set_viewport_size({'width': width, 'height': 960})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(args.output / f'{route}-{width}.png'), full_page=True)
        checks.append('stored serving exception and recovery layouts work in the selected browser engine')
        denied = browser.new_page(viewport={'width': 390, 'height': 960})
        denied.on('pageerror', lambda e: errors.append(str(e)))
        denied.add_init_script("for (const key of ['localStorage','sessionStorage']) Object.defineProperty(window,key,{get(){throw new DOMException('Storage disabled','SecurityError')}});")
        denied.goto(args.base, wait_until='networkidle')
        assert denied.get_by_test_id('case-study').is_visible()
        assert denied.get_by_test_id('case-storage-warning').is_visible()
        denied.locator('.case-connection-config > summary').click()
        denied.get_by_test_id('case-api-base').fill(args.api)
        denied.get_by_role('button', name='주소 적용', exact=True).click()
        denied.get_by_test_id('case-next').click()
        denied.wait_for_function('document.querySelector("[data-testid=case-study]").dataset.step === "1"', timeout=110000)
        assert denied.get_by_test_id('case-storage-warning').is_visible()
        denied.reload(wait_until='networkidle')
        assert denied.get_by_test_id('case-study').get_attribute('data-step') == '0'
        assert denied.get_by_test_id('case-storage-warning').is_visible()
        denied.close()
        checks.append('injected localStorage and sessionStorage denial keeps live execution usable with an explicit no-restore warning')
        assert not errors, errors
        report = {'engine': args.engine, 'browser_version': browser.version, 'scope': 'Playwright engine; not real-device Safari or user comprehension research', 'base': args.base, 'api': args.api, 'checks': checks, 'failures': failures, 'page_errors': errors, 'media': media, 'action_id': after['action']['action_id'], 'session': after['session']}
        (args.output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print('RESTORATION_RESULT ' + json.dumps(report, ensure_ascii=False), flush=True)
        for check in checks: print('PASS', check, flush=True)
        page.unroute_all(behavior='ignoreErrors')
        context.close()
        browser.close()
        assert not failures, failures


if __name__ == '__main__':
    main()
