"""Record six real case steps and a comparison round trip; requires running local API/UI and ffmpeg.

PLAYWRIGHT_BROWSERS_PATH must contain Playwright's ffmpeg, or run playwright install ffmpeg.
No mocked HTTP, frame synthesis or playback speed changes are used.
"""
import argparse
import json, time, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base',default='http://127.0.0.1:5178')
parser.add_argument('--api',default='http://127.0.0.1:8023')
parser.add_argument('--output',type=Path,default=Path('work/recording'))
parser.add_argument('--browser-executable',default='/usr/bin/chromium')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1];out=args.output;out.mkdir(parents=True,exist_ok=True)
(root/'demo/public/media').mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=args.browser_executable, args=['--no-sandbox','--disable-dev-shm-usage'])
    context=browser.new_context(viewport={'width':1280,'height':1080},record_video_dir=str(out),record_video_size={'width':1280,'height':1080})
    context.add_init_script('localStorage.setItem("recheck-api-base", ' + json.dumps(args.api) + ')')
    page=context.new_page(); responses=[]
    page.on('response',lambda r: responses.append({'url':r.url,'status':r.status}) if '/api/' in r.url else None)
    page.goto(args.base,wait_until='networkidle'); page.wait_for_timeout(2800)
    page.screenshot(path=str(out/'entry.jpg'),type='jpeg',quality=85)
    case=page.get_by_test_id('case-study')
    case.evaluate('(e)=>e.scrollIntoView({block:"start"})'); page.wait_for_timeout(1000)
    for step in range(1,7):
        page.get_by_test_id('case-next').click()
        page.wait_for_function('(s)=>document.querySelector("[data-testid=case-study]").dataset.step===String(s)',arg=step)
        case.evaluate('(e)=>e.scrollIntoView({block:"start"})')
        page.wait_for_timeout(2600 if step not in (3,6) else 4000)
        if step in (3,6):
            page.evaluate('scrollTo(0,0)');page.screenshot(path=str(out/f'step-{step}.jpg'),type='jpeg',quality=85)
    action=page.get_by_test_id('case-action').locator('code').inner_text()
    page.get_by_test_id('case-action').scroll_into_view_if_needed()
    page.screenshot(path=str(out/'poster.png'))
    page.locator('.replay-audit > summary').click()
    with page.expect_download() as d: page.get_by_role('button',name='사건 기록 JSON',exact=True).click()
    d.value.save_as(str(out/'case.json'))
    journal = page.get_by_test_id('case-journal')
    journal.get_by_role('button',name='실행 차단',exact=True).click()
    journal.scroll_into_view_if_needed();page.wait_for_timeout(2500)
    journal.get_by_role('button',name='기록·재시도',exact=True).click()
    journal.scroll_into_view_if_needed();page.wait_for_timeout(3000)
    # Show preserved result through an actual round trip to comparison.
    page.get_by_role('button',name='세 방식 비교',exact=True).click();page.evaluate('scrollTo(0,0)');page.wait_for_timeout(3000)
    nav=page.get_by_role('navigation',name='화면 선택')
    nav.get_by_role('button',name='실행 기록',exact=True).click()
    assert page.get_by_test_id('case-action').locator('code').inner_text()==action
    case.evaluate('(e)=>e.scrollIntoView({block:"start"})');page.wait_for_timeout(2000)
    page.get_by_role('button',name='직접 구성',exact=True).click()
    page.get_by_role('button',name='실험 시작',exact=True).click()
    page.get_by_test_id('evidence-ready').wait_for(timeout=100000)
    page.get_by_label('근거 문서',exact=True).select_option('refund')
    page.get_by_role('button',name='답변 준비',exact=True).click()
    page.get_by_test_id('evidence-output').wait_for()
    page.get_by_role('button',name='이 답변으로 작업 기록',exact=True).click()
    page.locator('.task-result').wait_for()
    page.wait_for_timeout(2500)
    page.get_by_role('button',name='같은 요청 재시도',exact=True).click()
    page.wait_for_function('document.querySelector(".task-result")?.textContent.includes("같은 작업 반환")')
    page.get_by_role('button',name='서버 기록 조회',exact=True).click()
    page.get_by_test_id('custom-execution').locator('.server-records li').wait_for()
    page.get_by_test_id('custom-execution').scroll_into_view_if_needed();page.wait_for_timeout(2500)
    (out/'custom-action.json').write_text(json.dumps({'receipt_and_response':page.get_by_test_id('custom-execution').locator('pre').text_content(),'server_record':page.get_by_test_id('custom-execution').locator('.server-records').inner_text()},ensure_ascii=False,indent=2))
    page.locator('.el-workbench').scroll_into_view_if_needed();page.screenshot(path=str(out/'custom.jpg'),type='jpeg',quality=85)
    nav.get_by_role('link',name='모델 부하',exact=True).click()
    page.evaluate('scrollTo(0,0)');page.wait_for_timeout(4500)
    page.get_by_test_id('phase-select').nth(1).click();page.wait_for_timeout(3000)
    page.screenshot(path=str(out/'serving.jpg'),type='jpeg',quality=85)
    nav.get_by_role('link',name='장애 복구',exact=True).click()
    page.evaluate('scrollTo(0,0)');page.wait_for_timeout(4500)
    page.screenshot(path=str(out/'recovery.jpg'),type='jpeg',quality=85)
    nav.get_by_role('button',name='실행 기록',exact=True).click()
    assert page.get_by_test_id('case-action').locator('code').inner_text()==action
    page.get_by_test_id('case-action').scroll_into_view_if_needed();page.wait_for_timeout(2500)
    video=page.video;context.close();path=Path(video.path());browser.close()
    (out/'capture.json').write_text(json.dumps({'recorded_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'scope':'Current UI with actual local Python API and SQLite; six manually advanced steps, blocked/record/replay journal filters, comparison round trip, custom refund-document record/replay and server-record lookup, archived model-load and recovery screens, return with same action ID. No intercepted or fabricated API responses. No speed changes.','responses':responses,'action_id':action,'raw_video':str(path)},ensure_ascii=False,indent=2))
    subprocess.run(['ffmpeg','-y','-ss','1','-i',str(path),'-an','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(root/'demo/public/media/recheck-workspace-20261019.mp4')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    subprocess.run(['ffmpeg','-y','-i',str(out/'poster.png'),'-quality','85',str(root/'demo/public/media/recheck-workspace-poster-20261019.webp'),'-loglevel','error'],check=True)
    subprocess.run(['ffmpeg','-y','-ss','1','-i',str(path),'-an','-c:v','libvpx-vp9','-b:v','0','-crf','32','-deadline','realtime','-cpu-used','6','-row-mt','1',str(root/'demo/public/media/recheck-workspace-20261019.webm'),'-loglevel','error'],check=True)
