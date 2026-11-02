#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Observe real browser request paths/stream types without initiating chats."""
import json,sys
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'live-validation-20261031'))
from playwright.sync_api import sync_playwright,expect,TimeoutError as PWTimeout
from browser_access import CHROME
from probe_access import BASE,read_ui_credentials
ROOT=Path(__file__).resolve().parent
records=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path=CHROME)
 context=browser.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100})
 page=context.new_page()
 def block(route):
  records.append({'event':'blocked-unrequested-chat','path':urlparse(route.request.url).path});route.abort()
 page.route('**/api/openclaw/chat/stream',block)
 page.on('request',lambda request:records.append({'event':'request','at':datetime.now(timezone.utc).isoformat(),'path':urlparse(request.url).path,'method':request.method,'resourceType':request.resource_type}))
 page.on('response',lambda response:records.append({'event':'response','at':datetime.now(timezone.utc).isoformat(),'path':urlparse(response.url).path,'status':response.status,'contentType':response.headers.get('content-type')}))
 cdp=context.new_cdp_session(page);cdp.send('Network.enable')
 cdp.on('Network.eventSourceMessageReceived',lambda e:records.append({'event':'eventSource','data':e}))
 try:
  page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
  try:page.wait_for_load_state('networkidle',timeout=10000)
  except PWTimeout:pass
  expect(page.get_by_role('button',name='view',exact=True)).to_be_visible(timeout=90000)
  page.wait_for_timeout(4000)
  (ROOT/'network-observation.html').write_text(page.content())
  (ROOT/'network-observation.txt').write_text(page.locator('body').inner_text())
  page.screenshot(path=str(ROOT/'network-observation.png'),full_page=True)
 finally:
  (ROOT/'network-observation.private.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
  browser.close()
print(json.dumps([x for x in records if x.get('path','').startswith('/api/')],ensure_ascii=False))
