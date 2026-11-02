#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Prepare a minimal real-chart backport with protected backups and server review."""
from datetime import datetime, timezone
import base64, hashlib, json, pathlib, shutil, subprocess, tarfile

PARENT=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-protocol-20261031'
ROOT=PARENT/'persistent-compat-attempt3'
ROOT.mkdir(mode=0o700,parents=True,exist_ok=True);ROOT.chmod(0o700)
K=[str(pathlib.Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
H=[str(pathlib.Path.home()/'.local/bin/helm'),'--kube-context','kind-mosaic-poc','-n','mosaic']

def protected(name,raw):
    p=ROOT/name;p.write_bytes(raw);p.chmod(0o600);return p
def run(argv,name):
    p=subprocess.run(argv,capture_output=True)
    protected(name+'.stdout.private',p.stdout);protected(name+'.stderr.private',p.stderr)
    assert p.returncode==0,{'stage':name,'exitCode':p.returncode,'detail':'See protected output.'}
    return p.stdout
def digest(data):return hashlib.sha256(data).hexdigest()
def secret_digest(obj):
    data=dict(obj.get('data',{}))
    for k,v in obj.get('stringData',{}).items():data[k]=base64.b64encode(v.encode()).decode()
    return digest(json.dumps(data,sort_keys=True).encode())

history=json.loads(run(H+['history','mosaic','-o','json'],'history-before'))
assert history[-1]['revision']==13 and history[-1]['status']=='deployed'
protected('user-values-before.private.json',run(H+['get','values','mosaic','-o','json'],'user-values-before'))
values_raw=run(H+['get','values','mosaic','--all','-o','json'],'values-before')
protected('values-before.private.json',values_raw)
protected('manifest-before.private.yaml',run(H+['get','manifest','mosaic'],'manifest-before'))
values=json.loads(values_raw)
assert values['modules']['research']['enabled'] and values['llm']['requestCompatibility']['enabled']
values['llm']['requestCompatibility'].setdefault('researchToolCalls',{}).update(enabled=True,auditEnabled=True)
protected('values-validation.private.json',json.dumps(values,indent=2).encode()+b'\n')
current={s['metadata']['name']:s for s in json.loads(subprocess.check_output(K+['get','secrets','-o','json']))['items'] if s.get('type')!='helm.sh/release.v1'}
fingerprints={name:{'type':s.get('type'),'keys':sorted(s.get('data',{})),'dataDigest':secret_digest(s)} for name,s in current.items()}
protected('application-secret-fingerprints-before.private.json',json.dumps(fingerprints,indent=2).encode()+b'\n')
previous=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-debug/query-guard-final/apply-summary.json'
original=pathlib.Path(json.loads((PARENT/'persistent-compat-attempt2/prepare-summary.json').read_text())['chartPath'])
protected('original-chart.tgz',original.read_bytes())
extract=ROOT/'chart';assert not extract.exists(),'Prepared output already exists; inspect it rather than overwrite.'
extract.mkdir(mode=0o700)
with tarfile.open(original) as t:t.extractall(extract,filter='data')
chart=extract/'mosaic-stack'
changes=[]
for source,destination in [('llm-compat-fixed.mjs','files/llm-compat-server.mjs'),('llm-compat-candidate.yaml','templates/llm-compat.yaml')]:
    raw=(PARENT/source).read_bytes();out=chart/destination
    if out.exists():protected('before-'+out.name,out.read_bytes())
    out.write_bytes(raw);changes.append({'path':destination,'bytes':len(raw),'sha256':digest(raw)})
launch=json.loads((PARENT/'node-candidate-launch.json').read_text())
assert changes[0]['sha256']==digest((PARENT/'llm-compat-fixed.mjs').read_bytes())
chart_yaml=chart/'Chart.yaml';text=chart_yaml.read_text();line=next(x for x in text.splitlines() if x.startswith('version:'))
old_version=line.split(':',1)[1].strip().strip('"\'');version=old_version+'.startup2'
chart_yaml.write_text(text.replace(line,'version: '+version,1))
run([str(pathlib.Path.home()/'.local/bin/helm'),'lint',str(chart),'-f',str(ROOT/'values-validation.private.json')],'lint')
preview=json.loads(run(H+['upgrade','mosaic',str(chart),'-f',str(ROOT/'values-validation.private.json'),'--dry-run=server','-o','json'],'preview'))
manifest=protected('preview-manifest.private.yaml',preview['manifest'].encode())
python=str(pathlib.Path.home()/'.local/share/mosaic-validation-20261031/embedding/.venv/bin/python')
parser='import json,yaml,sys;print(json.dumps([x for x in yaml.safe_load_all(open(sys.argv[1])) if x]))'
objects=json.loads(run([python,'-c',parser,str(manifest)],'preview-objects'))
checked=[]
for obj in objects:
    if obj.get('kind')=='Secret' and obj['metadata']['name'] in current:
        name=obj['metadata']['name'];assert secret_digest(obj)==secret_digest(current[name]),'Secret data would change: '+name;checked.append(name)
assert checked
assert not any(o.get('kind')=='ClusterRoleBinding' and o['metadata']['name'].endswith('-oc-editor') for o in objects)
name=values['llm']['requestCompatibility']['name']
cm=next(o for o in objects if o.get('kind')=='ConfigMap' and o['metadata']['name']==name)
deployment=next(o for o in objects if o.get('kind')=='Deployment' and o['metadata']['name']==name)
env={v['name']:v.get('value') for v in deployment['spec']['template']['spec']['containers'][0]['env']}
assert env['RESEARCH_TOOL_CALLS_ENABLED']=='true' and env['RESEARCH_TOOL_CALLS_AUDIT_DIR']=='/audit/records'
assert deployment['spec']['template']['spec']['containers'][0]['command']==['node','/config/server.mjs']
run([str(pathlib.Path.home()/'.local/bin/helm'),'package',str(chart),'--destination',str(ROOT)],'package')
packages=list(ROOT.glob('mosaic-stack-*.tgz'));assert len(packages)==1
summary={'at':datetime.now(timezone.utc).isoformat(),'baseRevision':13,'chartVersionBefore':old_version,'chartVersionAfter':version,'chartPath':str(packages[0]),'changeScope':changes,'originalChartSha256':digest(original.read_bytes()),'renderedProxySha256':digest(cm['data']['server.mjs'].encode()),'existingSecretDataUnchangedInServerDryRun':True,'checkedSecretNames':checked,'applicationSecretsCompared':len(fingerprints),'noEditorBinding':True,'researchToolCallsEnabled':True,'auditEnabledForValidation':True,'renderedResources':[{'kind':o['kind'],'namespace':o.get('metadata',{}).get('namespace'),'name':o['metadata']['name']} for o in objects],'sharedModelRestarted':False}
(ROOT/'prepare-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
