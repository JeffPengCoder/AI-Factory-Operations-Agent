#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Submit the recorded operator correction once through the real native chat API."""
from datetime import datetime,timezone
import base64,json,sys,time,urllib.request
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from gpu_access import BASE,read_ui_credentials,request
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'review-api';OUT.mkdir(exist_ok=True)
s=json.loads((ROOT/'browser/summary.json').read_text());key=s['sessionKey']
c=read_ui_credentials();auth=base64.b64encode((c['username']+':'+c['password']).encode()).decode();c=None
before=request('/api/openclaw/chat?'+urlencode({'sessionKey':key,'limit':1000}),auth)
assert before['httpStatus']==200 and before['body'].get('hasActiveRun') is False
assert not (OUT/'started.json').exists(), 'Inspect prior request before resending.'
body={'prompt':(ROOT/'review/prompt.txt').read_text(),'sessionKey':key,'conciseMode':False,'accessMode':'view'}
(OUT/'request.json').write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n')
(OUT/'before-history-api.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n')
(OUT/'started.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'path':'/api/openclaw/chat/stream','method':'POST','accessMode':'view','submission':'same-session operator fact-check through native View chat API after real browser investigation completed'},indent=2)+'\n')
req=urllib.request.Request(BASE+'/api/openclaw/chat/stream',data=json.dumps(body).encode(),headers={'Authorization':'Basic '+auth,'Content-Type':'application/json'})
started=time.monotonic();opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(req,timeout=180) as r,(OUT/'stream.ndjson').open('wb') as f:
 (OUT/'response-metadata.json').write_text(json.dumps({'status':r.status,'contentType':r.headers.get('Content-Type')},indent=2)+'\n')
 while True:
  line=r.readline()
  if not line:break
  f.write(line);f.flush()
for _ in range(120):
 after=request('/api/openclaw/chat?'+urlencode({'sessionKey':key,'limit':1000}),auth)
 if after['httpStatus']==200 and after['body'].get('hasActiveRun') is False and after['body'].get('rawMessageCount',0)>s['messages']:break
 time.sleep(1)
else:raise RuntimeError('Review completion not observed')
h=json.loads(after['body']['history']['stdout'])
(OUT/'history-api.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n')
(OUT/'history-gateway.json').write_text(json.dumps(h,ensure_ascii=False,indent=2)+'\n')
answer=''.join(x.get('text','') for x in h['messages'][-1].get('content',[]) if x.get('type')=='text')
(OUT/'model-corrected-report.zh-CN.txt').write_text(answer+'\n')
result={'at':datetime.now(timezone.utc).isoformat(),'sessionKey':key,'sessionId':h['sessionId'],'messages':len(h['messages']),'elapsedSeconds':time.monotonic()-started,'newResearchCalls':sum(x.get('role')=='toolResult' and x.get('toolName')=='iraop_query' for x in h['messages'][s['messages']:]),'operatorCorrectionsProvided':True,'viewOnly':True}
(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
