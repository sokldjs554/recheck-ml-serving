"""Reconcile rendered answer records with actual API rows; failure injection is local/browser-side."""
import argparse, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', required=True); p.add_argument('--api', required=True)
    p.add_argument('--browser-executable', default='/usr/bin/chromium'); p.add_argument('--output', type=Path, default=Path('work/records-browser'))
    a=p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
    evidence={'base':a.base,'api':a.api,'observed_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':[],'requests':[],'observations':[]}
    with sync_playwright() as pw:
        b=pw.chromium.launch(executable_path=a.browser_executable,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=b.new_page(viewport={'width':1440,'height':1050});page.set_default_timeout(20000)
        page.add_init_script('localStorage.setItem("recheck-api-base",'+json.dumps(a.api)+')')
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:evidence['requests'].append({'method':r.method,'url':r.url,'body':r.post_data_json if r.method=='POST' else None}) if '/api/sessions/' in r.url and '/evidence/' in r.url else None)
        page.goto(a.base,wait_until='networkidle')
        def records(): return page.get_by_test_id('server-records').filter(visible=True)
        def settled(): expect(records()).to_have_attribute('aria-busy','false')
        def next_step(n):
            page.get_by_test_id('case-next').click();page.wait_for_function('(n)=>document.querySelector("[data-testid=case-study]").dataset.step===String(n)',arg=n);expect(page.get_by_test_id('case-next')).to_be_enabled();settled()
        def query():
            with page.expect_response('**/evidence/actions'):
                records().get_by_role('button',name='서버 기록 조회').click()
            settled()
        def snapshot():return page.evaluate('JSON.parse(sessionStorage.getItem("recheck-case-checkpoint-v1")).snapshot')
        def reconcile(label,sid):
            settled();rows=page.request.get(f'{a.api}/api/sessions/{sid}/evidence/actions').json()['actions']
            ui=records().locator('li').evaluate_all('(els)=>els.map(e=>({action_id:e.dataset.actionId,output:e.querySelector(".stored-answer").textContent}))')
            assert ui==[{'action_id':r['action_id'],'output':r['output']} for r in rows], (ui,rows)
            expect(records().get_by_test_id('record-count')).to_have_text(f'{len(rows)}개 작업')
            evidence['observations'].append({'label':label,'session':sid,'api_rows':rows,'rendered_rows':ui});return rows
        def passed(s):evidence['checks'].append(s);print('PASS',s,flush=True)
        expect(records()).to_contain_text('조회 전');expect(records().get_by_test_id('record-count')).to_have_count(0)
        page.get_by_test_id('case-run-top').click();expect(page.get_by_test_id('case-run-top')).to_be_enabled(timeout=110000);settled()
        assert snapshot()['step']==1
        assert not any(r['url'].endswith('/execute') for r in evidence['requests']), 'First action only prepares; no write before the visitor can inspect the output'
        sid=snapshot()['session'];assert reconcile('new empty session',sid)==[]
        passed('unqueried is distinct from GET-confirmed empty; prepared answer does not create a stored task')
        next_step(2);next_step(3);old=snapshot()['oldReceipt'];assert reconcile('blocked answer absent',sid)==[]
        assert old['output']==page.locator('.case-answer-text').text_content().strip()
        pair=page.get_by_test_id('source-comparison');expect(pair).to_have_attribute('open','')
        source=next(s for s in snapshot()['state']['sources'] if s['source_id']==old['references'][0]['source_id'])
        expect(pair.get_by_test_id('cited-source')).to_have_text(old['references'][0]['text'])
        expect(pair.get_by_test_id('current-source')).to_have_text(source['text'])
        assert source['text']!=old['references'][0]['text']
        expect(records().get_by_test_id('request-outcome')).to_have_text('이번 기록 요청 거절')
        page.locator('.replay-machine').screenshot(path=str(a.output/'blocked.jpg'),type='jpeg',quality=90)
        passed('blocked intended answer remains readable and is absent from actual saved records')
        next_step(4);next_step(5);fresh=snapshot()['freshReceipt'];before=reconcile('recorded before retry',sid)
        assert len(before)==1 and before[0]['output']==fresh['output'] and before[0]['action_id']==snapshot()['action']['action_id']
        expect(records().get_by_test_id('request-outcome')).to_have_text('새 기록 저장')
        page.locator('.replay-machine').screenshot(path=str(a.output/'recorded.jpg'),type='jpeg',quality=90)
        passed('valid POST body and action ID match automatic GET and displayed full answer')
        held=[];page.route('**/evidence/actions',lambda r:held.append(r))
        page.get_by_test_id('case-next').click();page.wait_for_function('document.querySelector("[data-testid=case-study]").dataset.step==="6"');expect(records()).to_have_attribute('aria-busy','true')
        assert page.locator('[data-testid=case-status] .case-spin').count()==1, 'Step number advances before the follow-up GET finishes; it is not a completion signal'
        expect(page.get_by_test_id('case-status')).to_contain_text('작업 기록 조회 중')
        expect(records()).to_contain_text('아직 확인되지')
        assert len(held)==1
        held[0].fulfill(status=503,content_type='application/json',body='{"detail":"injected_read_unavailable"}');settled()
        expect(records()).to_contain_text('현재 조회 실패');expect(records()).to_contain_text('마지막으로 확인한 기록')
        page.unroute('**/evidence/actions');query();after=reconcile('after same-key retry and successful fresh GET',sid)
        assert before==after;expect(records()).to_contain_text('이번 요청으로 추가된 기록 0건')
        expect(records().get_by_test_id('request-outcome')).to_have_text('기존 기록 반환')
        writes=[r for r in evidence['requests'] if r['url'].endswith('/execute')];assert writes[-1]['body']==writes[-2]['body']
        passed('same-key retry performs a new GET even with identical action ID; failed GET retains labelled old rows; successful refresh confirms same single record')
        page.locator('.replay-machine').screenshot(path=str(a.output/'replayed.jpg'),type='jpeg',quality=90)
        count=len(evidence['requests']);page.get_by_role('button',name='세 방식 비교',exact=True).click();page.get_by_role('navigation',name='화면 선택').get_by_role('button',name='답변 기록',exact=True).click();settled();assert len(evidence['requests'])==count;assert reconcile('return without implicit request',sid)==after
        passed('view round trip preserves GET rows and creates no implicit API calls')
        records().locator('li details > summary').click();expect(records().locator('li code').first).to_have_text(before[0]['action_id']);expect(records().locator('li code').first).to_be_visible()
        for width in [390,320,768,1440]:
            page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert records().locator('.stored-answer').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')>=16
            if width==390:records().screenshot(path=str(a.output/'records-mobile.jpg'),type='jpeg',quality=90)
        passed('actual answer text, ID details and controls fit 320/390/768/1440 widths')
        page.reload(wait_until='networkidle');expect(records()).to_contain_text('조회 전');expect(page.get_by_test_id('case-restored')).to_be_visible()
        query();reconcile('explicit GET after historical browser restoration',sid)
        passed('reload labels historical POST evidence and does not pretend to restore fresh GET results')
        # Actual commit with a deliberately lost browser response.
        page.get_by_test_id('case-reset').click()
        for n in range(1,5):next_step(n)
        lost=[]
        def lose(route):
            response=route.fetch();assert response.status==200;lost.append({'key':route.request.post_data_json,'response':response.json()});route.abort()
        page.route('**/evidence/receipts/*/execute',lose);page.get_by_test_id('case-next').click();expect(page.get_by_test_id('case-status')).to_have_attribute('role','alert');expect(page.get_by_test_id('case-next')).to_be_enabled();settled()
        expect(records()).to_contain_text('기록 요청 응답 미확인');expect(records()).to_contain_text('저장된 답변은 확인')
        sid2=snapshot()['session'];rows=reconcile('lost POST response, GET confirms actual save',sid2);assert rows[0]['action_id']==lost[0]['response']['action_id'];assert snapshot()['action'] is None
        page.unroute('**/evidence/receipts/*/execute');next_step(5);assert snapshot()['action']['replayed'];assert reconcile('same key resolves lost response',sid2)==rows
        evidence['lost_response']=lost
        passed('lost POST response is not called save failure or POST success; GET reconciles actual commit; original key retry returns it')
        # An old session GET must never populate a newly reset workspace.
        held=[];page.route('**/evidence/actions',lambda r:held.append(r));records().get_by_role('button',name='서버 기록 조회').click();expect(records()).to_have_attribute('aria-busy','true')
        page.get_by_test_id('case-reset').click();held[0].fulfill(status=200,content_type='application/json',body=json.dumps({'actions':rows}));page.unroute('**/evidence/actions');expect(records()).to_contain_text('조회 전');expect(records().locator('li')).to_have_count(0)
        passed('late GET from the previous session cannot populate the reset workspace')
        page.get_by_role('button',name='직접 구성',exact=True).click();page.get_by_role('button',name='실험 시작',exact=True).click();page.get_by_test_id('evidence-ready').wait_for();settled();expect(records()).to_contain_text('0개 작업')
        page.get_by_role('button',name='답변 준비',exact=True).click();page.get_by_test_id('evidence-output').wait_for();output=page.get_by_test_id('evidence-output').text_content()
        pair=page.get_by_test_id('source-comparison').filter(visible=True);pair.locator(':scope > summary').click()
        cited=pair.get_by_test_id('cited-source').text_content()
        page.get_by_label('근거 문서',exact=True).select_option('refund')
        expect(pair.get_by_test_id('current-source')).to_have_text(cited)
        page.get_by_label('근거 문서',exact=True).select_option('transfer')
        page.get_by_role('button',name='이 답변으로 작업 기록',exact=True).click();expect(page.get_by_role('button',name='같은 요청 재시도',exact=True)).to_be_enabled();settled()
        execution=page.get_by_test_id('custom-execution');detail=json.loads(execution.locator('pre').text_content());aid=detail['last_success']['action_id'];assert records().locator('li').get_attribute('data-action-id')==aid;assert records().locator('.stored-answer').text_content()==output
        custom_sid=next(r['url'].split('/sessions/')[1].split('/')[0] for r in reversed(evidence['requests']) if r['url'].endswith('/execute'))
        custom_before=reconcile('custom saved answer',custom_sid);page.get_by_role('button',name='같은 요청 재시도',exact=True).click();expect(page.get_by_role('button',name='같은 요청 재시도',exact=True)).to_be_enabled();assert reconcile('custom same-key retry',custom_sid)==custom_before;expect(records()).to_contain_text('추가된 기록 0건')
        page.locator('.el-workbench').screenshot(path=str(a.output/'custom.jpg'),type='jpeg',quality=85)
        page.set_viewport_size({'width':390,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert records().locator('.stored-answer').is_visible()
        page.get_by_role('button',name='답변 준비',exact=True).click();expect(page.get_by_role('button',name='답변 준비',exact=True)).to_be_enabled();expect(records().get_by_test_id('record-confirmation')).to_have_count(0);assert reconcile('new draft preserves old server rows but clears old request summary',custom_sid)==custom_before
        passed('custom workspace uses the same full answer / GET count / action-ID semantics with its own isolated session and mobile layout')
        assert not errors; evidence['page_errors']=errors;b.close()
    (a.output/'results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
