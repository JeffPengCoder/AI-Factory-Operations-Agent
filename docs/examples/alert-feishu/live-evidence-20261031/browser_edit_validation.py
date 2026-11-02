#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Actual UI Edit denial/approval for one forced-command user-service fixture."""
from datetime import datetime, timezone
import json
import re
import subprocess
import time
from urllib.parse import urlencode, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, expect
from probe_access import BASE, ROOT, SSH, read_ui_credentials
from browser_access import CHROME

WRAPPER='/home/spark-user/.local/share/mosaic-validation-20261031/repair/repair.sh'
UNIT='mosaic-repair-validation.service'
requests=[]

def host_state(label):
    code='import json,subprocess,pathlib; p=pathlib.Path.home()/".local/share/mosaic-validation-20261031/repair"; s=subprocess.run(["systemctl","--user","show","'+UNIT+'","-p","ActiveState","-p","SubState","-p","Result","-p","ExecMainStatus","-p","InvocationID","-p","ActiveEnterTimestamp"],capture_output=True,text=True); print(json.dumps({"markerExists":(p/"ready").exists(),"state":s.stdout,"audit":(p/"ssh-audit.jsonl").read_text()}))'
    import shlex
    result=json.loads(subprocess.check_output(SSH+['python3 -c '+shlex.quote(code)]))
    (ROOT/('edit-'+label+'-host.json')).write_text(json.dumps(result,indent=2)+'\n')
    return result

def save(page,label):
    (ROOT/('edit-'+label+'.html')).write_text(page.content())
    (ROOT/('edit-'+label+'.txt')).write_text(page.locator('body').inner_text())
    page.screenshot(path=str(ROOT/('edit-'+label+'.png')),full_page=True)
    (ROOT/'edit-ui-requests.json').write_text(json.dumps(requests,indent=2)+'\n')

def api(context,path):
    r=context.request.get(BASE+path,timeout=90000)
    assert r.status==200,(path,r.status)
    return r.json()

def wait_approval(page,context,session_key,label):
    for _ in range(180):
        data=api(context,'/api/openclaw/approvals?'+urlencode({'sessionKey':session_key}))
        matches=[x for x in data.get('approvals',[]) if x.get('request',{}).get('toolName')=='run_remote_ssh' and 'repair.sh' in x.get('request',{}).get('description','')]
        if matches:
            assert len(matches)==1,data
            assert 'repair-demo' in matches[0]['request']['description']
            (ROOT/('edit-'+label+'-approval.json')).write_text(json.dumps(data,indent=2)+'\n')
            save(page,label+'-pending')
            return matches[0]
        page.wait_for_timeout(500)
    save(page,label+'-missing-approval')
    raise RuntimeError('No matching approval card')

def wait_done(page,context,session_key,label):
    for _ in range(360):
        d=api(context,'/api/openclaw/chat?'+urlencode({'sessionKey':session_key,'limit':1000}))
        if d.get('rawMessageCount',0)>=3 and d.get('hasActiveRun') is False:
            (ROOT/('edit-'+label+'-history-api.json')).write_text(json.dumps(d,indent=2)+'\n')
            h=json.loads(d['history']['stdout'])
            (ROOT/('edit-'+label+'-history-gateway.json')).write_text(json.dumps(h,indent=2)+'\n')
            save(page,label+'-complete')
            return h
        page.wait_for_timeout(500)
    raise RuntimeError('Chat did not finish')

def send(page,text):
    before=len([x for x in requests if x['path']=='/api/openclaw/chat/stream'])
    page.locator('textarea:visible').fill(text)
    page.get_by_role('button',name='Send',exact=True).click()
    for _ in range(80):
        posts=[x for x in requests if x['path']=='/api/openclaw/chat/stream']
        if len(posts)>before:return posts[-1]['body']['sessionKey']
        page.wait_for_timeout(250)
    raise RuntimeError('No chat request observed')

def main():
    credentials=read_ui_credentials()
    before=host_state('initial')
    assert not before['markerExists'] and 'ActiveState=failed' in before['state']
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=CHROME)
        context=browser.new_context(http_credentials=credentials,viewport={'width':1500,'height':1050})
        page=context.new_page()
        def record(req):
            if req.method!='GET':
                try:body=req.post_data_json
                except Exception:body=req.post_data
                requests.append({'at':datetime.now(timezone.utc).isoformat(),'path':urlparse(req.url).path,'method':req.method,'body':body})
        page.on('request',record)
        page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
        try:page.wait_for_load_state('networkidle',timeout=10000)
        except PWTimeout:pass
        save(page,'before-new-chat')
        page.get_by_role('button',name='New Chat',exact=True).click()
        page.wait_for_timeout(700)
        expect(page.get_by_role('button',name='view',exact=True)).to_have_attribute('aria-pressed','true')
        page.get_by_role('button',name='edit',exact=True).click()
        expect(page.get_by_role('button',name='edit',exact=True)).to_have_attribute('aria-pressed','true')
        save(page,'selected')
        key=send(page,'Authorized isolated test from Jeff Peng. Use only run_remote_ssh with host="repair-demo", argv=["'+WRAPPER+'"]. Submit the exact request and await approval. Do not change mode, use another tool, or touch another service.')
        approval=wait_approval(page,context,key,'deny')
        assert not host_state('before-deny')['markerExists']
        deny=page.get_by_role('button',name=re.compile(r'^(Deny|Reject|Decline)\b',re.I))
        assert deny.count()==1, page.get_by_role('button').all_text_contents()
        deny.click()
        wait_done(page,context,key,'denied')
        assert not host_state('after-deny')['markerExists']
        key2=send(page,'I now authorize a new request for the same isolated fixture. Call run_remote_ssh exactly with host="repair-demo", argv=["'+WRAPPER+'"], and wait for a new approval. Do not use another tool or target.')
        assert key2==key
        approval2=wait_approval(page,context,key,'approve')
        assert approval2['id']!=approval['id']
        assert not host_state('before-approve')['markerExists']
        approve=page.get_by_role('button',name=re.compile(r'^(Approve|Allow)\b',re.I))
        assert approve.count()==1,page.get_by_role('button').all_text_contents()
        approve.click()
        wait_done(page,context,key,'approved')
        after=host_state('after-approve')
        assert after['markerExists'] and 'ActiveState=active' in after['state'] and 'Result=success' in after['state']
        (ROOT/'edit-ui-summary.json').write_text(json.dumps({'sessionKey':key,'denyApprovalId':approval['id'],'approveApprovalId':approval2['id'],'denyKeptFailed':True,'approveRestoredService':True,'at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
        print('Edit UI denial and approval passed; '+key)
        browser.close()

if __name__=='__main__':
    main()
