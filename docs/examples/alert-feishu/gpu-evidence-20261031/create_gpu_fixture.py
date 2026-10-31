#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Create only the exact run-labelled fixture after identity and absence checks."""
from datetime import datetime,timezone
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN=ROOT.name;NS='mosaic-'+RUN
SSH=['ssh','-S','/private/tmp/mosaic-gpu-rca-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
manifest=json.loads((ROOT/'gpu-fixture.prepared.private.json').read_text())
(ROOT/'gpu-fixture.applied-input.private.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert not (ROOT/'create-fixture-started.json').exists()
(ROOT/'create-fixture-started.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'runId':RUN,'scope':'six new run-labelled GPU simulation fixture objects; no production/Secret/RBAC/GPU hardware changes'},indent=2)+'\n')
remote=r'''import json,subprocess,sys
from datetime import datetime,timezone
m=json.loads(sys.stdin.read());run='gpu-rca-20261031t121240z';ns='mosaic-'+run
rows=[]
def execute(args,data=None,expected=(0,)):
 p=subprocess.run(args,input=data,text=True,capture_output=True,timeout=45)
 row={'at':datetime.now(timezone.utc).isoformat(),'argv':args,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 if data is not None:row['stdin']=data
 rows.append(row)
 if p.returncode not in expected:raise RuntimeError('Command failed: '+repr(args))
 return p.stdout
k=['kubectl','--context','kubernetes-admin@kubernetes']
try:
 assert execute(['hostname']).strip()=='target-node-1'
 assert execute(['kubectl','config','current-context']).strip()=='kubernetes-admin@kubernetes'
 assert not execute(k+['get','namespace',ns,'--ignore-not-found','-o','json']).strip()
 assert not execute(k+['get','prometheusrule','mosaic-'+run,'-n','monitoring','--ignore-not-found','-o','json']).strip()
 node=json.loads(execute(k+['get','node','target-node-1','-o','json']))
 assert any(x['type']=='Ready' and x['status']=='True' for x in node['status']['conditions'])
 for condition in node['status']['conditions']:
  if condition['type'] in ['MemoryPressure','DiskPressure','PIDPressure']:assert condition['status']=='False'
 for obj in m['items']:assert obj['metadata']['labels']['run_id']==run
 execute(k+['create','--dry-run=server','-f','-','-o','json'],json.dumps(m['items'][-1]))
 execute(k+['create','-f','-','-o','json'],json.dumps(m['items'][0]))
 for obj in m['items'][1:]:execute(k+['create','--dry-run=server','-f','-','-o','json'],json.dumps(obj))
 for obj in m['items'][1:]:execute(k+['create','-f','-','-o','json'],json.dumps(obj))
 execute(k+['get','pod','gpu-telemetry-fixture','-n',ns,'-o','json'])
 execute(k+['get','prometheusrule','mosaic-'+run,'-n','monitoring','-o','json'])
 result={'success':True,'commands':rows}
except Exception as e:result={'success':False,'errorType':type(e).__name__,'error':str(e),'commands':rows}
print(json.dumps(result))
if not result['success']:raise SystemExit(1)
'''
# The remote script is an argv argument; the exact manifest travels through stdin.
import shlex
p=subprocess.run(SSH+['python3 -c '+shlex.quote(remote)],input=json.dumps(manifest),text=True,capture_output=True,timeout=240)
(ROOT/'create-fixture.stderr').write_text(p.stderr)
try:result=json.loads(p.stdout)
except ValueError:
 (ROOT/'create-fixture-unparsed.stdout').write_text(p.stdout);raise
(ROOT/'create-fixture-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'success':result['success'],'runId':RUN,'commands':len(result['commands']),'error':result.get('error')}))
assert p.returncode==0 and result['success']
