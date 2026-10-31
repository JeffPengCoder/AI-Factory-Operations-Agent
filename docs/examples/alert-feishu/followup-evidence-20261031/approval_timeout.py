#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Actual UI approval expiry against the existing isolated user-service fixture."""
from datetime import datetime,timezone
import json,re,shlex,subprocess,sys,time
from pathlib import Path
from urllib.parse import urlencode,urlparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'live-validation-20261031'))
from probe_access import BASE,SSH,read_ui_credentials
from browser_access import CHROME
from playwright.sync_api import sync_playwright,TimeoutError as PWTimeout,expect

ROOT=Path(__file__).resolve().parent/'approval-timeout';ROOT.mkdir(exist_ok=True)
UNIT='mosaic-repair-validation.service'
WRAPPER='/home/spark-user/.local/share/mosaic-validation-20261031/repair/repair.sh'
requests=[]

def host(label,action='read'):
    code='''import json,pathlib,subprocess
p=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/repair'
steps=[]
def run(argv):
 r=subprocess.run(argv,capture_output=True,text=True);steps.append({'argv':argv,'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
action=%r
if action=='reset':
 run(['systemctl','--user','stop',%r]);(p/'ready').unlink(missing_ok=True)
 run(['systemctl','--user','reset-failed',%r]);run(['systemctl','--user','start',%r])
if action=='restore':run([str(p/'repair.sh')])
run(['systemctl','--user','show',%r,'-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus','-p','InvocationID','-p','ActiveEnterTimestamp'])
print(json.dumps({'action':action,'markerExists':(p/'ready').exists(),'steps':steps,'sshAudit':(p/'ssh-audit.jsonl').read_text()}))
''' % (action,UNIT,UNIT,UNIT,UNIT)
    data=json.loads(subprocess.check_output(SSH+['python3 -c '+shlex.quote(code)],timeout=60))
    (ROOT/(label+'-host.json')).write_text(json.dumps(data,indent=2)+'\n')
    return data

def save(page,label):
    (ROOT/(label+'.html')).write_text(page.content());(ROOT/(label+'.txt')).write_text(page.locator('body').inner_text())
    page.screenshot(path=str(ROOT/(label+'.png')),full_page=True)
    (ROOT/'ui-requests.json').write_text(json.dumps(requests,indent=2)+'\n')

def main():
    original=host('before-test')
    assert original['markerExists'] and 'ActiveState=active' in original['steps'][-1]['stdout']
    before=host('reset','reset')
    assert not before['markerExists'] and 'ActiveState=failed' in before['steps'][-1]['stdout']
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=CHROME)
            context=browser.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1050})
            page=context.new_page()
            def get(path):
                r=context.request.get(BASE+path,timeout=90000);assert r.status==200,(path,r.status);return r.json()
            def record(req):
                if req.method!='GET':
                    try:body=req.post_data_json
                    except Exception:body=req.post_data
                    requests.append({'at':datetime.now(timezone.utc).isoformat(),'path':urlparse(req.url).path,'method':req.method,'body':body})
            page.on('request',record)
            try:
                page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
                try:page.wait_for_load_state('networkidle',timeout=10000)
                except PWTimeout:pass
                page.get_by_role('button',name='New Chat',exact=True).click()
                expect(page.get_by_role('button',name='view',exact=True)).to_have_attribute('aria-pressed','true')
                page.get_by_role('button',name='edit',exact=True).click()
                expect(page.get_by_role('button',name='edit',exact=True)).to_have_attribute('aria-pressed','true')
                page.locator('textarea:visible').fill('test from Jeff Peng: isolated approval EXPIRY test. Call only run_remote_ssh with host="repair-demo", argv=["'+WRAPPER+'"]. Submit once and wait for the approval. I will deliberately leave it unanswered to verify the configured timeout; do not retry, use another tool, or change mode.')
                page.get_by_role('button',name='Send',exact=True).click()
                for _ in range(120):
                    posts=[r for r in requests if r['path']=='/api/openclaw/chat/stream']
                    if posts:break
                    page.wait_for_timeout(250)
                assert len(posts)==1
                key=posts[0]['body']['sessionKey'];assert posts[0]['body']['accessMode']=='edit'
                for _ in range(180):
                    data=get('/api/openclaw/approvals?'+urlencode({'sessionKey':key}))
                    matches=[a for a in data.get('approvals',[]) if a.get('request',{}).get('toolName')=='run_remote_ssh' and 'repair.sh' in a.get('request',{}).get('description','')]
                    if matches:break
                    page.wait_for_timeout(500)
                assert len(matches)==1,data
                approval=matches[0];assert 'repair-demo' in approval['request']['description']
                (ROOT/'pending-approval.json').write_text(json.dumps(data,indent=2)+'\n')
                save(page,'pending')
                pending=host('while-pending');assert not pending['markerExists']
                observed=time.monotonic();polls=[]
                for _ in range(180):
                    data=get('/api/openclaw/chat?'+urlencode({'sessionKey':key,'limit':1000}))
                    polls.append({'at':datetime.now(timezone.utc).isoformat(),'hasActiveRun':data.get('hasActiveRun'),'rawMessageCount':data.get('rawMessageCount')})
                    if data.get('rawMessageCount',0)>=4 and data.get('hasActiveRun') is False:break
                    page.wait_for_timeout(1000)
                assert data.get('hasActiveRun') is False
                elapsed=time.monotonic()-observed
                history=json.loads(data['history']['stdout'])
                (ROOT/'history-api.json').write_text(json.dumps(data,indent=2)+'\n')
                (ROOT/'history-gateway.json').write_text(json.dumps(history,indent=2)+'\n')
                (ROOT/'completion-polls.json').write_text(json.dumps(polls,indent=2)+'\n')
                results=[m for m in history['messages'] if m.get('role')=='toolResult']
                assert len(results)==1,results
                assert re.search(r'tim(?:ed?\s*out|eout)',json.dumps(results[0]),re.I),results
                after=host('after-expiry')
                assert not after['markerExists'] and 'ActiveState=failed' in after['steps'][-1]['stdout']
                assert before['sshAudit']==after['sshAudit']
                assert not any('/approvals' in r['path'] for r in requests)
                save(page,'expired')
                page.get_by_role('button',name='view',exact=True).click()
                expect(page.get_by_role('button',name='view',exact=True)).to_have_attribute('aria-pressed','true')
                save(page,'restored-view')
                summary={'at':datetime.now(timezone.utc).isoformat(),'sessionKey':key,'approvalId':approval['id'],'elapsedAfterPendingObservedSeconds':elapsed,'timeoutObserved':True,'noSSHExecution':True,'fixtureStayedFailed':True,'modeRestoredView':True}
                (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
            except BaseException:
                save(page,'exception');raise
            finally:browser.close()
    finally:
        restored=host('maintenance-restored','restore')
        assert restored['markerExists'] and 'ActiveState=active' in restored['steps'][-1]['stdout']
        print('Test controller separately restored its own fixture after the expiry trial.',flush=True)

if __name__=='__main__':main()
