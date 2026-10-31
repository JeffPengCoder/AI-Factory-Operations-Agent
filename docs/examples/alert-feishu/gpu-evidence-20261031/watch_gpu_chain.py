#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Capture the actual Prometheus -> Alertmanager -> MOSAIC transitions in full."""
from datetime import datetime,timezone
import base64,json,subprocess,sys,time
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from gpu_access import SSH,read_ui_credentials,request
ROOT=Path(__file__).resolve().parent
RUN=ROOT.name;NS='mosaic-'+RUN
c=read_ui_credentials();auth=base64.b64encode((c['username']+':'+c['password']).encode()).decode();c=None
remote=r'''import json,urllib.request,urllib.error
from datetime import datetime,timezone
run='gpu-rca-20261031t121240z';ns='mosaic-'+run
from urllib.parse import urlencode
queries=[('fixture','http://target-node-1.example.invalid:30090/api/v1/query?'+urlencode({'query':'mosaic_test_dcgm_xid_error{run_id="'+run+'"}'})),('firing','http://target-node-1.example.invalid:30090/api/v1/query?'+urlencode({'query':'ALERTS{run_id="'+run+'"}'})),('alertmanager','http://target-node-1.example.invalid:30093/api/v2/alerts?'+urlencode({'filter':'run_id="'+run+'"'}))]
rows=[]
for name,url in queries:
 try:
  with urllib.request.urlopen(url,timeout=12) as r:status,body=r.status,r.read().decode()
 except urllib.error.HTTPError as e:status,body=e.code,e.read().decode()
 except Exception as e:rows.append({'name':name,'url':url,'at':datetime.now(timezone.utc).isoformat(),'errorType':type(e).__name__});continue
 rows.append({'name':name,'url':url,'at':datetime.now(timezone.utc).isoformat(),'status':status,'body':body})
print(json.dumps(rows))
'''
assert not (ROOT/'chain-samples.jsonl').exists()
last=None
with (ROOT/'chain-samples.jsonl').open('x') as f:
 for iteration in range(150):
  if (ROOT/'stop-watcher').exists():break
  snapshot={'at':datetime.now(timezone.utc).isoformat(),'iteration':iteration}
  try:
   p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=65)
   snapshot['remoteExitCode']=p.returncode;snapshot['remoteStderr']=p.stderr
   if p.returncode==0:snapshot['remote']=json.loads(p.stdout)
   else:snapshot['remoteStdout']=p.stdout
  except Exception as e:snapshot['remoteErrorType']=type(e).__name__
  snapshot['mosaic']=request('/api/alerts',auth)
  snapshot['mosaicPolling']=request('/api/alerts/alertmanager',auth)
  body=snapshot['mosaic'].get('body',{})
  selected=[a for a in body.get('alerts',[]) if RUN in json.dumps(a)] if isinstance(body,dict) else []
  snapshot['selected']=selected
  f.write(json.dumps(snapshot,ensure_ascii=False)+'\n');f.flush()
  states={}
  for row in snapshot.get('remote',[]):
   try:b=json.loads(row.get('body','null'))
   except ValueError:b=None
   if row['name']=='alertmanager':states['alertmanagerCount']=len(b) if isinstance(b,list) else None
   elif isinstance(b,dict):states[row['name']]=b.get('data',{}).get('result',[])
  marker={'states':{k:([{**v,'value':[None,v['value'][1]]} for v in value] if isinstance(value,list) else value) for k,value in states.items()},'mosaicCount':len(selected)}
  if marker!=last:
   print(json.dumps({'at':snapshot['at'],**marker}),flush=True);last=marker
  if selected and not (ROOT/'first-mosaic-alert.json').exists():
   (ROOT/'first-mosaic-alert.json').write_text(json.dumps({'observedAt':snapshot['at'],'alerts':selected},ensure_ascii=False,indent=2)+'\n')
  time.sleep(8)
print(json.dumps({'watcherStoppedAt':datetime.now(timezone.utc).isoformat()}),flush=True)
