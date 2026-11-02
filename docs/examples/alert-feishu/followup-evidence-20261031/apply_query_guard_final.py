#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Apply the reviewed, persistent IRAOP plugin-only chart backport."""
from datetime import datetime,timezone
import hashlib,json,pathlib,subprocess,time

ROOT=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-debug/query-guard-final'
HELM=[str(pathlib.Path.home()/'.local/bin/helm'),'--kube-context','kind-mosaic-poc','-n','mosaic']
K=[str(pathlib.Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
def private(name,data):
    p=ROOT/name;p.write_bytes(data);p.chmod(0o600)
def run(argv,name):
    started=time.monotonic();p=subprocess.run(argv,capture_output=True)
    private(name+'.stdout.private',p.stdout);private(name+'.stderr.private',p.stderr)
    assert p.returncode==0,{'stage':name,'exitCode':p.returncode,'detail':'See protected outputs'}
    return p.stdout,time.monotonic()-started
def history():return json.loads(subprocess.check_output(HELM+['history','mosaic','-o','json']))
def fingerprints():
    data=json.loads(subprocess.check_output(K+['get','secrets','-o','json']))['items']
    return {s['metadata']['name']:{'type':s.get('type'),'keys':sorted(s.get('data',{})),'dataDigest':hashlib.sha256(json.dumps(s.get('data',{}),sort_keys=True).encode()).hexdigest()} for s in data if s.get('type')!='helm.sh/release.v1'}

def main():
    prepared=json.loads((ROOT/'prepare-summary.json').read_text())
    assert prepared['baseRevision']==11 and prepared['existingSecretDataUnchangedInServerDryRun'] and prepared['noEditorBinding']
    current=history();assert current[-1]['revision']==11 and current[-1]['status']=='deployed'
    expected={s['name']:{k:s[k] for k in ['type','keys','dataDigest']} for s in json.loads((ROOT/'application-secret-fingerprints-before.private.json').read_text())}
    assert fingerprints()==expected,'Application credentials changed since preparation; re-review before upgrading.'
    raw,elapsed=run(HELM+['upgrade','mosaic',prepared['chartPath'],'-f',str(ROOT/'values-before.private.yaml'),'--atomic','--wait','--timeout','20m','-o','json'],'upgrade')
    release=json.loads(raw);assert release['info']['status']=='deployed'
    after=history();private('history-after.private.json',json.dumps(after,indent=2).encode()+b'\n')
    normal=fingerprints();private('application-secret-fingerprints-after.private.json',json.dumps(normal,indent=2).encode()+b'\n')
    changed=[name for name,value in expected.items() if normal.get(name)!=value]
    assert not changed,'Unexpected application Secret changes: '+','.join(changed)
    assert after[-1]['chart'].endswith(prepared['chartVersionAfter'])
    private('current-values.private.yaml',subprocess.check_output(HELM+['get','values','mosaic','-o','yaml']))
    private('current-manifest.private.yaml',subprocess.check_output(HELM+['get','manifest','mosaic']))
    pods=json.loads(subprocess.check_output(K+['get','pods','-o','json']))
    (ROOT/'pods-after.json').write_text(json.dumps(pods,indent=2)+'\n')
    script='const fs=require("fs"),crypto=require("crypto"); const p="/home/node/.openclaw/extensions/iraop/index.ts"; const t=fs.readFileSync(p); console.log(JSON.stringify({path:p,sha256:crypto.createHash("sha256").update(t).digest("hex"),hasQueryEvidenceGuard:t.includes(Buffer.from("function queryEvidenceProblem"))}));'
    plugin=json.loads(subprocess.check_output(K+['exec','-c','gateway','deploy/openclaw','--','node','-e',script]))
    (ROOT/'loaded-plugin.json').write_text(json.dumps(plugin,indent=2)+'\n')
    rendered=json.loads(subprocess.check_output(K+['get','cm','openclaw-seed','-o','json']))['data']['iraop.index.ts'].encode()
    assert plugin['sha256']==hashlib.sha256(rendered).hexdigest() and plugin['hasQueryEvidenceGuard']
    assert rendered==(ROOT/'chart/mosaic-stack/files/openclaw-seed/extensions/iraop/index.ts').read_bytes().rstrip(b'\n')
    summary={'at':datetime.now(timezone.utc).isoformat(),'beforeRevision':11,'afterRevision':after[-1]['revision'],'status':after[-1]['status'],'chartVersion':prepared['chartVersionAfter'],'elapsedSeconds':elapsed,'plugin':plugin,'applicationSecretChanges':changed,'applicationSecretsCompared':len(expected),'chartPath':prepared['chartPath'],'nativeQueryValidation':'pending','scope':'Original real chart/dependencies and existing values retained; only IRAOP plugin source and chart build metadata changed.'}
    (ROOT/'apply-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':
    try:
        main();(ROOT/'apply-exit.json').write_text('{"exitCode":0}\n')
    except BaseException:
        (ROOT/'apply-exit.json').write_text('{"exitCode":1}\n');raise
