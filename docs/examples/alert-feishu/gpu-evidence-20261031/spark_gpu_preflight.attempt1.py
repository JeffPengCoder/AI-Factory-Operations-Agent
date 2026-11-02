#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Collect only current GPU telemetry and safe MOSAIC module metadata, read-only."""
from datetime import datetime,timezone
import base64,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from probe_access import SSH,read_ui_credentials,request
ROOT=Path(__file__).resolve().parent
remote=r"""import json,pathlib,subprocess,urllib.request,urllib.parse,urllib.error
from datetime import datetime,timezone
rows=[]
queries=['DCGM_FI_DEV_GPU_UTIL','DCGM_FI_DEV_XID_ERRORS','DCGM_FI_DEV_ECC_DBE_VOL_TOTAL','DCGM_FI_DEV_ECC_DBE_AGG_TOTAL','DCGM_FI_DEV_ROW_REMAP_FAILURE','DCGM_FI_DEV_RETIRED_DBE','up{job=~".*dcgm.*"}']
for query in queries:
 url='http://target-node-1.example.invalid:30090/api/v1/query?'+urllib.parse.urlencode({'query':query})
 try:
  with urllib.request.urlopen(url,timeout=15) as r:status,body=r.status,r.read().decode()
  rows.append({'at':datetime.now(timezone.utc).isoformat(),'query':query,'httpStatus':status,'body':body})
 except Exception as e:rows.append({'at':datetime.now(timezone.utc).isoformat(),'query':query,'errorType':type(e).__name__})
url='http://target-node-1.example.invalid:30090/api/v1/rules?type=alert'
with urllib.request.urlopen(url,timeout=15) as r:rules=json.load(r)
selected=[]
for g in rules['data']['groups']:
 own=[x for x in g['rules'] if any(word in (x['name']+' '+x.get('query','')).upper() for word in ['DCGM','GPU','XID','ECC'])]
 if own:selected.append({**g,'rules':own})
helm=str(pathlib.Path.home()/'.local/bin/helm')
values=json.loads(subprocess.check_output([helm,'--kube-context','kind-mosaic-poc','get','values','mosaic','-n','mosaic','-o','json']))
modules=values.get('modules',{})
k=str(pathlib.Path.home()/'.local/bin/kubectl')
pods=json.loads(subprocess.check_output([k,'--context','kind-mosaic-poc','-n','mosaic','get','pods','-o','json']))
safePods=[{'name':p['metadata']['name'],'images':[c['image'] for c in p['spec']['containers']],'phase':p['status']['phase']} for p in pods['items']]
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'metrics':rows,'completeSelectedGpuRuleGroups':selected,'moduleFlags':modules,'pods':safePods}))
"""
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=180)
(ROOT/'spark-gpu-preflight.stderr').write_text(p.stderr)
assert p.returncode==0,p.stderr
out=json.loads(p.stdout);(ROOT/'spark-gpu-preflight.private.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
c=read_ui_credentials();auth=base64.b64encode((c['username']+':'+c['password']).encode()).decode();c=None
status=request('/api/alerts/alertmanager',auth);(ROOT/'mosaic-polling-before.private.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'moduleFlags':out['moduleFlags'],'gpuRuleNames':[x['name'] for g in out['completeSelectedGpuRuleGroups'] for x in g['rules']],'metricSeriesCounts':[{'query':x['query'],'series':len(json.loads(x['body']).get('data',{}).get('result',[])) if x.get('httpStatus')==200 else None} for x in out['metrics']],'mosaicPollingHttp':status['httpStatus']}),flush=True)
