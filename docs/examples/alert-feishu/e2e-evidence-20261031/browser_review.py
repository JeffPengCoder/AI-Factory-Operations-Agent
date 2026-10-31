#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Record a transparent operator correction in the same existing alert session."""
from datetime import datetime,timezone
import json,sys,time
from pathlib import Path
from urllib.parse import urlencode,urlparse
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from playwright.sync_api import sync_playwright,expect,TimeoutError as PWTimeout
from browser_access import CHROME
from probe_access import BASE,read_ui_credentials
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'review';OUT.mkdir(exist_ok=True)
summary=json.loads((ROOT/'browser/summary.json').read_text());KEY=summary['sessionKey']
expr=json.loads((ROOT/'isolated-error-fixture.applied-input.json').read_text())['items'][3]['spec']['groups'][0]['rules'][0]['expr']
prompt=f'''Operator evidence review for the SAME alert {summary['fingerprint']}, run {ROOT.name}. Keep View mode. The prior report and IRAOP answer contain factual overreach that must remain in history and be corrected explicitly:
1. The ACTUAL new PrometheusRule is mosaic-e2e-20261031t075722z, UID 0faf5f01-a21e-439f-b4f6-c6da8d5c219d, expression {expr}, for10s, evaluation interval10s. Independent recorded Prometheus samples show pending then firing; Alertmanager and MOSAIC share fingerprint1bdae10de10f472e. This was NOT a vector(1) rule and was NOT posted directly to Alertmanager. The PDF's separate descriptions of those older injection methods do not describe this run.
2. 82953a81-6578-4cbe-b638-ef3de927279a is the POD UID, not an Alert UID. Do not mix those identifiers.
3. /fixture is a read-only ConfigMap mount. touch /fixture/ready inside the container is inapplicable. Current verified deployment enables SSH-only Edit; Kubernetes write backend is disabled. Merely selecting Edit/Auto cannot grant Kubernetes patch permission. Do not attempt any write or mode change.
4. The PDF does not contain this unique Pod/namespace/run ID, exit23 implementation, fixture-input ConfigMap or literal REQUIRED_FILE_MISSING. Those facts came from the supplied context and live Kubernetes tools. Never cite the PDF as if it specified the exact implementation. The original IRAOP answers incorrectly made that attribution.
5. Node health conditions are limited observations, not a comprehensive GPU diagnosis. State that no GPU fault was injected and current evidence establishes this fixture's startup failure; do not certify all GPUs healthy.
Call iraop_query ONCE with depth quick, collections [mosaic-validation-20261031], using a document-only question: retrieve the actual general instructions in mosaic-validation-control.pdf about reading service state/logs before repair, automatic investigations being read-only, and required completion evidence. Cite file/pages. Ask it to distinguish generic source passages from an external new Kubernetes example; do not ask it to diagnose the current Pod or claim the document contains that Pod implementation. The source may discuss old vector(1)/direct Alertmanager examples; label those as different examples.
Then produce a complete corrected Chinese report, preserving run ID/fingerprint/Pod UID/session key, the actual rule expression, observed log lines/exit23/ConfigMap evidence and current toolCallIds; distinguish live facts versus PDF guidance; explicitly correct the above errors, list original failed kubectl --timeout command, and state no repair/no Feishu send was executed by this agent. Keep it suitable for operator review and later group delivery. Do not hide earlier drafts or failures.'''
(OUT/'prompt.txt').write_text(prompt+'\n')
posts=[]
def save(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=CHROME);c=b.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100});page=c.new_page()
 def record(req):
  if req.method=='POST' and urlparse(req.url).path=='/api/openclaw/chat/stream':posts.append({'at':datetime.now(timezone.utc).isoformat(),'body':req.post_data_json})
 page.on('request',record)
 def shot(n):
  (OUT/(n+'.html')).write_text(page.content());(OUT/(n+'.txt')).write_text(page.locator('body').inner_text());page.screenshot(path=str(OUT/(n+'.png')),full_page=True)
 try:
  page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
  try:page.wait_for_load_state('networkidle',timeout=10000)
  except PWTimeout:pass
  card=page.locator('.mosaic-alert-slide-in').filter(has_text='MosaicInjectedWorkloadFailure')
  expect(card).to_have_count(1,timeout=90000);card.get_by_role('button',name='Open Chat',exact=True).click()
  text=page.locator('textarea:visible').last;expect(text).to_be_visible(timeout=60000);shot('before')
  text.fill(prompt);page.get_by_role('button',name='Send',exact=True).last.click()
  for _ in range(120):
   if posts:break
   page.wait_for_timeout(250)
  assert len(posts)==1 and posts[0]['body']['sessionKey']==KEY and posts[0]['body'].get('accessMode','view')=='view'
  started=time.monotonic();polls=[]
  for _ in range(900):
   r=c.request.get(BASE+'/api/openclaw/chat?'+urlencode({'sessionKey':KEY,'limit':1000}),timeout=90000);assert r.status==200
   d=r.json();polls.append({'at':datetime.now(timezone.utc).isoformat(),'rawMessageCount':d.get('rawMessageCount'),'hasActiveRun':d.get('hasActiveRun')})
   if d.get('rawMessageCount',0)>summary['messages']+1 and d.get('hasActiveRun') is False:break
   page.wait_for_timeout(500)
  else:raise RuntimeError('Review did not finish')
  h=json.loads(d['history']['stdout']);save('history-api.json',d);save('history-gateway.json',h);save('polls.json',polls);shot('after')
  answer=''.join(x.get('text','') for x in h['messages'][-1].get('content',[]) if x.get('type')=='text')
  (OUT/'model-corrected-report.zh-CN.txt').write_text(answer+'\n')
  save('summary.json',{'at':datetime.now(timezone.utc).isoformat(),'sessionKey':KEY,'sessionId':h['sessionId'],'messages':len(h['messages']),'elapsedSeconds':time.monotonic()-started,'newResearchCalls':sum(x.get('role')=='toolResult' and x.get('toolName')=='iraop_query' for x in h['messages'][summary['messages']:]),'operatorCorrectionsProvided':True})
  print(json.dumps({'completed':True,'messages':len(h['messages']),'elapsedSeconds':time.monotonic()-started}),flush=True)
 finally:
  save('posts.json',posts);b.close()
