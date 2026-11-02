#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Restore real Alertmanager polling through the visible UI and save all alerts."""
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"live-validation-20261031"))
import json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, expect
from browser_access import CHROME
from probe_access import BASE, read_ui_credentials
ROOT=Path(__file__).resolve().parent/"alerts-restored"
ROOT.mkdir(exist_ok=True)

def main():
    requests=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=CHROME)
        context=browser.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100})
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
        expect(page.get_by_role('switch',name='Auto investigate',exact=True)).to_have_attribute('aria-checked','false')
        pull=page.get_by_role('switch',name='Auto pull',exact=True)
        before=pull.get_attribute('aria-checked')
        if before=='false':pull.click()
        expect(pull).to_have_attribute('aria-checked','true')
        page.get_by_role('button',name='Refresh',exact=True).click()
        page.get_by_text('MosaicSyntheticAlert',exact=False).first.wait_for(timeout=60000)
        page.wait_for_timeout(1000)
        (ROOT/'alerts-pulled.html').write_text(page.content())
        (ROOT/'alerts-pulled.txt').write_text(page.locator('body').inner_text())
        page.screenshot(path=str(ROOT/'alerts-pulled.png'),full_page=True)
        data={}
        for path in ['/api/alerts','/api/alerts/alertmanager','/api/modules']:
            r=context.request.get(BASE+path,timeout=60000)
            data[path]={'status':r.status,'data':r.json()}
        (ROOT/'alerts-pulled-api.private.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        (ROOT/'alerts-pull-ui-requests.json').write_text(json.dumps(requests,ensure_ascii=False,indent=2)+'\n')
        alerts=data['/api/alerts']['data']['alerts']
        selected=[a for a in alerts if a.get('fingerprint')=='0fa8cbd733f54a5a']
        assert len(selected)==1
        (ROOT/'selected-alert-current.json').write_text(json.dumps(selected[0],ensure_ascii=False,indent=2)+'\n')
        assert selected[0]['annotations']['test_from']=='test from Jeff Peng'
        summary={'at':datetime.now(timezone.utc).isoformat(),'autoPullWas':before,'autoPullNow':pull.get_attribute('aria-checked'),'autoInvestigateNow':page.get_by_role('switch',name='Auto investigate',exact=True).get_attribute('aria-checked'),'alertCount':len(alerts),'selectedId':selected[0]['id'],'fingerprint':selected[0]['fingerprint'],'stage':selected[0]['stage']}
        (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary))
        browser.close()

if __name__=='__main__':main()
