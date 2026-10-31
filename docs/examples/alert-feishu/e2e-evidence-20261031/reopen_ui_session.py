#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read-only discovery of the UI path for reopening the captured alert session."""
import json,sys,re
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from playwright.sync_api import sync_playwright,TimeoutError as PWTimeout,expect
from browser_access import CHROME
from probe_access import BASE,read_ui_credentials
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'reopened-session-attempt2';OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=CHROME);c=b.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100});page=c.new_page()
 page.route('**/api/openclaw/chat/stream',lambda r:r.abort())
 responses=[];page.on('response',lambda r:responses.append({'path':urlparse(r.url).path,'status':r.status}))
 page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
 try:page.wait_for_load_state('networkidle',timeout=10000)
 except PWTimeout:pass
 page.get_by_role('button',name='Conversations',exact=True).first.click()
 entry=page.get_by_role('button',name=re.compile('Alert Alertmanager 1bdae10de10f472e'));entry.focus();entry.press('Enter')
 page.wait_for_timeout(2000)
 expect(page.get_by_text('MOSAIC 注入式工作负载故障（MosaicInjectedWorkloadFailure）修正调查报告',exact=False).last).to_be_visible(timeout=60000)
 (OUT/'list.html').write_text(page.content());(OUT/'list.txt').write_text(page.locator('body').inner_text());page.screenshot(path=str(OUT/'list.png'),full_page=True)
 result={'buttons':page.get_by_role('button').all_text_contents(),'inputs':page.locator('input').evaluate_all('els=>els.map(e=>({type:e.type,placeholder:e.placeholder}))'),'responses':responses}
 (OUT/'discovery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'inputFields':result['inputs'],'buttonNamePrefixes':[x[:150] for x in result['buttons'][:30]]},ensure_ascii=False))
 b.close()
