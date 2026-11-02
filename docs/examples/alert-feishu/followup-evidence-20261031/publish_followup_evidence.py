#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Publish complete selected follow-up records with explicit privacy redactions."""
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'live-validation-20261031'))
from probe_access import SSH

ROOT = Path(__file__).resolve().parent
DEST = Path('/private/tmp/afoa-spark-alert-runbook-20261030/docs/examples/alert-feishu/followup-evidence-20261031')
records = {}
field_redactions = {}

def add(path, name=None, raw=None):
    assert path.is_file(), path
    records[name or str(path.relative_to(ROOT))] = (path, path.read_bytes() if raw is None else raw)

for directory in ['approval-timeout', 'iraop-restart', 'query-guard-2', 'query-guard-final', 'query-guard-ui', 'alerts-restored']:
    for p in (ROOT/directory).iterdir():
        if p.is_file() and '.private.' not in p.name and p.suffix in {'.json', '.jsonl', '.log', '.diff', '.stderr'}:
            add(p)
add(ROOT/'query-guard-ui/after.txt')
for name in ['vllm-flags', 'vllm-container-profile', 'tokenizer-generation']:
    add(ROOT/(name+'.private.json'), name+'.json')
for directory in ['baseline', 'direct-no-thinking-1', 'temperature-zero-1', 'guided-search-1']:
    for name in ['metadata.json', 'direct-hybrid-search.json', 'trace-summary.json']:
        add(ROOT/directory/name)
    p = ROOT/directory/'agent-state.private.json'
    state = json.loads(p.read_text())
    assert all(m.get('type') in ['human', 'ai', 'tool'] for m in state['messages'])
    assert state.get('files') == {}, 'Review any virtual-filesystem contents before publishing.'
    add(p, directory+'/agent-state.json')
for p in (ROOT/'replay').iterdir():
    if '.private.' not in p.name and p.suffix in {'.json', '.sse'}:
        add(p)
p = ROOT/'raw/raw-summary.json'
raw_summary = json.loads(p.read_text())
for choice in raw_summary['response']['choices']:
    if choice.get('prompt_token_ids') is not None:
        assert len(choice['prompt_token_ids']) == 7893
        choice['prompt_token_ids'] = '[PRIVATE: all 7893 input token IDs retained in the internal original; they encode proprietary system prompts]'
field_redactions['raw/raw-summary.json'] = ['response.choices[*].prompt_token_ids: complete input preserved privately; all generated token IDs and all other fields retained.']
add(p, raw=json.dumps(raw_summary, ensure_ascii=False, indent=2).encode()+b'\n')
for p in ROOT.iterdir():
    if not p.is_file() or '.private.' in p.name or p.name in {'STATUS.md', 'followup-publication-summary.json'}:
        continue
    if p.suffix in {'.py', '.diff', '.log', '.json', '.jsonl'} or p.name.endswith('-prompt.txt'):
        add(p)
for name in ['after-query-guard-check', 'after-query-guard-restored', 'after-final-guard-old-tunnel', 'after-final-guard-restored']:
    add(ROOT.parent/'live-validation-20261031'/(name+'.json'), 'access/'+name+'.json')

# Read current Secret material into memory only. Never save the result, values,
# headers or the substitution map. Match both decoded and encoded forms.
secret_reader = "import json,pathlib,subprocess; k=str(pathlib.Path.home()/'.local/bin/kubectl'); d=json.loads(subprocess.check_output([k,'--context','kind-mosaic-poc','-n','mosaic','get','secrets','-o','json'])); print(json.dumps({'items':[s for s in d['items'] if s.get('type')!='helm.sh/release.v1']}))"
secret_raw = subprocess.check_output(SSH+['python3 -c '+shlex.quote(secret_reader)], timeout=30)
secrets = []
for secret in json.loads(secret_raw)['items']:
    if secret.get('type') == 'helm.sh/release.v1':
        continue
    for key, encoded in secret.get('data', {}).items():
        label = secret['metadata']['name']+'/'+key
        for value in [encoded, base64.b64decode(encoded).decode(errors='ignore')]:
            if len(value) >= 12:
                secrets.append((label, value))
secret_raw = None
secrets.sort(key=lambda pair: len(pair[1]), reverse=True)

