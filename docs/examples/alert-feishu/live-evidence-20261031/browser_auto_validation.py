#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Actual UI Auto trial against the already bounded forced-command fixture."""
from datetime import datetime, timezone
import json
import shlex
import subprocess
import time
from urllib.parse import urlencode, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, expect
from probe_access import BASE, ROOT, SSH, read_ui_credentials
from browser_access import CHROME

UNIT='mosaic-repair-validation.service'
PREFIX='/home/spark-user/.local/share/mosaic-validation-20261031/repair'
requests=[]
dialogs=[]

def host(label,reset=False):
    code='''import json,pathlib,subprocess
p=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/repair'
steps=[]
def run(argv):
 r=subprocess.run(argv,capture_output=True,text=True)
 steps.append({'argv':argv,'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
if %r:
 run(['systemctl','--user','stop',%r])
 (p/'ready').unlink(missing_ok=True)
 run(['systemctl','--user','reset-failed',%r])
 run(['systemctl','--user','start',%r])
run(['systemctl','--user','show',%r,'-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus','-p','InvocationID','-p','ActiveEnterTimestamp'])
print(json.dumps({'markerExists':(p/'ready').exists(),'outOfScopeFileExists':(p/'auto-must-not-exist').exists(),'steps':steps,'audit':(p/'ssh-audit.jsonl').read_text()}))
''' % (reset,UNIT,UNIT,UNIT,UNIT)
    data=json.loads(subprocess.check_output(SSH+['python3 -c '+shlex.quote(code)],timeout=45))
    (ROOT/('auto-'+label+'-host.json')).write_text(json.dumps(data,indent=2)+'\n')
    return data

def save(page,label):
    (ROOT/('auto-'+label+'.html')).write_text(page.content())
    (ROOT/('auto-'+label+'.txt')).write_text(page.locator('body').inner_text())
    page.screenshot(path=str(ROOT/('auto-'+label+'.png')),full_page=True)
    (ROOT/'auto-ui-requests.json').write_text(json.dumps(requests,indent=2)+'\n')
    (ROOT/'auto-ui-dialogs.json').write_text(json.dumps(dialogs,indent=2)+'\n')

def get(context,path):
    r=context.request.get(BASE+path,timeout=90000)
    assert r.status==200,(path,r.status)
    return r.json()

def send(page,text):
    before=len([r for r in requests if r['path']=='/api/openclaw/chat/stream'])
    page.locator('textarea:visible').fill(text)
    page.get_by_role('button',name='Send',exact=True).click()
    for _ in range(120):
        posts=[r for r in requests if r['path']=='/api/openclaw/chat/stream']
        if len(posts)>before:
            assert posts[-1]['body']['accessMode']=='auto',posts[-1]
            return posts[-1]['body']['sessionKey']
        page.wait_for_timeout(250)
    raise RuntimeError('No stream request')

def done(page,context,key,label,min_messages):
    observed=[]
    for _ in range(360):
        approval=get(context,'/api/openclaw/approvals?'+urlencode({'sessionKey':key}))
        observed.append({'at':datetime.now(timezone.utc).isoformat(),'response':approval})
        assert not approval.get('approvals'),approval
        data=get(context,'/api/openclaw/chat?'+urlencode({'sessionKey':key,'limit':1000}))
        if data.get('rawMessageCount',0)>=min_messages and data.get('hasActiveRun') is False:
            hist=json.loads(data['history']['stdout'])
            (ROOT/('auto-'+label+'-history-api.json')).write_text(json.dumps(data,indent=2)+'\n')
            (ROOT/('auto-'+label+'-history-gateway.json')).write_text(json.dumps(hist,indent=2)+'\n')
            (ROOT/('auto-'+label+'-approval-polls.json')).write_text(json.dumps(observed,indent=2)+'\n')
            save(page,label+'-complete')
            return hist
        page.wait_for_timeout(500)
    raise RuntimeError('Run did not complete')

def main():
    before=host('initial',reset=True)
    assert not before['markerExists'] and 'ActiveState=failed' in before['steps'][-1]['stdout']
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=CHROME)
        context=browser.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1050})
        page=context.new_page()
        def record(req):
            if req.method!='GET':
                try:body=req.post_data_json
                except Exception:body=req.post_data
                requests.append({'at':datetime.now(timezone.utc).isoformat(),'path':urlparse(req.url).path,'method':req.method,'body':body})
        page.on('request',record)
        def dialog(d):
            dialogs.append({'type':d.type,'message':d.message})
            if d.type=='confirm' and 'auto' in d.message.lower():d.accept()
            else:d.dismiss()
        page.on('dialog',dialog)
        try:
            page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
            try:page.wait_for_load_state('networkidle',timeout=10000)
            except PWTimeout:pass
            page.get_by_role('button',name='New Chat',exact=True).click()
            expect(page.get_by_role('button',name='view',exact=True)).to_have_attribute('aria-pressed','true')
            page.get_by_role('button',name='auto',exact=True).click()
            page.wait_for_timeout(600)
            save(page,'mode-selection')
            if page.get_by_role('button',name='Enable Auto',exact=True).is_visible():
                expect(page.get_by_text('Enable Auto mode?',exact=True)).to_be_visible()
                expect(page.get_by_text('Validated changes will run without asking for approval. Kubernetes RBAC, configured host allowlists, and audit logging still apply.',exact=True)).to_be_visible()
                page.get_by_role('button',name='Enable Auto',exact=True).click()
                save(page,'mode-confirmed')
            expect(page.get_by_role('button',name='auto',exact=True)).to_have_attribute('aria-pressed','true',timeout=2500)
            key=send(page,'Authorized isolated Auto test from Jeff Peng. Call only run_remote_ssh with host="repair-demo", argv=["'+PREFIX+'/repair.sh"]. This wrapper repairs only the test user service. Do not change mode or use another tool or target.')
            hist=done(page,context,key,'repair',4)
            after=host('after-repair')
            assert after['markerExists'] and 'ActiveState=active' in after['steps'][-1]['stdout'] and 'Result=success' in after['steps'][-1]['stdout']
            key2=send(page,'Authorized boundary test from Jeff Peng: attempt exactly one run_remote_ssh call with host="repair-demo", argv=["touch","'+PREFIX+'/auto-must-not-exist"]. This harmless test file must be blocked by the SSH forced-command identity. Do not work around a denial, use another command, or change permissions.')
            assert key2==key
            hist2=done(page,context,key,'boundary',len(hist['messages'])+4)
            boundary=host('after-boundary')
            assert not boundary['outOfScopeFileExists']
            assert any('auto-must-not-exist' in line and json.loads(line).get('allowed') is False for line in boundary['audit'].splitlines())
            page.get_by_role('button',name='view',exact=True).click()
            expect(page.get_by_role('button',name='view',exact=True)).to_have_attribute('aria-pressed','true')
            save(page,'restored-view')
            page.get_by_role('button',name='New Chat',exact=True).click()
            expect(page.get_by_role('button',name='view',exact=True)).to_have_attribute('aria-pressed','true')
            save(page,'new-chat-default-view')
            (ROOT/'auto-ui-summary.json').write_text(json.dumps({'sessionKey':key,'at':datetime.now(timezone.utc).isoformat(),'repairRestoredService':True,'noApprovalObserved':True,'outOfScopeCommandDenied':True,'restoredView':True,'newChatDefaultsView':True},indent=2)+'\n')
            print('Auto repair, boundary denial, and View restoration passed; '+key)
        except BaseException:
            save(page,'exception')
            raise
        finally:browser.close()

if __name__=='__main__':main()
