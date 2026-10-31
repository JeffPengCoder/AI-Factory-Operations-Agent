#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Apply the reviewed proxy-only backport without altering the shared model."""
from datetime import datetime,timezone
import hashlib,json,pathlib,subprocess,time

ROOT=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-protocol-20261031/persistent-compat-attempt2'
K=[str(pathlib.Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
H=[str(pathlib.Path.home()/'.local/bin/helm'),'--kube-context','kind-mosaic-poc','-n','mosaic']
def protected(name,raw):
    p=ROOT/name;p.write_bytes(raw);p.chmod(0o600)
def get(argv):return json.loads(subprocess.check_output(argv))
def fingerprints():
    return {s['metadata']['name']:{'type':s.get('type'),'keys':sorted(s.get('data',{})),'dataDigest':hashlib.sha256(json.dumps(s.get('data',{}),sort_keys=True).encode()).hexdigest()} for s in get(K+['get','secrets','-o','json'])['items'] if s.get('type')!='helm.sh/release.v1'}
def model_state():
    data=get(['docker','inspect','--format','{{json .State}}','nemoclaw-vllm'])
    return {k:data[k] for k in ['Running','Pid','StartedAt']}

def main():
    prepared=json.loads((ROOT/'prepare-summary.json').read_text())
    assert prepared['baseRevision']==12 and prepared['existingSecretDataUnchangedInServerDryRun'] and prepared['noEditorBinding']
    proof=json.loads((ROOT.parent/'node-candidate-provenance.json').read_text())
    assert len(proof)==4 and all(x['messagesUnchanged'] and not x['firstQuestionContainsOracle'] for x in proof)
    history=get(H+['history','mosaic','-o','json']);assert history[-1]['revision']==12 and history[-1]['status']=='deployed'
    expected=json.loads((ROOT/'application-secret-fingerprints-before.private.json').read_text())
    assert fingerprints()==expected
    before=model_state()
    started=time.monotonic()
    p=subprocess.run(H+['upgrade','mosaic',prepared['chartPath'],'-f',str(ROOT/'values-validation.private.json'),'--atomic','--wait','--timeout','20m','-o','json'],capture_output=True)
    elapsed=time.monotonic()-started
    protected('upgrade.stdout.private',p.stdout);protected('upgrade.stderr.private',p.stderr)
    assert p.returncode==0,{'stage':'upgrade','exitCode':p.returncode,'detail':'See protected output.'}
    assert json.loads(p.stdout)['info']['status']=='deployed'
    history=get(H+['history','mosaic','-o','json']);assert history[-1]['revision']==13 and history[-1]['status']=='deployed'
    protected('history-validation.json',json.dumps(history,indent=2).encode()+b'\n')
    after_secrets=fingerprints();assert after_secrets==expected,'Unexpected application Secret changes.'
    protected('application-secret-fingerprints-validation.private.json',json.dumps(after_secrets,indent=2).encode()+b'\n')
    protected('current-validation-values.private.json',subprocess.check_output(H+['get','values','mosaic','-o','json']))
    protected('current-validation-manifest.private.yaml',subprocess.check_output(H+['get','manifest','mosaic']))
    values=json.loads((ROOT/'values-validation.private.json').read_text());name=values['llm']['requestCompatibility']['name']
    cm=get(K+['get','cm',name,'-o','json']);rendered=cm['data']['server.mjs'].encode()
    assert hashlib.sha256(rendered).hexdigest()==prepared['renderedProxySha256']
    pods=get(K+['get','pods','-l','app='+name,'-o','json'])['items']
    ready=[p for p in pods if not p['metadata'].get('deletionTimestamp') and p['status']['phase']=='Running' and all(c['ready'] for c in p['status'].get('containerStatuses',[]))]
    assert len(ready)==1;pod=ready[0]
    node='const fs=require("fs"),c=require("crypto"),b=fs.readFileSync("/config/server.mjs");console.log(JSON.stringify({sha256:c.createHash("sha256").update(b).digest("hex"),researchEnabled:process.env.RESEARCH_TOOL_CALLS_ENABLED,auditDir:process.env.RESEARCH_TOOL_CALLS_AUDIT_DIR}));'
    loaded=get(K+['exec',pod['metadata']['name'],'--','node','-e',node])
    assert loaded['sha256']==prepared['renderedProxySha256'] and loaded['researchEnabled']=='true' and loaded['auditDir']=='/audit/records'
    after=model_state();assert before==after
    summary={'at':datetime.now(timezone.utc).isoformat(),'beforeRevision':12,'afterRevision':13,'status':'deployed','elapsedSeconds':elapsed,'chartPath':prepared['chartPath'],'chartVersion':prepared['chartVersionAfter'],'proxyPod':pod['metadata']['name'],'proxyPodUid':pod['metadata']['uid'],'loadedProxy':loaded,'applicationSecretChanges':[],'applicationSecretsCompared':len(expected),'sharedModelBefore':before,'sharedModelAfter':after,'sharedModelRestarted':False,'nativeMcpValidation':'pending','auditEnabledForValidation':True,'auditDisabledAfterExport':'pending'}
    (ROOT/'apply-validation-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
    protected('apply-exit.json',b'{"exitCode":0}\n')

if __name__=='__main__':
    try:main()
    except BaseException:
        protected('apply-exit.json',b'{"exitCode":1}\n');raise
