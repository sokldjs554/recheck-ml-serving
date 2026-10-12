"""Check measured serving evidence, deep links, and mobile access in a real browser."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:5175')
    parser.add_argument('--browser-executable', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('work/job-fit/browser'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser_executable, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.base, wait_until='networkidle')
        entry = page.get_by_role('navigation', name='실험 선택')
        assert entry.count() == 1, 'First screen must expose serving and recovery evidence'
        entry.get_by_role('link', name='모델 부하').click()
        page.get_by_role('heading', name='모델의 처리 한계').wait_for()
        assert page.get_by_test_id('serving-good').inner_text() == '896 / 900'
        assert '실시간' in page.get_by_test_id('stored-evidence-note').inner_text()
        assert page.locator('.mode-banner').count() == 0, 'Stored results must not be labeled browser simulation'
        handoff = page.get_by_role('region', name='학습 모델 인계 검증', exact=True)
        assert handoff.get_by_role('row').count() == 7
        assert handoff.get_by_role('cell', name='시작 차단', exact=True).count() == 5
        handoff.locator('summary').click()
        assert handoff.locator('.handoff-scores').is_visible()
        checks.append('model handoff shows startup rejection cases and expandable prediction values')
        page.get_by_role('button', name='60 req/s').click()
        assert page.get_by_test_id('serving-good').inner_text() == '2,572 / 3,600'
        counts = page.get_by_test_id('serving-outcomes').inner_text()
        assert all(number in counts for number in ('148', '775', '105')), counts
        assert 'API·DB' in page.get_by_test_id('serving-boundary').inner_text()
        page.screenshot(path=str(args.output / 'serving-desktop.png'), full_page=True)
        checks.append('all request outcomes including late HTTP 200 are visible; boundary and stored evidence are labeled')
        page.reload(wait_until='networkidle')
        page.get_by_role('heading', name='모델의 처리 한계').wait_for()
        checks.append('serving deep link survives reload')
        page.get_by_role('navigation', name='실험 선택').get_by_role('link', name='장애 복구').click()
        page.get_by_role('heading', name='장애에서 다시 추론까지').wait_for()
        assert '503' in page.get_by_test_id('recovery-proof').inner_text()
        assert '5' in page.get_by_test_id('postgres-recovery').inner_text()
        assert '32.717' in page.get_by_test_id('postgres-recovery').inner_text()
        public = page.get_by_role('region', name='공개 API 최근 관측')
        assert '65.1' in public.inner_text() and '2 / 3' in public.inner_text()
        assert public.get_by_role('link', name='실패한 원본 실행').get_attribute('href').endswith('38126563464')
        checks.append('actual dependency failure and nonzero DB restart errors are retained')
        page.get_by_role('button', name='운영 기록 조회', exact=True).click()
        page.get_by_test_id('public-operations').wait_for(timeout=95000)
        assert 'postgresql' in page.get_by_test_id('public-operations').inner_text()
        checks.append('public PostgreSQL journal is fetched and labeled as boot-scoped observations')
        for width in (320, 390, 768):
            page.set_viewport_size({'width': width, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'overflow at {width}'
            page.screenshot(path=str(args.output / f'recovery-{width}.png'), full_page=True)
        page.go_back(wait_until='networkidle')
        page.get_by_role('heading', name='모델의 처리 한계').wait_for()
        page.get_by_role('button', name='60 req/s').click()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        for width in (320, 390, 768):
            page.set_viewport_size({'width': width, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'serving overflow at {width}'
            page.screenshot(path=str(args.output / f'serving-{width}.png'), full_page=True)
        page.get_by_role('navigation', name='실험 선택').get_by_role('link', name='정합성 재현').click()
        page.get_by_test_id('case-study').wait_for()
        checks.append('back navigation, return to live case, and mobile layouts work')
        assert not errors, errors
        browser.close()
    report = {'checks': checks, 'page_errors': errors}
    (args.output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
