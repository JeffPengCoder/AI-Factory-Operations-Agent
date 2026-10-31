#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Use warning for the exact test rule; retain default global inhibition policy."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SSH=['ssh','-S','/private/tmp/mosaic-gpu-rca-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote=r'''import json,subprocess
from datetime import datetime,timezone
patch=[{'op':'test','path':'/metadata/uid','value':'476cc14d-fc7f-4720-b5b1-cbc63528356b'},{'op':'test','path':'/spec/groups/0/rules/0/labels/severity','value':'info'},{'op':'replace','path':'/spec/groups/0/rules/0/labels/severity','value':'warning'}]
argv=['kubectl','--context','kubernetes-admin@kubernetes','patch','prometheusrule','mosaic-gpu-rca-20261031t121240z','-n','monitoring','--type=json','-p',json.dumps(patch),'-o','json']
p=subprocess.run(argv,capture_output=True,text=True,timeout=30)
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'argv':argv,'patch':patch,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}));raise SystemExit(p.returncode)
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=60)
(ROOT/'test-severity-fix.private.stderr').write_text(p.stderr);d=json.loads(p.stdout)
(ROOT/'test-severity-fix.private.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'exitCode':d['exitCode'],'severity':'warning','globalInhibitionPolicyChanged':False}));assert p.returncode==0
