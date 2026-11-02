#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Resume post-upgrade checks without applying another Helm revision."""
from datetime import datetime, timezone
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-debug/query-guard-2'
K = [str(pathlib.Path.home()/'.local/bin/kubectl'), '--context', 'kind-mosaic-poc', '-n', 'mosaic']
H = [str(pathlib.Path.home()/'.local/bin/helm'), '--kube-context', 'kind-mosaic-poc', '-n', 'mosaic']

def get(args):
    return json.loads(subprocess.check_output(args))

def digest(data):
    return hashlib.sha256(data).hexdigest()

prepared = json.loads((ROOT/'prepare-summary.json').read_text())
history = get(H+['history', 'mosaic', '-o', 'json'])
assert history[-1]['revision'] == 11 and history[-1]['status'] == 'deployed'
cm = get(K+['get', 'cm', 'openclaw-seed', '-o', 'json'])
rendered = cm['data']['iraop.index.ts'].encode()
source = next(ROOT.glob('**/extensions/iraop/index.ts')).read_bytes()
assert digest(source) == prepared['pluginAfterSha256']
assert source.rstrip(b'\n') == rendered
deployment = get(K+['get', 'deploy', 'openclaw', '-o', 'json'])
selector = ','.join(k+'='+v for k, v in deployment['spec']['selector']['matchLabels'].items())
pods = get(K+['get', 'pods', '-l', selector, '-o', 'json'])['items']
ready = [p for p in pods if not p['metadata'].get('deletionTimestamp') and all(s['ready'] for s in p['status'].get('containerStatuses', [])) and p['status']['phase'] == 'Running']
assert len(ready) == 1
pod = ready[0]
script = 'const fs=require("fs"),c=require("crypto"),p="/home/node/.openclaw/extensions/iraop/index.ts",b=fs.readFileSync(p);console.log(JSON.stringify({path:p,bytes:b.length,sha256:c.createHash("sha256").update(b).digest("hex"),hasQueryEvidenceGuard:b.includes(Buffer.from("function queryEvidenceProblem"))}));'
loaded = get(K+['exec', '-c', 'gateway', pod['metadata']['name'], '--', 'node', '-e', script])
assert loaded['hasQueryEvidenceGuard'] and loaded['sha256'] == digest(rendered)
expected = {s['name']: {k: s[k] for k in ['type', 'keys', 'dataDigest']} for s in json.loads((ROOT/'application-secret-fingerprints-before.private.json').read_text())}
normal = {s['metadata']['name']: {'type': s.get('type'), 'keys': sorted(s.get('data', {})), 'dataDigest': digest(json.dumps(s.get('data', {}), sort_keys=True).encode())} for s in get(K+['get', 'secrets', '-o', 'json'])['items'] if s.get('type') != 'helm.sh/release.v1'}
changed = [name for name, value in expected.items() if normal.get(name) != value]
assert not changed
summary = {
    'at': datetime.now(timezone.utc).isoformat(), 'beforeRevision': 10, 'afterRevision': 11,
    'status': history[-1]['status'], 'chartVersion': prepared['chartVersionAfter'],
    'pluginSourceBytes': len(source), 'pluginSourceSha256': digest(source),
    'renderedBytes': len(rendered), 'renderedSha256': digest(rendered), 'plugin': loaded,
    'pod': {'name': pod['metadata']['name'], 'uid': pod['metadata']['uid'], 'createdAt': pod['metadata']['creationTimestamp'], 'containers': [{'name': s['name'], 'ready': s['ready'], 'restartCount': s['restartCount'], 'imageID': s['imageID']} for s in pod['status']['containerStatuses']]},
    'applicationSecretChanges': changed, 'applicationSecretsCompared': len(expected),
    'previousPostcheck': {'exitCode': 1, 'cause': 'Helm block scalar removed one final LF; the source and rendered hashes differ, but the live plugin matches the rendered ConfigMap exactly.', 'originalCheckPreserved': True},
    'additionalUpgradePerformed': False, 'nativeQueryValidation': 'pending',
    'scope': 'Original real chart, child dependencies, existing values and application credentials retained; IRAOP plugin source and chart build metadata changed.',
}
(ROOT/'apply-verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary))