ip_pattern = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')
ip_map = {}
for _, raw in records.values():
    for match in ip_pattern.finditer(raw.decode()):
        try: ip = ipaddress.ip_address(match.group())
        except ValueError: continue
        if ip.is_private and not ip.is_loopback and str(ip) != '0.0.0.0':
            ip_map[str(ip)] = ''
ip_map = {ip: f'followup-private-address-{i:02d}.example.invalid' for i, ip in enumerate(sorted(ip_map, key=ipaddress.ip_address), 1)}
ip_map.update({'spark.example.invalid': 'spark.example.invalid', 'target-node-1.example.invalid': 'target-node-1.example.invalid', 'target-node-2.example.invalid': 'target-node-2.example.invalid', 'spark-kind-bridge.example.invalid': 'spark-kind-bridge.example.invalid'})
replacements = {'/Users/operator': '/Users/operator', '/home/spark-user': '/home/spark-user', 'spark-user@': 'spark-user@', 'spark-host': 'spark-host', 'target-node-1': 'target-node-1', 'target-node-2': 'target-node-2', 'target-lab': 'target-lab', 'NGC_ORG_ID': 'NGC_ORG_ID', '"user": "spark-user"': '"user": "spark-user"'}
manifest, secret_counts = [], {}
DEST.mkdir(parents=True, exist_ok=True)
for name, (source, raw) in sorted(records.items()):
    text = raw.decode()
    for label, value in secrets:
        count = text.count(value)
        if count:
            secret_counts.setdefault(name, {})[label] = count
            text = text.replace(value, '[REDACTED_CREDENTIAL]')
    for before, after in replacements.items():
        text = text.replace(before, after)
    text = re.sub(r'\bjepeng\b', 'operator', text)
    text = ip_pattern.sub(lambda match: ip_map.get(match.group(), match.group()), text)
    data = text.encode()
    if source.suffix == '.py' and b'SPDX-License-Identifier:' not in b'\n'.join(data.splitlines()[:5]):
        header = b'# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n# SPDX-License-Identifier: Apache-2.0\n'
        if data.startswith(b'#!'):
            first, rest = data.split(b'\n', 1)
            data = first+b'\n'+header+rest
        else:
            data = header+data
    target = DEST/name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    original = source.read_bytes()
    manifest.append({'path': name, 'originalBytes': len(original), 'originalSha256': hashlib.sha256(original).hexdigest(), 'publishedBytes': len(data), 'publishedSha256': hashlib.sha256(data).hexdigest(), 'changed': original != data, 'explicitFieldRedactions': field_redactions.get(name, []), 'credentialRedactions': secret_counts.get(name, {})})
policy = {
    'scope': 'Complete selected follow-up outputs, all direct-search hits and scores, every selected message/tool result, all generated output token IDs, full comparison responses, failure attempts, actual scripts and patches. The tables in the companion document are additional summaries.',
    'redactions': ['Private addresses, actual OS/SSH account/hostnames and private registry organization replaced consistently.', 'Actual Secret values scanned in memory only; matches, if any, replaced and counted per file.', 'Raw completion input token IDs encode proprietary system prompts and are explicitly replaced. All 32 generated output token IDs remain.'],
    'excludedFromPublic': ['Credentials, raw Helm values/manifests/server render and private child-chart package stay on Spark under protected permissions.', 'Complete agent event/request traces, original raw-completion inputs and tokenizer IDs include proprietary system prompts and remain in the internal evidence bundle.', 'Whole browser DOM/screenshots, full all-alert snapshots and unrelated private events stay in the internal bundle. Complete selected query page text, selected test alert and session/tool records are included.'],
    'files': manifest,
}
(DEST/'manifest.json').write_text(json.dumps(policy, indent=2)+'\n')
(ROOT/'followup-publication-summary.json').write_text(json.dumps({'files': len(manifest), 'publishedBytes': sum(x['publishedBytes'] for x in manifest), 'credentialRedactions': secret_counts}, indent=2)+'\n')
print(json.dumps({'files': len(manifest), 'publishedBytes': sum(x['publishedBytes'] for x in manifest), 'credentialRedactions': secret_counts}))
