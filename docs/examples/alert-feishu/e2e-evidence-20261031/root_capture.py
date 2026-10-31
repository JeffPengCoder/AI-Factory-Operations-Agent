#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Independent complete read-only witness of this exact isolated workload."""
from datetime import datetime,timezone
import json,re,subprocess,sys,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parent
phase=sys.argv[1];assert re.fullmatch('[a-z0-9-]+',phase)
SSH=['ssh','-S','/private/tmp/mosaic-e2e-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote=r'''import json,subprocess,time
from datetime import datetime,timezone
ns='mosaic-e2e-20261031t075722z';pod='mosaic-log-fixture'
k=['kubectl','--context','kubernetes-admin@kubernetes'];rows=[]
for args in [['get','pod',pod,'-n',ns,'-o','json'],['describe','pod',pod,'-n',ns],['logs',pod,'-n',ns,'-c','fixture','--previous','--timestamps'],['logs',pod,'-n',ns,'-c','fixture','--timestamps'],['get','events','-n',ns,'-o','json'],['get','configmap','fixture-input','-n',ns,'-o','json'],['get','prometheusrule','mosaic-e2e-20261031t075722z','-n','monitoring','-o','json']]:
 start=time.monotonic();p=subprocess.run(k+args,capture_output=True,text=True,timeout=25)
 rows.append({'at':datetime.now(timezone.utc).isoformat(),'argv':k+args,'elapsedSeconds':time.monotonic()-start,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'commands':rows}))
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=180)
(ROOT/('root-'+phase+'.stderr')).write_text(p.stderr);assert p.returncode==0,p.stderr
r=json.loads(p.stdout);(ROOT/('root-'+phase+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
pod=json.loads(r['commands'][0]['stdout']);cs=pod['status'].get('containerStatuses',[])
print(json.dumps({'phase':phase,'podPhase':pod['status']['phase'],'containers':cs,'previousLog':r['commands'][2],'currentLog':r['commands'][3]},ensure_ascii=False))
