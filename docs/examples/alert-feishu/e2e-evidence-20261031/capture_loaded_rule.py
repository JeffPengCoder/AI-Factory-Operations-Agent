#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Record complete loaded-rule response and the complete exact selected group."""
import json,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/Users/operator/workspace/system-sa/aiops/mosaic-run/alerts/live-validation-20261031')
from probe_access import SSH
ROOT=Path(__file__).resolve().parent
remote="""import json,urllib.request
from datetime import datetime,timezone
url='http://target-node-1.example.invalid:30090/api/v1/rules?type=alert'
with urllib.request.urlopen(url,timeout=20) as r:d={'at':datetime.now(timezone.utc).isoformat(),'url':url,'status':r.status,'body':r.read().decode()}
print(json.dumps(d))
"""
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=45)
(ROOT/'loaded-rule.stderr').write_text(p.stderr);assert p.returncode==0,p.stderr
d=json.loads(p.stdout);(ROOT/'prometheus-loaded-rules.private.json').write_text(json.dumps(d,indent=2)+'\n')
selected=[x for x in json.loads(d['body'])['data']['groups'] if x['name']==ROOT.name]
assert len(selected)==1
(ROOT/'prometheus-loaded-test-group.json').write_text(json.dumps({'at':d['at'],'status':d['status'],'groups':selected},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'groups':len(selected),'rules':[{'name':x['name'],'state':x['state'],'health':x['health'],'lastError':x.get('lastError'),'query':x.get('query')} for x in selected[0]['rules']]}))
