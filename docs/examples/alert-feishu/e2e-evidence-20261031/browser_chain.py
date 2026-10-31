#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exercise this new alert's real UI investigation and same-session research."""
from datetime import datetime,timezone
import json,sys,time
from pathlib import Path
from urllib.parse import urlencode,urlparse
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from playwright.sync_api import sync_playwright,expect,TimeoutError as PWTimeout
from browser_access import CHROME
from probe_access import BASE,read_ui_credentials
ROOT=Path(__file__).resolve().parent
RUN=ROOT.name;NS='mosaic-'+RUN
OUT=ROOT/'browser';OUT.mkdir(exist_ok=True)
assert not (OUT/'summary.json').exists()
posts=[];responses=[];polls=[]
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=CHROME)
 context=b.new_context(http_credentials=read_ui_credentials(),viewport={'width':1500,'height':1100})
 context.add_init_script('''window.__e2eStreams=[];const nativeFetch=window.fetch;window.fetch=async function(...args){const r=await nativeFetch.apply(this,args);const input=args[0],u=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,location.href);const type=r.headers.get('content-type')||'';if(type.includes('application/x-ndjson')||type.includes('text/event-stream')){const item={path:u.pathname,status:r.status,contentType:type,chunks:[],finished:false};window.__e2eStreams.push(item);const copy=r.clone();(async()=>{try{const reader=copy.body.getReader(),d=new TextDecoder();while(true){const {done,value}=await reader.read();if(done)break;item.chunks.push(d.decode(value,{stream:true}));}item.chunks.push(d.decode());item.finished=true;}catch(e){item.error=String(e);}})();}return r;};''')
 page=context.new_page()
 def get(path):
  r=context.request.get(BASE+path,timeout=90000);assert r.status==200,(path,r.status);return r.json()
 def record(req):
  if req.method!='GET' and urlparse(req.url).path.startswith('/api/'):
   try:body=req.post_data_json
   except Exception:body=req.post_data
   posts.append({'at':datetime.now(timezone.utc).isoformat(),'path':urlparse(req.url).path,'method':req.method,'body':body})
 page.on('request',record)
 page.on('response',lambda r:responses.append({'at':datetime.now(timezone.utc).isoformat(),'path':urlparse(r.url).path,'status':r.status}))
 def shot(label):
  (OUT/(label+'.html')).write_text(page.content());(OUT/(label+'.txt')).write_text(page.locator('body').inner_text())
  page.screenshot(path=str(OUT/(label+'.png')),full_page=True)
 def wait_run(key,label,minimum):
  started=time.monotonic()
  for _ in range(900):
   data=get('/api/openclaw/chat?'+urlencode({'sessionKey':key,'limit':1000}))
   polls.append({'at':datetime.now(timezone.utc).isoformat(),'phase':label,'rawMessageCount':data.get('rawMessageCount'),'hasActiveRun':data.get('hasActiveRun')})
   if data.get('rawMessageCount',0)>=minimum and data.get('hasActiveRun') is False:
    hist=json.loads(data['history']['stdout']);save(label+'-history-api.json',data);save(label+'-history-gateway.json',hist)
    shot(label+'-complete')
    return data,hist,time.monotonic()-started
   page.wait_for_timeout(500)
  raise RuntimeError(label+' did not finish')
 try:
  page.goto(BASE,wait_until='domcontentloaded',timeout=60000)
  try:page.wait_for_load_state('networkidle',timeout=10000)
  except PWTimeout:pass
  expect(page.get_by_role('switch',name='Auto investigate',exact=True)).to_have_attribute('aria-checked','false',timeout=90000)
  expect(page.get_by_role('switch',name='Auto pull',exact=True)).to_have_attribute('aria-checked','true',timeout=90000)
  shot('before-new-alert')
  for _ in range(600):
   a=get('/api/alerts');selected=[x for x in a.get('alerts',[]) if RUN in json.dumps(x)]
   if selected:
    assert len(selected)==1,selected;alert=selected[0];save('new-alert-before-investigation.json',alert);break
   page.wait_for_timeout(1000)
  else:raise RuntimeError('New run alert was not imported into MOSAIC')
  fingerprint=alert['fingerprint'];key='agent:default:alert-alertmanager-'+fingerprint
  card=page.locator('.mosaic-alert-slide-in').filter(has_text='MosaicInjectedWorkloadFailure')
  expect(card).to_have_count(1,timeout=60000)
  card.screenshot(path=str(OUT/'new-alert-card.png'))
  card.get_by_role('button',name='Start Investigating ❯',exact=True).click()
  for _ in range(120):
   stream_posts=[x for x in posts if x['path']=='/api/openclaw/chat/stream']
   if stream_posts:break
   page.wait_for_timeout(250)
  assert len(stream_posts)==1 and stream_posts[0]['body']['sessionKey']==key
  assert stream_posts[0]['body'].get('accessMode','view')=='view'
  shot('investigation-started')
  first,hist,elapsed=wait_run(key,'initial',3)
  save('initial-summary.json',{'sessionKey':key,'sessionId':hist['sessionId'],'elapsedSeconds':elapsed,'messages':len(hist['messages'])})
  prompt=f'''Continue this SAME alert investigation in View mode. test from Jeff Peng. Run ID {RUN}, fingerprint {fingerprint}. Use the registered cluster target-lab and ONLY namespace {NS}, Pod mosaic-log-fixture, container fixture for workload logs.
Collect fresh evidence with run_kubectl: get this Pod -o json; describe this Pod; logs for fixture --previous --timestamps; current logs --timestamps; get events in this namespace -o json; and get ConfigMap fixture-input -o json. Read node target-node-1 status as useful. Preserve exact tool errors rather than working around authorization. Never read Secrets, exec, change mode, create/patch/delete resources or repair anything.
After collecting the actual logs/status/events, call iraop_query once, depth quick, collections [mosaic-validation-20261031]. Build its question from the observed error and ask for the applicable diagnostic procedure and read-only investigation limits in mosaic-validation-control.pdf (MOSAIC-KB-20261031). The query must include the actual observed error, not a guessed cause. Cite exact filename and page, and distinguish generic runbook advice from direct evidence about this Pod.
Then return one complete Chinese report: run ID/fingerprint; exact observed error lines, termination reason/exit code/restarts and ConfigMap evidence; timeline; knowledge query/answer/sources; root cause and confidence; suggested next actions without execution; all failures and limitations. Do not infer a GPU fault. Do not claim Feishu delivery: an operator will separately send the reviewed report through the configured custom bot. This is a new test alert, not the old synthetic alert.'''
  (OUT/'followup-prompt.txt').write_text(prompt+'\n')
  expect(page.locator('textarea:visible')).to_be_visible(timeout=60000)
  page.locator('textarea:visible').fill(prompt);page.get_by_role('button',name='Send',exact=True).click()
  for _ in range(120):
   stream_posts=[x for x in posts if x['path']=='/api/openclaw/chat/stream']
   if len(stream_posts)>=2:break
   page.wait_for_timeout(250)
  assert len(stream_posts)==2 and stream_posts[1]['body']['sessionKey']==key
  assert stream_posts[1]['body'].get('accessMode','view')=='view'
  final,history,elapsed2=wait_run(key,'evidence-research',first['rawMessageCount']+2)
  tools=[x for x in history['messages'] if x.get('role')=='toolResult']
  research=[x for x in tools if x.get('toolName')=='iraop_query']
  save('selected-alert-after.json',[x for x in get('/api/alerts').get('alerts',[]) if x.get('fingerprint')==fingerprint])
  summary={'at':datetime.now(timezone.utc).isoformat(),'runId':RUN,'fingerprint':fingerprint,'sessionKey':key,'sessionId':history['sessionId'],'initialElapsedSeconds':elapsed,'followupElapsedSeconds':elapsed2,'messages':len(history['messages']),'toolResults':[{'toolCallId':x.get('toolCallId'),'toolName':x.get('toolName'),'isError':x.get('isError')} for x in tools],'researchCalls':len(research),'viewOnly':True}
  save('summary.json',summary);print(json.dumps(summary),flush=True)
  assert research,'No actual IRAOP tool call was observed'
 finally:
  save('posts.json',posts);save('responses.json',responses);save('polls.json',polls)
  try:save('fetch-streams.private.json',page.evaluate('window.__e2eStreams'));shot('final')
  except Exception:pass
  b.close()
