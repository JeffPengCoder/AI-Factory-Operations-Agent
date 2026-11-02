#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read the real Audit UI after the bounded repair trials."""
import json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,TimeoutError as PWTimeout
from probe_access import ROOT,BASE,read_ui_credentials
from browser_access import CHROME

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=CHROME)
    context=browser.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100})
    page=context.new_page()
    responses=[]
    def response(r):
        path=urlparse(r.url).path
        if 'audit' in path and '/api/' in path:
            try:body=r.json()
            except Exception:body=r.text()
            responses.append({'path':path,'status':r.status,'body':body})
    page.on('response',response)
    page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
    try:page.wait_for_load_state('networkidle',timeout=10000)
    except PWTimeout:pass
    page.get_by_role('button',name='Audit',exact=True).first.click()
    page.wait_for_timeout(3000)
    (ROOT/'audit-ui.html').write_text(page.content())
    (ROOT/'audit-ui.txt').write_text(page.locator('body').inner_text())
    page.screenshot(path=str(ROOT/'audit-ui.png'),full_page=True)
    (ROOT/'audit-ui-api.json').write_text(json.dumps(responses,indent=2)+'\n')
    print(json.dumps({'auditResponses':[{'path':x['path'],'status':x['status']} for x in responses],'bodyCharacters':len(page.locator('body').inner_text())}))
    browser.close()
