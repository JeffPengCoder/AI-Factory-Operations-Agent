#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Persist research compatibility with temporary request-body tracing disabled."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import time

PARENT=Path.home()/'.local/share/mosaic-validation-20261031/research-protocol-20261031'
ROOT=PARENT/'persistent-compat-final'
ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
K=[str(Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
H=[str(Path.home()/'.local/bin/helm'),'--kube-context','kind-mosaic-poc','-n','mosaic']
def get(argv):return json.loads(subprocess.check_output(argv))
def protected(name,raw):
    p=ROOT/name;p.write_bytes(raw);p.chmod(0o600)
def secrets():
    return {s['metadata']['name']:{'type':s.get('type'),'keys':sorted(s.get('data',{})),
            'dataDigest':hashlib.sha256(json.dumps(s.get('data',{}),sort_keys=True).encode()).hexdigest()}
            for s in get(K+['get','secrets','-o','json'])['items'] if s.get('type')!='helm.sh/release.v1'}
def model():
    s=get(['docker','inspect','--format','{{json .State}}','nemoclaw-vllm'])
    return {k:s[k] for k in ['Running','Pid','StartedAt']}

assert not (ROOT/'apply-launch.json').exists(), 'Do not repeat an applied upgrade.'
(ROOT/'apply-launch.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat()})+'\n')
history=get(H+['history','mosaic','-o','json']);assert history[-1]['revision']==14 and history[-1]['status']=='deployed'
prepared=json.loads((PARENT/'persistent-compat-attempt3/prepare-summary.json').read_text())
export=json.loads((PARENT/'native-proxy-provenance-revision14.json').read_text())
archive=Path(export['archive']);assert hashlib.sha256(archive.read_bytes()).hexdigest()==export['archiveSha256']
originals=json.loads(gzip.decompress(archive.read_bytes()));assert len(originals['files'])==len(export['records'])
check='''const fs=require('fs'),c=require('crypto'),dir='/audit/records';console.log(JSON.stringify(fs.readdirSync(dir).filter(x=>x.endsWith('.json')).sort().map(path=>({path,sha256:c.createHash('sha256').update(fs.readFileSync(dir+'/'+path)).digest('hex')}))));'''
current=get(K+['exec',export['pod'],'--','node','-e',check])
assert current==[{'path':r['path'],'sha256':r['sha256']} for r in originals['files']], 'New records appeared; export again before rolling the Pod.'
values=get(H+['get','values','mosaic','--all','-o','json'])
protected('values-before.private.json',json.dumps(values,indent=2).encode()+b'\n')
protected('manifest-before.private.yaml',subprocess.check_output(H+['get','manifest','mosaic']))
assert values['llm']['requestCompatibility']['researchToolCalls']=={'enabled':True,'auditEnabled':True}
values['llm']['requestCompatibility']['researchToolCalls']['auditEnabled']=False
protected('values-final.private.json',json.dumps(values,indent=2).encode()+b'\n')
expected=secrets();before=model();started=time.monotonic()
p=subprocess.run(H+['upgrade','mosaic',prepared['chartPath'],'-f',str(ROOT/'values-final.private.json'),
                    '--atomic','--wait','--timeout','20m','-o','json'],capture_output=True)
protected('upgrade.stdout.private',p.stdout);protected('upgrade.stderr.private',p.stderr)
assert p.returncode==0, 'See protected upgrade output.'
elapsed=time.monotonic()-started
history=get(H+['history','mosaic','-o','json']);assert history[-1]['revision']==15 and history[-1]['status']=='deployed'
protected('history-final.json',json.dumps(history,indent=2).encode()+b'\n')
assert secrets()==expected and model()==before
protected('application-secret-fingerprints-final.private.json',json.dumps(expected,indent=2).encode()+b'\n')
protected('current-values.private.json',subprocess.check_output(H+['get','values','mosaic','--all','-o','json']))
protected('current-manifest.private.yaml',subprocess.check_output(H+['get','manifest','mosaic']))
pods=get(K+['get','pods','-l','app=llm-openai-compat','-o','json'])['items']
pod=next(p for p in pods if not p['metadata'].get('deletionTimestamp') and all(c['ready'] for c in p['status'].get('containerStatuses',[])))
code='''const fs=require('fs'),c=require('crypto');console.log(JSON.stringify({sha256:c.createHash('sha256').update(fs.readFileSync('/config/server.mjs')).digest('hex'),researchEnabled:process.env.RESEARCH_TOOL_CALLS_ENABLED,auditDirectory:process.env.RESEARCH_TOOL_CALLS_AUDIT_DIR||null,auditVolumeExists:fs.existsSync('/audit')}));'''
loaded=get(K+['exec',pod['metadata']['name'],'--','node','-e',code])
assert loaded=={'sha256':prepared['renderedProxySha256'],'researchEnabled':'true','auditDirectory':None,'auditVolumeExists':False}
summary={'at':datetime.now(timezone.utc).isoformat(),'beforeRevision':14,'afterRevision':15,'status':'deployed',
         'elapsedSeconds':elapsed,'chartPath':prepared['chartPath'],'chartVersion':prepared['chartVersionAfter'],
         'proxyPod':pod['metadata']['name'],'proxyPodUid':pod['metadata']['uid'],'loadedProxy':loaded,
         'applicationSecretsCompared':len(expected),'applicationSecretChanges':[],
         'sharedModelBefore':before,'sharedModelAfter':model(),'sharedModelRestarted':False,
         'auditRecordsExported':len(originals['files']),'auditArchiveSha256':export['archiveSha256'],
         'researchToolCallsEnabled':True,'auditEnabled':False}
(ROOT/'apply-final-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
