#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Resolve only this test's UI cards after both actual sources are confirmed clear."""
import json,sys
from pathlib import Path
from urllib.parse import urlparse,urlencode
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from playwright.sync_api import sync_playwright,expect,TimeoutError as PWTimeout
from browser_access import CHROME
from gpu_access import BASE,read_ui_credentials
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'ui-cleanup';OUT.mkdir(exist_ok=True)
final=json.loads((ROOT/'related-cleared.json').read_text())
assert all(not (json.loads(r['body']) if r['name']=='alertmanager' else json.loads(r['body'])['data']['result']) for r in final['remote'])
posts=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=CHROME);c=b.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100});page=c.new_page()
 page.route('**/api/openclaw/chat/stream',lambda r:r.abort())
 page.on('dialog',lambda d:d.accept())
 def rec(req):
  if req.method not in ['GET','HEAD']:
   try:body=req.post_data_json
   except Exception:body=req.post_data
   posts.append({'path':urlparse(req.url).path,'method':req.method,'body':body})
 page.on('request',rec)
 page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
 try:page.wait_for_load_state('networkidle',timeout=10000)
 except PWTimeout:pass
 before=c.request.get(BASE+'/api/alerts').json();selected=[a for a in before['alerts'] if ROOT.name in json.dumps(a)]
 assert {x['fingerprint'] for x in selected}=={'9d039033924e9122','d1e25281f02cec92'}
 for x in selected:assert x['labels']['namespace']=='mosaic-gpu-rca-20261031t121240z' and x['labels']['pod']=='gpu-telemetry-fixture'
 (OUT/'before.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
 for severity in ['info','warning']:
  card=page.locator('.mosaic-alert-slide-in').filter(has_text=ROOT.name).filter(has_text='MosaicGpuTelemetrySimulation').filter(has_text='severity='+severity)
  expect(card).to_have_count(1,timeout=60000)
  button=card.get_by_role('button',name='Resolve',exact=True);button.focus();button.press('Enter');page.wait_for_timeout(500)
 page.wait_for_timeout(1500)
 after=c.request.get(BASE+'/api/alerts').json();remaining=[a for a in after['alerts'] if ROOT.name in json.dumps(a)]
 (OUT/'after.json').write_text(json.dumps(remaining,ensure_ascii=False,indent=2)+'\n')
 (OUT/'after.html').write_text(page.content());(OUT/'after.txt').write_text(page.locator('body').inner_text());page.screenshot(path=str(OUT/'after.png'),full_page=True)
 key='agent:default:alert-alertmanager-d1e25281f02cec92';r=c.request.get(BASE+'/api/openclaw/chat?'+urlencode({'sessionKey':key,'limit':1000}));history=r.json();assert r.status==200 and history['rawMessageCount']==41 and history['hasActiveRun'] is False
 (OUT/'retained-history-api.json').write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n')
 (OUT/'posts.json').write_text(json.dumps(posts,ensure_ascii=False,indent=2)+'\n')
 result={'resolvedFingerprints':[x['fingerprint'] for x in selected],'remainingRelated':len(remaining),'retainedMessages':history['rawMessageCount'],'sourceClearVerifiedBeforeUiResolve':True,'allPosts':posts}
 (OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result),flush=True)
 b.close()
