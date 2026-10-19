#!/usr/bin/env python3
"""Actual HTTP case, navigation lifetime, delayed reset and explicitly injected expiry response."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlparse
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
        api_requests = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        def record_request(request):
            parsed = urlparse(request.url)
            if parsed.netloc == urlparse(args.api).netloc and (parsed.path.startswith('/api/') or parsed.path in ('/health', '/ready')):
                api_requests.append({'method': request.method, 'url': request.url})
        page.on('request', record_request)
        page.goto(args.base, wait_until='networkidle')
        case = page.get_by_test_id('case-study')
        assert case.count() == 1, 'Guided case must be the default entry'
        def step(number):
            page.wait_for_function('(n) => document.querySelector("[data-testid=case-study]")?.dataset.step === String(n)', arg=number, timeout=110000)
        def next_step(number):
            page.get_by_test_id('case-next').click()
            step(number)
        def navigate(name):
            target = page.get_by_role('button', name=name, exact=True, include_hidden=True)
            menu = page.locator('.supporting-menu')
            if menu.get_by_role('button', name=name, exact=True, include_hidden=True).count() and not target.is_visible():
                menu.locator('summary').click()
            target.click()
        def return_to_case():
            page.get_by_role('navigation', name='화면 선택').get_by_role('button', name='상담 기록', exact=True).click()
        def download_case(name):
            with page.expect_download() as download:
                page.get_by_role('button', name='사건 기록 JSON', exact=True).click()
            filename = args.output / name
            download.value.save_as(filename)
            return json.loads(filename.read_text())
        def configure(base):
            details = page.locator('.case-connection-config')
            if not details.evaluate('(el) => el.open'):
                details.locator('summary').click()
            page.get_by_test_id('case-api-base').fill(base)
            page.get_by_role('button', name='주소 적용', exact=True).click()
            details.locator('summary').click()
        configure(args.api)
        page.screenshot(path=str(args.output / 'case-initial-desktop.png'), full_page=True)
        assert page.get_by_role('heading', name='상담 기록', exact=True).is_visible()
        assert page.locator('.project-intro').count() == 0, 'Working screen must not render a marketing hero'
        assert page.locator('h1').evaluate('(el) => parseFloat(getComputedStyle(el).fontSize)') <= 22
        assert page.get_by_test_id('case-policy-value').inner_text() == '—', 'Do not present staged values as fetched policy'
        assert page.locator('.replay-result-guide').is_visible(), 'The check criteria must not be hidden by CSS'
        checks.append('compact working screen exposes check criteria and leaves unfetched policy blank')
        assert page.get_by_test_id('case-run-top').is_visible(), 'Top entry must start the real shared case'
        top_box = page.get_by_test_id('case-run-top').bounding_box()
        assert top_box['y'] + top_box['height'] < 760, 'Start must be visible without scrolling on desktop'
        # Same JS turn: both controls are clicked before React can paint disabled state.
        page.evaluate('''() => {
            document.querySelector('[data-testid=case-run-top]').click();
            document.querySelector('[data-testid=case-run-all]').click();
            document.querySelector('[data-testid=case-run-top]').click();
        }''')
        step(6)
        session_posts = [r for r in api_requests if r['method'] == 'POST' and r['url'].endswith('/api/sessions')]
        assert len(session_posts) == 1, 'Shared entry controls must create exactly one session'
        assert page.get_by_test_id('case-run-top').is_disabled()
        checks.append('top and existing run buttons clicked in one turn create one session and one flow')
        assert '300만 원' in page.get_by_test_id('case-old-draft').inner_text()
        assert '100만 원' in page.get_by_test_id('case-draft').inner_text()
        assert '오래된 답변 차단' in page.get_by_test_id('case-outcomes').inner_text()
        with page.expect_download() as automatic_download:
            page.get_by_role('button', name='사건 기록 JSON', exact=True).click()
        automatic_file = args.output / 'automatic-case.json'
        automatic_download.value.save_as(automatic_file)
        automatic_data = json.loads(automatic_file.read_text())
        automatic_actions = page.request.get(f"{args.api}/api/sessions/{automatic_data['session_id']}/evidence/actions").json()['actions']
        assert len(automatic_actions) == 1
        assert automatic_actions[0]['action_id'] == page.get_by_test_id('case-action').locator('code').inner_text()
        checks.append('one-click actual HTTP run preserves old/new answers and produces exactly one persisted task')
        completed_action = page.get_by_test_id('case-action').locator('code').inner_text()
        requests_before_result = len(api_requests)
        page.get_by_role('button', name='이번 실행 결과', exact=True).click()
        assert case.is_visible(), 'Result button must stay on this run, not open stored comparison evidence'
        assert page.get_by_test_id('case-outcomes').evaluate('(el) => el === document.activeElement')
        assert len(api_requests) == requests_before_result
        assert '새 답변 기록 완료' in page.get_by_test_id('case-outcomes').inner_text()
        checks.append('result button focuses the current run summary without navigation or API requests')
        requests_before_navigation = len(api_requests)
        page.get_by_role('button', name='세 방식 비교', exact=True).click()
        page.get_by_test_id('case-study').wait_for(state='hidden')
        return_to_case()
        step(6)
        page.wait_for_timeout(150)
        assert len(api_requests) == requests_before_navigation, 'Completed navigation must issue zero API operations'
        returned_data = download_case('completed-after-navigation.json')
        assert returned_data == automatic_data, 'Navigation must preserve the exact downloaded session, snapshot and event history'
        assert page.get_by_test_id('case-action').locator('code').inner_text() == completed_action
        checks.append('completed compare -> primary execution navigation preserves exact downloaded evidence and action with zero API requests')

        # Pause a real HTTP mutation while the application-owned flow is running.
        page.get_by_test_id('case-reset').click()
        next_step(1)
        inflight_before = download_case('inflight-before-navigation.json')
        held_events = []
        def hold_event(route):
            held_events.append(route)
        page.route('**/evidence/events', hold_event)
        with page.expect_request('**/evidence/events'):
            page.get_by_test_id('case-run-all').click()
        assert len(held_events) == 1
        assert page.get_by_test_id('case-run-top').is_disabled()
        assert page.get_by_test_id('case-run-all').is_disabled()
        requests_before_navigation = len(api_requests)
        navigate('서버 설계')
        page.get_by_test_id('case-study').wait_for(state='hidden')
        page.wait_for_timeout(100)
        assert len(api_requests) == requests_before_navigation, 'Unmounting the case view must not issue API operations'
        with page.expect_response(lambda response: '/execute' in response.url and response.status == 200 and response.json().get('replayed') is True, timeout=110000):
            held_events[0].continue_()
        page.unroute('**/evidence/events', hold_event)
        page.wait_for_timeout(150)
        requests_before_return = len(api_requests)
        return_to_case()
        step(6)
        page.wait_for_timeout(100)
        assert len(api_requests) == requests_before_return, 'Returning must not restart the completed hidden flow'
        inflight_after = download_case('inflight-after-navigation.json')
        assert inflight_after['session_id'] == inflight_before['session_id']
        assert inflight_after['events'][:len(inflight_before['events'])] == inflight_before['events']
        assert len([r for r in api_requests if r['url'].endswith(f"/api/sessions/{inflight_before['session_id']}/evidence/events")]) == 1
        inflight_actions = page.request.get(f"{args.api}/api/sessions/{inflight_after['session_id']}/evidence/actions").json()['actions']
        assert len(inflight_actions) == 1
        assert inflight_actions[0]['action_id'] == page.get_by_test_id('case-action').locator('code').inner_text()
        checks.append('held actual HTTP mutation continues while case view is absent; return preserves session, event prefix and one persisted action without duplicate navigation requests')
        page.get_by_test_id('case-reset').click()
        step(0)
        next_step(1)
        assert '300만 원' in page.get_by_test_id('case-source').inner_text()
        assert '300만 원' in page.get_by_test_id('case-draft').inner_text()
        next_step(2)
        assert '100만 원' in page.get_by_test_id('case-source').inner_text()
        assert '300만 원' in page.get_by_test_id('case-draft').inner_text()
        next_step(3)
        assert '오래된 답변 차단' in page.get_by_test_id('case-status').inner_text()
        assert '새 답변 기록 완료' not in page.get_by_test_id('case-outcomes').inner_text()
        assert '동일 작업 반환' not in page.get_by_test_id('case-outcomes').inner_text()
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
        assert '새 답변 기록 완료' not in page.get_by_test_id('case-outcomes').inner_text()
        page.unroute('**/evidence/receipts/*/execute', malformed_success)
        with page.expect_request('**/evidence/receipts/*/execute') as retried:
            next_step(5)
        assert retried.value.post_data_json['idempotency_key'] == rejected_keys[0]
        checks.append('lost commit response cannot claim success; retry retains original key and displays replay')
        assert '같은 작업 반환' in page.locator('.replay-gate h2').inner_text(), 'A lost commit response must display the actual replay result on retry'
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
                assert page.get_by_test_id('case-old-draft').locator('summary').evaluate('(el) => document.activeElement === el'), 'Focus must follow the visible answer before processing controls'
                page.keyboard.press('Tab')
                assert page.locator('.case-progress-detail summary').evaluate('(el) => document.activeElement === el')
                page.keyboard.press('Tab')
                assert page.get_by_test_id('case-next').evaluate('(el) => document.activeElement === el'), 'Collapsed progress must not trap keyboard focus'
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

        # This is a controlled HTTP 404 response, not a claim of real server TTL expiry.
        page.get_by_test_id('case-reset').click()
        next_step(1)
        before_expiry = download_case('before-injected-expiry.json')
        injected_expiry = []
        def expire_session(route):
            injected_expiry.append(route.request.url)
            route.fulfill(status=404, content_type='application/json', body='{"detail":"session_missing_or_expired"}')
        page.route('**/evidence/events', expire_session)
        page.get_by_test_id('case-next').click()
        page.get_by_role('alert').wait_for()
        page.unroute('**/evidence/events', expire_session)
        assert len(injected_expiry) == 1
        assert case.get_attribute('data-step') == '1'
        assert page.get_by_test_id('case-next').is_disabled()
        assert page.get_by_test_id('case-run-all').is_disabled()
        assert page.get_by_test_id('case-run-top').is_disabled()
        expired_data = download_case('injected-expiry-preserved.json')
        assert expired_data['session_id'] == before_expiry['session_id']
        assert expired_data['events'] == before_expiry['events']
        requests_before_navigation = len(api_requests)
        navigate('서버 설계')
        return_to_case()
        assert page.get_by_test_id('case-next').is_disabled()
        page.wait_for_timeout(100)
        assert len(api_requests) == requests_before_navigation
        assert download_case('injected-expiry-after-navigation.json') == expired_data
        page.get_by_test_id('case-reset').click()
        next_step(1)
        restarted_data = download_case('after-explicit-expiry-restart.json')
        assert restarted_data['session_id'] != expired_data['session_id']
        checks.append('injected HTTP404 session_missing_or_expired preserves historical evidence across navigation, disables continuation and requires explicit reset for a new real session')
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
        (args.output / 'case-browser.json').write_text(json.dumps({'frontend': args.base, 'api': args.api, 'checks': checks, 'page_errors': errors, 'api_requests': api_requests, 'expiry_scope': 'controlled HTTP404 response injection; real SQL-age expiry is a separate server check'}, ensure_ascii=False, indent=2) + '\n')
        for check in checks:
            print('PASS', check)
        browser.close()


if __name__ == '__main__':
    main()
