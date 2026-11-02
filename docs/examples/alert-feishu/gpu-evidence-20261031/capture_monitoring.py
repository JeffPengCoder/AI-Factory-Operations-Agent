#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Capture selected scrape target errors, original metric families and rule history."""
import json,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
from gpu_access import SSH
phase=sys.argv[1];assert phase.replace('-','').isalnum()
remote=r'''import json,urllib.request,urllib.parse,urllib.error,re,hashlib
from datetime import datetime,timezone
run='gpu-rca-20261031t121240z';ns='mosaic-'+run
base='http://target-node-1.example.invalid:30090';rows=[]
queries=['count by (__name__) ({__name__=~"DCGM_.*"})','up{namespace="'+ns+'"}','mosaic_test_dcgm_xid_error{run_id="'+run+'"}','ALERTS{run_id="'+run+'"}','prometheus_config_last_reload_successful','prometheus_config_last_reload_success_timestamp_seconds']
for q in queries:
 path='/api/v1/query?'+urllib.parse.urlencode({'query':q})
 with urllib.request.urlopen(base+path,timeout=20) as r:rows.append({'at':datetime.now(timezone.utc).isoformat(),'path':path,'query':q,'httpStatus':r.status,'body':r.read().decode()})
with urllib.request.urlopen(base+'/api/v1/targets?state=active',timeout=20) as r:targets=json.load(r)
selected=[x for x in targets['data']['activeTargets'] if run in json.dumps(x)]
with urllib.request.urlopen(base+'/api/v1/status/config',timeout=20) as r:config=json.load(r)['data']['yaml']
starts=[m.start() for m in re.finditer(r'(?m)^\s*- job_name:',config)];starts.append(len(config))
selected_configs=[config[a:b] for a,b in zip(starts,starts[1:]) if run in config[a:b]]
end=datetime.now(timezone.utc).timestamp();start=datetime(2026,10,31,13,32,tzinfo=timezone.utc).timestamp()
path='/api/v1/query_range?'+urllib.parse.urlencode({'query':'ALERTS{run_id="'+run+'"}','start':start,'end':end,'step':5})
with urllib.request.urlopen(base+path,timeout=20) as r:rows.append({'at':datetime.now(timezone.utc).isoformat(),'path':path,'httpStatus':r.status,'body':r.read().decode()})
print(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'requests':rows,'selectedTargets':selected,'completeSelectedScrapeConfigBlocks':selected_configs,'fullConfigSha256':hashlib.sha256(config.encode()).hexdigest()}))
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=150)
(ROOT/('monitoring-'+phase+'.private.stderr')).write_text(p.stderr);assert p.returncode==0
d=json.loads(p.stdout);(ROOT/('monitoring-'+phase+'.private.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'phase':phase,'targets':[{'scrapeUrl':x['scrapeUrl'],'health':x['health'],'lastError':x['lastError']} for x in d['selectedTargets']]}))
