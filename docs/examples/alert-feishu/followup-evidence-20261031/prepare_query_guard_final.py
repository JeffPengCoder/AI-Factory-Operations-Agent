#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Prepare one plugin-file backport using the preserved real deployment chart."""
from datetime import datetime,timezone
import base64,copy,hashlib,json,pathlib,shutil,subprocess,tarfile

ROOT=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-debug/query-guard-final'
ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
ROOT.chmod(0o700)
HELM=[str(pathlib.Path.home()/'.local/bin/helm'),'--kube-context','kind-mosaic-poc','-n','mosaic']
K=[str(pathlib.Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']

def protected(name,data):
    p=ROOT/name;p.write_bytes(data);p.chmod(0o600);return p
def command(argv,name):
    p=subprocess.run(argv,capture_output=True)
    protected(name+'.stdout.private',p.stdout);protected(name+'.stderr.private',p.stderr)
    assert p.returncode==0,{'stage':name,'exitCode':p.returncode,'details':'See protected output files.'}
    return p.stdout
def digest_secret(obj):
    data=dict(obj.get('data',{}))
    for key,value in obj.get('stringData',{}).items():data[key]=base64.b64encode(value.encode()).decode()
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

def main():
    history=json.loads(command(HELM+['history','mosaic','-o','json'],'history-before'))
    assert history[-1]['revision']==11 and history[-1]['status']=='deployed',history[-1]
    values=command(HELM+['get','values','mosaic','-o','yaml'],'values-before')
    protected('values-before.private.yaml',values)
    protected('manifest-before.private.yaml',command(HELM+['get','manifest','mosaic'],'manifest-before'))
    # Compute fingerprints in memory; do not create a copy of all Secret values.
    secrets=json.loads(subprocess.check_output(K+['get','secrets','-o','json']))['items']
    current={s['metadata']['name']:s for s in secrets if s.get('type')!='helm.sh/release.v1'}
    fingerprints=[{'name':s['metadata']['name'],'type':s.get('type'),'keys':sorted(s.get('data',{})),'dataDigest':digest_secret(s)} for s in current.values()]
    protected('application-secret-fingerprints-before.private.json',json.dumps(fingerprints,indent=2).encode()+b'\n')
    original=pathlib.Path(json.loads((ROOT.parent/'query-guard-2/prepare-summary.json').read_text())['chartPath'])
    shutil.copy2(original,ROOT/'original-chart.tgz')
    extract=ROOT/'chart'
    assert not extract.exists(),'Prepared chart already exists; inspect it instead of overwriting.'
    extract.mkdir(mode=0o700)
    with tarfile.open(original) as archive:archive.extractall(extract,filter='data')
    chart=extract/'mosaic-stack'
    destination=chart/'files/openclaw-seed/extensions/iraop/index.ts'
    old=destination.read_bytes();new=(ROOT.parent/'iraop-index-final.ts').read_bytes()
    assert b'function queryEvidenceProblem' in new and b'function queryEvidenceProblem' in old
    protected('original-iraop-index.ts',old);destination.write_bytes(new)
    chart_yaml=chart/'Chart.yaml';text=chart_yaml.read_text()
    line=next(x for x in text.splitlines() if x.startswith('version:'))
    old_version=line.split(':',1)[1].strip().strip('"\'')
    version=old_version+'.2'
    chart_yaml.write_text(text.replace(line,'version: '+version,1))
    command([str(pathlib.Path.home()/'.local/bin/helm'),'lint',str(chart),'-f',str(ROOT/'values-before.private.yaml')],'lint')
    preview=json.loads(command(HELM+['upgrade','mosaic',str(chart),'-f',str(ROOT/'values-before.private.yaml'),'--dry-run=server','-o','json'],'upgrade-preview'))
    preview_manifest=protected('preview-manifest.private.yaml',preview['manifest'].encode())
    # The real chart includes resources in agent-sandbox-system as well as mosaic.
    # Parse the already server-rendered manifest without forcing one namespace
    # onto all of them. Reuse the existing embedding environment's YAML reader.
    python=str(pathlib.Path.home()/'.local/share/mosaic-validation-20261031/embedding/.venv/bin/python')
    parser='import sys,yaml,json; print(json.dumps([x for x in yaml.safe_load_all(open(sys.argv[1])) if x]))'
    items=json.loads(command([python,'-c',parser,str(preview_manifest)],'preview-objects'))
    checked=[]
    for obj in items:
        if obj.get('kind')=='Secret' and obj['metadata']['name'] in current:
            name=obj['metadata']['name'];assert digest_secret(obj)==digest_secret(current[name]),'Secret data would change: '+name;checked.append(name)
    assert checked,'Expected existing chart-managed secrets to be checked'
    assert not any(o.get('kind')=='ClusterRoleBinding' and o['metadata']['name'].endswith('-oc-editor') for o in items)
    command([str(pathlib.Path.home()/'.local/bin/helm'),'package',str(chart),'--destination',str(ROOT)],'package')
    packages=list(ROOT.glob('mosaic-stack-*.tgz'));assert len(packages)==1
    summary={'at':datetime.now(timezone.utc).isoformat(),'baseRevision':11,'chartVersionBefore':old_version,'chartVersionAfter':version,'chartPath':str(packages[0]),'pluginBeforeSha256':hashlib.sha256(old).hexdigest(),'pluginAfterSha256':hashlib.sha256(new).hexdigest(),'checkedExistingSecretNames':checked,'existingSecretDataUnchangedInServerDryRun':True,'renderedResources':[{'kind':o.get('kind'),'namespace':o.get('metadata',{}).get('namespace'),'name':o['metadata']['name']} for o in items],'noEditorBinding':True,'changeScope':['One IRAOP plugin source file','Chart build metadata'],'deployed':False}
    (ROOT/'prepare-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
