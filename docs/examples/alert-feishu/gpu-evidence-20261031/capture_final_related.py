#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Capture every remaining Alertmanager/Prometheus alert for the test namespace."""
from datetime import datetime,timezone
import base64,json,re,subprocess,sys
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from gpu_access import SSH,read_ui_credentials,request
ROOT=Path(__file__).resolve().parent;phase=sys.argv[1];assert re.fullmatch('[a-z0-9-]+',phase)
remote=r'''import json,urllib.request
from datetime import datetime,timezone
from urllib.parse import urlencode
ns='mosaic-gpu-rca-20261031t121240z';rows=[]
for name,url in [('prometheus','http://target-node-1.example.invalid:30090/api/v1/query?'+urlencode({'query':'ALERTS{namespace="'+ns+'"}'})),('alertmanager','http://target-node-1.example.invalid:30093/api/v2/alerts?'+urlencode({'filter':'namespace="'+ns+'"'}))]:
 with urllib.request.urlopen(url,timeout=20) as r:rows.append({'name':name,'at':datetime.now(timezone.utc).isoformat(),'url':url,'status':r.status,'body':r.read().decode()})
print(json.dumps(rows))
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=60)
assert p.returncode==0,p.stderr
c=read_ui_credentials();auth=base64.b64encode((c['username']+':'+c['password']).encode()).decode();c=None
ui=request('/api/alerts',auth);b=ui.get('body',{});selected=[a for a in b.get('alerts',[]) if ROOT.name in json.dumps(a)]
d={'at':datetime.now(timezone.utc).isoformat(),'remote':json.loads(p.stdout),'allRelatedMosaicAlerts':selected,'mosaicPolling':request('/api/alerts/alertmanager',auth),'uiHealth':request('/api/health'),'uiUnauthenticated':request('/api/alerts/alertmanager'),'uiAuthenticated':request('/api/alerts/alertmanager',auth)}
(ROOT/('related-'+phase+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'phase':phase,'remote':[{'name':x['name'],'count':len(json.loads(x['body'])) if x['name']=='alertmanager' else len(json.loads(x['body'])['data']['result'])} for x in d['remote']],'mosaicHistoricalAlerts':len(selected),'access':[d[k]['httpStatus'] for k in ['uiHealth','uiUnauthenticated','uiAuthenticated']]}))
