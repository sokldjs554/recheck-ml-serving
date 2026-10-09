"""Actual HTTP acceptance of evidence freshness/release lab; no fake successes."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:5175')
    parser.add_argument('--api',default='http://127.0.0.1:8012')
    parser.add_argument('--browser-executable',default='/usr/bin/chromium')
    parser.add_argument('--output',type=Path,default=Path('work/material-update/browser'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    report=dict(captured_at=datetime.now(timezone.utc).isoformat(),frontend=args.base,api=args.api,checks=[],page_errors=[],scope='actual HTTP API; fictional lexical retrieval; not LLM')
    def passed(name):
        report['checks'].append(dict(name=name,passed=True))
        print('PASS',name,flush=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.browser_executable,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport=dict(width=1440,height=1050))
        page.set_default_timeout(12000)
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        def click(name):
            page.get_by_role('button',name=name,exact=True).click()
        try:
            page.goto(args.base,wait_until='networkidle')
            click('근거 변경 실험')
            page.get_by_label('근거 실험 API 주소',exact=True).fill(args.api)
            click('실험 시작')
            expect(page.get_by_test_id('evidence-ready')).to_be_visible(timeout=100000)
            passed('real Python connection and isolated persistent session')
            click('답변 준비')
            expect(page.get_by_test_id('evidence-output')).to_contain_text('300만 원')
            click('지금 사용해도 되는지 확인')
            expect(page.get_by_test_id('evidence-validation')).to_contain_text('사용 가능')
            page.screenshot(path=str(args.output/'01-before.png'),full_page=True)
            passed('actual retrieval creates a currently usable receipt')
            page.get_by_label('문서 본문',exact=True).fill('하루 이체 한도는 100만 원입니다. 송금 본인 인증이 필요합니다.')
            click('수정 반영')
            expect(page.get_by_test_id('index-freshness')).to_contain_text('재구축 필요')
            expect(page.get_by_test_id('evidence-output')).to_contain_text('300만 원')
            click('지금 사용해도 되는지 확인')
            expect(page.get_by_test_id('evidence-validation')).to_contain_text('사용 거절')
            expect(page.get_by_test_id('evidence-validation')).to_contain_text('인용한 문서가 수정')
            page.screenshot(path=str(args.output/'02-refused.png'),full_page=True)
            passed('actual source edit preserves historical output and refuses its use')
            page.get_by_label('배포 후보',exact=True).select_option('mismatch')
            click('후보 평가')
            expect(page.get_by_test_id('release-verdict')).to_contain_text('배포 차단')
            expect(page.get_by_role('button',name='검증된 모델·인덱스 적용',exact=True)).to_be_disabled()
            expect(page.get_by_test_id('release-epoch')).to_have_text('r1')
            passed('same dimension incompatible model/index cannot deploy')
            page.get_by_label('배포 후보',exact=True).select_option('regressed')
            click('후보 평가')
            expect(page.get_by_test_id('release-verdict')).to_contain_text('배포 차단')
            expect(page.get_by_test_id('release-report')).to_contain_text('검색 품질')
            with page.expect_download() as download:
                click('평가 원본 JSON')
            download.value.save_as(str(args.output/'release-negative.json'))
            assert not json.loads((args.output/'release-negative.json').read_text())['passed']
            page.screenshot(path=str(args.output/'03-quality-gate.png'),full_page=True)
            passed('computed quality regression fails and real report is downloadable')
            page.get_by_label('배포 후보',exact=True).select_option('paired')
            click('후보 평가')
            expect(page.get_by_test_id('release-verdict')).to_contain_text('배포 가능')
            click('검증된 모델·인덱스 적용')
            expect(page.get_by_test_id('release-epoch')).to_have_text('r2')
            click('답변 준비')
            expect(page.get_by_test_id('evidence-output')).to_contain_text('100만 원')
            click('지금 사용해도 되는지 확인')
            expect(page.get_by_test_id('evidence-validation')).to_contain_text('사용 가능')
            passed('paired rebuild switches atomically and new receipt cites edited content')
            click('업무 체크리스트')
            click('답변 준비')
            expect(page.get_by_test_id('evidence-output')).to_contain_text('□ 적용 내용 확인')
            passed('second product reuses the evidence lifecycle')
            click('문서 삭제')
            click('지금 사용해도 되는지 확인')
            expect(page.get_by_test_id('evidence-validation')).to_contain_text('삭제')
            passed('deleted evidence cannot be used')
            for width in (390,768,1440):
                page.set_viewport_size(dict(width=width,height=1000))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'overflow at {width}'
                page.screenshot(path=str(args.output/f'04-layout-{width}.png'),full_page=True)
            passed('390/768/1440 responsive layout without document overflow')
            page.set_viewport_size(dict(width=1440,height=1050))
            click('새 실험')
            click('답변 준비')
            # Abort a real request to prove a network failure cannot retain a valid badge.
            click('지금 사용해도 되는지 확인')
            expect(page.get_by_test_id('evidence-validation')).to_contain_text('사용 가능')
            page.route('**/evidence/receipts/*/use',lambda route:route.abort())
            click('지금 사용해도 되는지 확인')
            expect(page.get_by_role('alert')).to_be_visible()
            expect(page.get_by_test_id('evidence-validation')).not_to_be_visible()
            page.unroute('**/evidence/receipts/*/use')
            passed('HTTP failure clears previous validation instead of showing success')
            # A failed mutation also clears previous use-time validation.
            page.route('**/evidence/events',lambda route: route.abort())
            page.get_by_label('문서 본문',exact=True).fill('하루 이체 한도는 200만 원입니다.')
            click('수정 반영')
            expect(page.get_by_role('alert')).to_be_visible()
            expect(page.get_by_test_id('evidence-validation')).not_to_be_visible()
            page.unroute('**/evidence/events')
            passed('failed document update leaves no stale success assertion')
            held=[]
            page.route('**/evidence/events', lambda route: held.append(route))
            click('수정 반영')
            expect(page.get_by_role('button',name='지금 사용해도 되는지 확인',exact=True)).to_be_disabled()
            expect(page.get_by_role('button',name='새 실험',exact=True)).to_be_disabled()
            page.wait_for_timeout(150)
            assert held, 'mutation request must actually be in flight'
            # Unmount the old session; completion may not leak into a new lab.
            click('서버 설계')
            held[0].continue_()
            page.unroute('**/evidence/events')
            click('근거 변경 실험')
            expect(page.get_by_role('button',name='실험 시작',exact=True)).to_be_visible()
            expect(page.get_by_test_id('evidence-output')).not_to_be_visible()
            passed('pending mutation disables reuse and late completion cannot overwrite a new lab')
            assert not report['page_errors'], report['page_errors']
        finally:
            (args.output/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            page.screenshot(path=str(args.output/'last-state.png'),full_page=True)
            browser.close()


if __name__=='__main__':
    main()
