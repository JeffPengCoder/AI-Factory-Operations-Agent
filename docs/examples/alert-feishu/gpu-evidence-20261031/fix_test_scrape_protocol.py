#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Patch only the new test ServiceMonitor with exact UID precondition."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SSH=['ssh','-S','/private/tmp/mosaic-gpu-rca-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
remote=r'''import json,subprocess
from datetime import datetime,timezone
ns='mosaic-gpu-rca-20261031t121240z';name='gpu-telemetry-fixture'
patch=[{'op':'test','path':'/metadata/uid','value':'3f990380-2497-4153-a290-9f3c00465f8c'},{'op':'add','path':'/spec/fallbackScrapeProtocol','value':'PrometheusText0.0.4'}]
argv=['kubectl','--context','kubernetes-admin@kubernetes','patch','servicemonitor',name,'-n',ns,'--type=json','-p',json.dumps(patch),'-o','json']
p=subprocess.run(argv,capture_output=True,text=True,timeout=30)
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'argv':argv,'patch':patch,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}))
raise SystemExit(p.returncode)
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=60)
(ROOT/'test-scrape-protocol-fix.private.stderr').write_text(p.stderr)
assert p.stdout,'No remote patch response'
d=json.loads(p.stdout);(ROOT/'test-scrape-protocol-fix.private.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'exitCode':d['exitCode'],'newFallback':'PrometheusText0.0.4'}));assert p.returncode==0
