#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Delete only the four exact run-owned objects after checking all original UIDs."""
from datetime import datetime,timezone
import json,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN=ROOT.name;NS='mosaic-'+RUN
assert json.loads((ROOT/'feishu-send-result.json').read_text())['botApiAccepted'], 'Retain evidence and inspect delivery before cleanup.'
created=json.loads((ROOT/'create-fixture-result.json').read_text());expected={}
for command in created['commands']:
 if 'create' not in command['argv'] or '--dry-run=server' in command['argv']:continue
 obj=json.loads(command['stdout']);expected[obj['kind']]=obj['metadata']['uid']
assert set(expected)=={'Namespace','ConfigMap','Pod','PrometheusRule'}
SSH=['ssh','-S','/private/tmp/mosaic-e2e-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote=r'''import json,subprocess,sys
from datetime import datetime,timezone
expected=json.loads(sys.stdin.read());run='e2e-20261031t075722z';ns='mosaic-'+run
k=['kubectl','--context','kubernetes-admin@kubernetes'];rows=[]
def execute(args):
 p=subprocess.run(k+args,capture_output=True,text=True,timeout=90)
 row={'at':datetime.now(timezone.utc).isoformat(),'argv':k+args,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr};rows.append(row)
 if p.returncode:raise RuntimeError('Command failed: '+repr(args))
 return p.stdout
objects=[('Namespace',['namespace',ns]),('ConfigMap',['configmap','fixture-input','-n',ns]),('Pod',['pod','mosaic-log-fixture','-n',ns]),('PrometheusRule',['prometheusrule','mosaic-'+run,'-n','monitoring'])]
try:
 for kind,args in objects:
  obj=json.loads(execute(['get']+args+['-o','json']))
  assert obj['metadata']['uid']==expected[kind] and obj['metadata']['labels']['run_id']==run
 for kind,args in [objects[3],objects[2],objects[1],objects[0]]:
  execute(['delete']+args+['--wait=true','--timeout=60s'])
 for kind,args in objects:
  assert not execute(['get']+args+['--ignore-not-found','-o','json']).strip()
 result={'success':True,'deletedOnlyExactOriginalUids':expected,'commands':rows}
except Exception as e:result={'success':False,'errorType':type(e).__name__,'error':str(e),'commands':rows}
print(json.dumps(result))
if not result['success']:raise SystemExit(1)
'''
assert not (ROOT/'cleanup-started.json').exists()
(ROOT/'cleanup-started.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'expectedUids':expected},indent=2)+'\n')
p=subprocess.run(SSH+['python3 -c '+shlex.quote(remote)],input=json.dumps(expected),text=True,capture_output=True,timeout=360)
(ROOT/'cleanup.stderr').write_text(p.stderr)
try:d=json.loads(p.stdout)
except ValueError:(ROOT/'cleanup-unparsed.stdout').write_text(p.stdout);raise
(ROOT/'cleanup-result.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'success':d['success'],'commands':len(d['commands']),'error':d.get('error')}));assert p.returncode==0 and d['success']
