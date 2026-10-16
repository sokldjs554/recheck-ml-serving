"""Verify the submitted demo's entry points, prerecorded media and responsive disclosures."""
import argparse
import json
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:5178')
    parser.add_argument('--api', default='http://127.0.0.1:8023')
    parser.add_argument('--browser-executable', default='/usr/bin/chromium')
    parser.add_argument('--output', type=Path, default=Path('work/presentation-browser'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks, errors, api_requests = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser_executable, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.add_init_script('localStorage.setItem("recheck-api-base", ' + json.dumps(args.api) + ')')
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: api_requests.append(request.url) if request.url.startswith(args.api.rstrip('/') + '/') else None)
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
        for source in video.locator('source').all():
            url = urljoin(page.url, source.get_attribute('src'))
            response = page.request.get(url)
            assert response.status == 200, f'Media delivery: {url} returned {response.status}'
            assert source.get_attribute('type') in response.headers.get('content-type', '')
            assert len(response.body()) > 10000
            print('Media delivered', url, response.status, response.headers.get('content-type'), flush=True)
        codecs = video.evaluate('''(v) => ({h264: v.canPlayType('video/mp4; codecs="avc1.640020"'), vp9: v.canPlayType('video/webm; codecs="vp9"')})''')
        print('Browser codecs', json.dumps(codecs), flush=True)
        print('Checking actual video playback while live health is pending', flush=True)
        video.evaluate('(v) => { v.muted = true; v.play().catch(e => { v.dataset.playbackError = String(e); }); }')
        try:
            page.wait_for_function('document.querySelector("video").currentTime > .2 && document.querySelector("video").videoWidth === 1280', timeout=20000)
        except Exception:
            diagnostic = video.evaluate('(v) => ({source:v.currentSrc,ready:v.readyState,network:v.networkState,error:v.error?.message,playbackError:v.dataset.playbackError,codec:v.canPlayType("video/mp4")})')
            print('VIDEO FAILURE', json.dumps(diagnostic), flush=True)
            raise
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
        checks.append('actual recording decodes while live health request is pending; stored label, live state, and shared controls remain distinct')
        journal = page.get_by_test_id('case-journal')
        requests_before_inspection = len(api_requests)
        count = page.get_by_test_id('case-events').locator('li').count()
        journal.get_by_role('button', name='실행 차단', exact=True).click()
        assert page.get_by_test_id('case-events').locator('li').count() == 1
        assert 'source_changed' in journal.inner_text()
        journal.get_by_role('button', name='기록·재시도', exact=True).click()
        assert page.get_by_test_id('case-events').locator('li').count() == 2
        assert journal.inner_text().count(action) == 2
        assert '새 작업 기록' in journal.inner_text() and '기존 작업 반환' in journal.inner_text()
        journal.locator('details').first.locator('summary').click()
        assert action in journal.locator('pre').first.inner_text()
        journal.get_by_role('button', name='전체', exact=True).click()
        assert page.get_by_test_id('case-events').locator('li').count() == count
        assert len(api_requests) == requests_before_inspection, 'Log filters must not send API requests'
        checks.append('journal filters retain all original events; blocked write and same-ID record/replay are distinguishable')
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
            if route == 'serving':
                selected = page.get_by_test_id('phase-detail')
                phases = json.loads((Path(__file__).resolve().parents[1] / 'demo/src/serving-evidence.json').read_text())['sustained']['phases']
                requests_before_inspection = len(api_requests)
                for i, phase in enumerate(phases):
                    control = page.get_by_test_id('phase-select').nth(i)
                    assert control.locator('.phase-track').bounding_box()['width'] > 10
                    for bar in control.locator('.phase-track > *').all():
                        assert bar.bounding_box()['width'] > 0 and bar.bounding_box()['height'] > 0
                    control.focus()
                    control.press('Enter')
                    text = selected.inner_text()
                    assert f"{phase['good']:,}" in text and f"{phase['attempted']:,}" in text
                    assert f"{phase['cycle']}회" in text
                    assert f"{phase['cohort_rates_rps']['good']:.2f} req/s" in text
                    assert control.get_attribute('aria-pressed') == 'true'
                assert len(api_requests) == requests_before_inspection, 'Stored phases must not send API requests'
                checks.append('six stored phases can be selected; offered and useful counts stay tied to the selected cohort')
            else:
                trace = page.get_by_test_id('trace-explorer')
                requests_before_inspection = len(api_requests)
                trace.locator('button[data-span-name="model.infer"]').click()
                assert '503: model_unavailable' in trace.get_by_test_id('span-detail').inner_text()
                assert 'recheck-worker' in trace.get_by_test_id('span-detail').inner_text()
                trace.get_by_test_id('trace-recovered').click()
                assert trace.locator('button[data-span-name="model.predict"]').count() == 1
                trace.locator('button[data-span-name="fence.commit"]').click()
                assert 'SQL 커밋 시간' in trace.get_by_test_id('span-detail').inner_text()
                assert '21fe3c1a-28f1-4360-ade8-e88c5ef2a996' in trace.inner_text()
                trace.get_by_test_id('trace-failed').click()
                assert trace.locator('button[data-span-name="model.predict"]').count() == 0
                assert len(api_requests) == requests_before_inspection, 'Stored trace inspection must not send API requests'
                checks.append('captured failure/recovery spans, model exception and matching SQL receipt are inspectable without fabricated DB span')
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
