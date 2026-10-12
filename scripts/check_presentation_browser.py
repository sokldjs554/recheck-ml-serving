"""Verify the submitted demo's entry points, prerecorded media and responsive disclosures."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:5178')
    parser.add_argument('--api', default='http://127.0.0.1:8023')
    parser.add_argument('--browser-executable', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('work/presentation-browser'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser_executable, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.add_init_script('localStorage.setItem("recheck-api-base", ' + json.dumps(args.api) + ')')
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.base, wait_until='networkidle')
        assert page.get_by_test_id('case-run-top').is_visible()
        assert page.locator('video').get_attribute('preload') == 'none', 'Do not download the recording before the visitor asks'
        pending = []
        page.route('**/health', lambda route: pending.append(route))
        page.get_by_test_id('case-run-top').click()
        page.wait_for_function('document.querySelector("[data-testid=case-run-top]").disabled')
        page.get_by_test_id('recorded-demo').locator('summary').click()
        assert '현재 요청' in page.get_by_test_id('recorded-demo').inner_text()
        assert '실행 중' in page.get_by_test_id('case-run-top').inner_text()
        video = page.locator('video')
        video.evaluate('(v) => { v.muted = true; return v.play(); }')
        page.wait_for_function('document.querySelector("video").currentTime > .2 && document.querySelector("video").videoWidth === 1280')
        media = video.evaluate('(v) => ({source:v.currentSrc,duration:v.duration,width:v.videoWidth,height:v.videoHeight,poster:v.poster})')
        assert 20 < media['duration'] < 90
        assert media['source'].startswith(args.base.rstrip('/') + '/media/')
        poster = page.request.get(media['poster'])
        assert poster.status == 200 and 'image/webp' in poster.headers.get('content-type', '')
        video.evaluate('(v) => v.pause()')
        assert len(pending) == 1
        assert page.get_by_test_id('case-run-all').is_disabled()
        pending[0].continue_()
        page.unroute('**/health')
        page.wait_for_function('document.querySelector("[data-testid=case-study]").dataset.step === "6"', timeout=110000)
        action = page.get_by_test_id('case-action').locator('code').inner_text()
        checks.append('actual MP4 decodes while live health request is pending; stored label, live state, and shared controls remain distinct')
        for width in (1440, 768, 390, 320):
            page.set_viewport_size({'width':width,'height':960})
            page.evaluate('scrollTo(0,0)')
            assert page.get_by_test_id('case-run-top').bounding_box()['y'] < 760
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'case/media overflow at {width}'
            assert video.bounding_box()['width'] <= width
            page.screenshot(path=str(args.output / f'case-media-{width}.png'), full_page=True)
        checks.append('1440/768/390/320: top control, expanded recording and case have no page overflow')
        for route, selector in [('serving','sustained-review'),('recovery','failure-review')]:
            page.goto(args.base.rstrip('/')+'/#'+route, wait_until='networkidle')
            article=page.get_by_test_id(selector)
            article.locator('.review-scope').wait_for()
            assert article.locator('.review-scope').is_visible()
            details=article.locator(':scope > details')
            for i in range(details.count()):
                assert not details.nth(i).evaluate('(e)=>e.open')
                details.nth(i).locator(':scope > summary').click()
                assert details.nth(i).evaluate('(e)=>e.open')
            for width in (1440,768,390,320):
                page.set_viewport_size({'width':width,'height':960})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'{route} disclosure overflow at {width}'
                for table in article.locator('.review-table-scroll').all():
                    assert table.evaluate('(e)=>e.clientWidth <= innerWidth')
                    table.evaluate('(e)=>e.scrollLeft=e.scrollWidth')
                page.screenshot(path=str(args.output/f'{route}-expanded-{width}.png'),full_page=True)
            checks.append(f'{route}: visible scope/results, collapsed conditions/raw data, expanded layout and contained table scrolling at four widths')
        assert not errors, errors
        browser.close()
    report={'checks':checks,'media':media,'action_id':action,'page_errors':errors}
    (args.output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    for check in checks: print('PASS',check)

if __name__ == '__main__':
    main()
