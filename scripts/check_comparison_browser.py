"""Inspect the stored SQL comparison and normal-cost evidence in a real browser."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:5177')
    parser.add_argument('--browser-executable', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('work/action-comparison/browser'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(captured_at=datetime.now(timezone.utc).isoformat(), frontend=args.base,
                  scope='browser inspection of stored actual SQL experiments; no live comparison writes', checks=[], page_errors=[])
    def passed(name):
        report['checks'].append(dict(name=name, passed=True))
        print('PASS', name, flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser_executable, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(viewport=dict(width=1440, height=1100))
        page.set_default_timeout(6000)
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        try:
            page.goto(args.base, wait_until='networkidle')
            requests = []
            page.on('request', lambda request: requests.append(request.url))
            page.get_by_role('button', name='세 방식 비교', exact=True).click()
            expect(page.get_by_label('비교할 사건')).to_be_visible()
            expect(page.get_by_test_id('comparison-scope')).to_contain_text('저장된 SQL 실행 기록')
            passed('comparison is reachable from the first screen and identifies stored evidence')
            for database in ('sqlite', 'postgresql'):
                page.get_by_label('비교할 데이터베이스').select_option(database)
                page.get_by_label('비교할 사건').select_option('cited_edit_after_check')
                expect(page.get_by_test_id('comparison-source')).to_contain_text('100만 원')
                expect(page.get_by_test_id('comparison-receipt')).to_contain_text('300만 원')
                rows = page.get_by_test_id('comparison-case-results').get_by_role('row')
                expect(rows.nth(1)).to_contain_text('오래된 근거로 기록')
                expect(rows.nth(2)).to_contain_text('오래된 근거로 기록')
                expect(rows.nth(3)).to_contain_text('source_changed')
                page.get_by_label('비교할 사건').select_option('unrelated_edit')
                expect(page.get_by_test_id('comparison-case-results')).not_to_contain_text('실행 거절')
                page.get_by_label('비교할 사건').select_option('revision_aba')
                expect(page.get_by_test_id('comparison-source')).to_contain_text('v3')
                expect(page.get_by_test_id('comparison-source')).to_contain_text('300만 원')
                expect(page.get_by_test_id('comparison-case-results')).to_contain_text('source_changed')
                page.get_by_label('비교할 사건').select_option('duplicate_submission')
                expect(page.get_by_test_id('comparison-case-results')).to_contain_text('기존 작업 반환')
                with page.expect_download() as download:
                    page.get_by_role('button', name='선택한 사건 JSON', exact=True).click()
                target = args.output / f'{database}-case.json'
                download.value.save_as(str(target))
                selected = json.loads(target.read_text())
                assert selected['database'] == database and len(selected['results']) == 3
                for row in selected['results']:
                    attempts = row['case']['attempts']
                    assert attempts[0]['action_id'] == attempts[1]['action_id']
                passed(f'{database}: stale rejection, selective invalidation, ABA and retry match SQL evidence')
            page.get_by_label('비교할 동시 요청').select_option('replay_after_edit')
            rows = page.get_by_test_id('comparison-workload-results').get_by_role('row')
            expect(rows.nth(2)).to_contain_text('72')
            expect(rows.nth(3)).to_contain_text('72')
            expect(page.get_by_test_id('comparison-workload-note')).to_contain_text('과거 작업')
            page.get_by_label('비교할 동시 요청').select_option('edit_after_check')
            expect(page.get_by_test_id('comparison-workload-note')).to_contain_text('검사')
            expect(page.get_by_test_id('comparison-latency')).to_contain_text('90')
            expect(page.get_by_test_id('comparison-latency')).to_contain_text('p95')
            passed('contended outcomes and separate normal-path latency have visible denominators')
            page.get_by_label('비교할 동시 요청').select_option('lock_timeout_retry')
            expect(page.get_by_test_id('comparison-workload-note')).to_contain_text('시간 초과')
            rows = page.get_by_test_id('comparison-workload-results').get_by_role('row')
            for row in range(1, 4):
                expect(rows.nth(row)).to_contain_text('0 / 72')
                expect(rows.nth(row)).to_contain_text('72 / 72')
            passed('real lock-timeout errors remain visible beside separately recorded recovery')
            assert not any('/api/' in url for url in requests), requests
            passed('record inspection never triggers unsafe API execution')
            page.get_by_label('비교할 사건').select_option('cited_edit_after_check')
            page.get_by_label('비교할 동시 요청').select_option('edit_after_check')
            for width in (390, 768, 1440):
                page.set_viewport_size(dict(width=width, height=1100))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'overflow at {width}'
                page.locator('.safety-comparison').screenshot(path=str(args.output / f'comparison-{width}.png'))
            page.get_by_label('비교할 사건').focus()
            expect(page.get_by_label('비교할 사건')).to_be_focused()
            passed('390/768/1440 layouts fit and native controls are keyboard reachable')
            assert not report['page_errors'], report['page_errors']
        finally:
            (args.output / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            browser.close()


if __name__ == '__main__':
    main()
