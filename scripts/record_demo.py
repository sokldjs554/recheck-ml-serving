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
    case=page.get_by_test_id('case-study')
    case.evaluate('(e)=>e.scrollIntoView({block:"start"})'); page.wait_for_timeout(1000)
    for step in range(1,7):
        page.get_by_test_id('case-next').click()
        page.wait_for_function('(s)=>document.querySelector("[data-testid=case-study]").dataset.step===String(s)',arg=step)
        case.evaluate('(e)=>e.scrollIntoView({block:"start"})')
        page.wait_for_timeout(3400 if step not in (3,6) else 5000)
    action=page.get_by_test_id('case-action').locator('code').inner_text()
    page.screenshot(path=str(out/'poster.png'))
    with page.expect_download() as d: page.get_by_role('button',name='사건 기록 JSON',exact=True).click()
    d.value.save_as(str(out/'case.json'))
    journal = page.get_by_test_id('case-journal')
    journal.get_by_role('button',name='실행 차단',exact=True).click()
    journal.scroll_into_view_if_needed();page.wait_for_timeout(2500)
    journal.get_by_role('button',name='기록·재시도',exact=True).click()
    journal.scroll_into_view_if_needed();page.wait_for_timeout(3000)
    # Show preserved result through an actual round trip to comparison.
    page.get_by_role('button',name='세 방식 비교',exact=True).click();page.evaluate('scrollTo(0,0)');page.wait_for_timeout(3000)
    page.get_by_role('navigation',name='실험 선택').get_by_role('button',name='실행 재현',exact=True).click()
    assert page.get_by_test_id('case-action').locator('code').inner_text()==action
    case.evaluate('(e)=>e.scrollIntoView({block:"start"})');page.wait_for_timeout(3500)
    video=page.video;context.close();path=Path(video.path());browser.close()
    (out/'capture.json').write_text(json.dumps({'recorded_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'Actual local Python API and SQLite; six manually advanced steps, blocked/record/replay journal filters, then comparison and return. No intercepted or fabricated API responses. No speed changes.','responses':responses,'action_id':action,'raw_video':str(path)},ensure_ascii=False,indent=2))
    subprocess.run(['ffmpeg','-y','-ss','1','-i',str(path),'-an','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(root/'demo/public/media/recheck-walkthrough.mp4')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    subprocess.run(['ffmpeg','-y','-i',str(out/'poster.png'),'-quality','85',str(root/'demo/public/media/recheck-poster.webp'),'-loglevel','error'],check=True)
    subprocess.run(['ffmpeg','-y','-ss','1','-i',str(path),'-an','-c:v','libvpx-vp9','-b:v','0','-crf','32','-deadline','realtime','-cpu-used','6','-row-mt','1',str(root/'demo/public/media/recheck-walkthrough.webm'),'-loglevel','error'],check=True)
