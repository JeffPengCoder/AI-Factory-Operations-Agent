#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Read-only E2E baseline; UI credentials are obtained and used only in memory."""
from datetime import datetime,timezone
import base64,json,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from probe_access import SSH,read_ui_credentials,request
ROOT=Path(__file__).resolve().parent
c=read_ui_credentials();auth=base64.b64encode((c['username']+':'+c['password']).encode()).decode()
for name,path in [('ui-health','/api/health'),('mosaic-alertmanager-before','/api/alerts/alertmanager'),('mosaic-alerts-before','/api/alerts')]:
 d={'at':datetime.now(timezone.utc).isoformat(),**request(path,auth)}
 (ROOT/(name+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'file':name,'status':d['httpStatus']}),flush=True)
remote="""import json,time,urllib.request,urllib.error
from datetime import datetime,timezone
opener=urllib.request.build_opener()
for name,url in [('prometheus-rules-before','http://target-node-1.example.invalid:30090/api/v1/rules?type=alert'),('prometheus-alerts-before','http://target-node-1.example.invalid:30090/api/v1/alerts'),('alertmanager-alerts-before','http://target-node-1.example.invalid:30093/api/v2/alerts')]:
 start=time.monotonic()
 try:
  with opener.open(url,timeout=20) as r:status,body=r.status,r.read().decode()
 except urllib.error.HTTPError as e:status,body=e.code,e.read().decode()
 print(json.dumps({'name':name,'at':datetime.now(timezone.utc).isoformat(),'url':url,'status':status,'elapsedSeconds':time.monotonic()-start,'body':body}),flush=True)
"""
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=100)
(ROOT/'remote-preflight.stderr').write_text(p.stderr)
assert p.returncode==0,p.stderr
for line in p.stdout.splitlines():
 d=json.loads(line);(ROOT/(d['name']+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'file':d['name'],'status':d['status']}),flush=True)
