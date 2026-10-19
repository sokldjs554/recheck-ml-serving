"""Film the final consultation workspace using actual local HTTP; no mocked responses or speed changes."""
import argparse, json, subprocess, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',default='http://127.0.0.1:5173');p.add_argument('--api',default='http://127.0.0.1:8025');p.add_argument('--output',type=Path,default=Path('work/record-results/film'));p.add_argument('--browser-executable',default='/usr/bin/chromium');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[1];media=root/'demo/public/media';observations=[]
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path=a.browser_executable,args=['--no-sandbox','--disable-dev-shm-usage'])
    ctx=b.new_context(viewport={'width':1280,'height':1080},record_video_dir=str(a.output),record_video_size={'width':1280,'height':1080})
    page=ctx.new_page();page.add_init_script('localStorage.setItem("recheck-api-base",'+json.dumps(a.api)+')');page.goto(a.base,wait_until='networkidle');page.wait_for_timeout(2200)
    def advance(n):
        page.get_by_test_id('case-next').click();page.wait_for_function('(n)=>document.querySelector("[data-testid=case-study]").dataset.step===String(n)',arg=n);expect(page.get_by_test_id('case-next')).to_be_enabled()
        page.locator('.replay-machine').scroll_into_view_if_needed();page.wait_for_timeout(2600)
    for n in [1,2,3]:advance(n)
    page.wait_for_timeout(5000);page.locator('.replay-machine').screenshot(path=str(a.output/'blocked.jpg'),type='jpeg',quality=90)
    advance(4);advance(5)
    def capture(label):
        s=page.evaluate('JSON.parse(sessionStorage.getItem("recheck-case-checkpoint-v1")).snapshot');rows=page.request.get(f'{a.api}/api/sessions/{s["session"]}/evidence/actions').json()['actions'];assert len(rows)==1 and rows[0]['output']==s['freshReceipt']['output'] and rows[0]['action_id']==s['action']['action_id'];observations.append({'label':label,'post_action':s['action'],'get_actions':rows})
    capture('before retry');page.wait_for_timeout(5000)
    advance(6);capture('after retry');assert observations[0]['get_actions']==observations[1]['get_actions'];assert observations[1]['post_action']['replayed']
    page.wait_for_timeout(5000);page.locator('.replay-machine').screenshot(path=str(a.output/'replayed.jpg'),type='jpeg',quality=90);page.screenshot(path=str(a.output/'poster.png'))
    page.get_by_test_id('server-records').locator('details > summary').click();page.wait_for_timeout(3500)
    page.locator('.replay-audit > summary').click()
    with page.expect_download() as d:page.get_by_role('button',name='사건 기록 JSON',exact=True).click()
    d.value.save_as(str(a.output/'case.json'))
    v=page.video;ctx.close();raw=Path(v.path());b.close()
    (a.output/'capture.json').write_text(json.dumps({'recorded_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source_base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'scope':'Actual local Python API with SQLite, final consultation UI. Manual progression with reading pauses in recording only. Rejected answer, GET-confirmed single saved answer, same-key retry and unchanged action ID. No request mocks or speed changes.','observations':observations},ensure_ascii=False,indent=2))
    for extension,codec in [('mp4',['-c:v','libx264','-preset','fast','-crf','25','-pix_fmt','yuv420p','-movflags','+faststart']),('webm',['-c:v','libvpx-vp9','-b:v','0','-crf','34','-deadline','realtime','-cpu-used','6','-row-mt','1'])]:
        subprocess.run(['ffmpeg','-y','-i',str(raw),'-an',*codec,str(media/f'recheck-records-query-20261019.{extension}'),'-loglevel','error'],check=True)
    subprocess.run(['ffmpeg','-y','-i',str(a.output/'poster.png'),'-quality','85',str(media/'recheck-records-query-poster-20261019.webp'),'-loglevel','error'],check=True)
