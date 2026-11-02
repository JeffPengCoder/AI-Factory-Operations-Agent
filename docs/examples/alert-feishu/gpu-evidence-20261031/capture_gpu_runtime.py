#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exact run objects, real counters and existing monitor identity; read only."""
import json,subprocess,sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;phase=sys.argv[1];assert re.fullmatch('[a-z0-9-]+',phase)
SSH=['ssh','-S','/private/tmp/mosaic-gpu-rca-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote=r'''import json,subprocess,pathlib,os,re
from datetime import datetime,timezone
run='gpu-rca-20261031t121240z';ns='mosaic-'+run;k=['kubectl','--context','kubernetes-admin@kubernetes']
commands=[k+['get','pod','gpu-telemetry-fixture','-n',ns,'-o','json'],k+['get','servicemonitor','gpu-telemetry-fixture','-n',ns,'-o','json'],k+['get','prometheusrule','mosaic-'+run,'-n','monitoring','-o','json'],k+['get','events','-n',ns,'-o','json'],k+['get','prometheusrule','mosaic-alert-smoke-test','-n','monitoring','-o','json'],['nvidia-smi','-q','-x'],['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name,used_gpu_memory','--format=csv'],['dcgmi','dmon','--host','127.0.0.1:5555','-e','230,311,313','-c','2']]
for c in ['telemetry','nvml-witness','kernel-witness']:commands.append(k+['logs','gpu-telemetry-fixture','-n',ns,'-c',c,'--timestamps'])
rows=[]
for argv in commands:
 p=subprocess.run(argv,capture_output=True,text=True,timeout=30)
 rows.append({'at':datetime.now(timezone.utc).isoformat(),'argv':argv,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
processes={}
for pid in [12518,1337145,1339392]:
 path=pathlib.Path('/proc')/str(pid)
 processes[str(pid)]={'exists':path.exists(),'comm':(path/'comm').read_text().strip() if (path/'comm').exists() else None}
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'commands':rows,'processes':processes}))
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=400)
(ROOT/('root-'+phase+'.private.stderr')).write_text(p.stderr);assert p.returncode==0
d=json.loads(p.stdout);(ROOT/('root-'+phase+'.private.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'phase':phase,'commands':[{'argv':r['argv'],'exitCode':r['exitCode']} for r in d['commands']],'processes':d['processes']}))
