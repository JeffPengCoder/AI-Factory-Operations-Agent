#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Publish full selected protocol evidence with explicit private-source exclusions."""
import base64,hashlib,ipaddress,json,re,shlex,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'live-validation-20261031'))
from probe_access import SSH
ROOT=Path(__file__).resolve().parent
DEST=Path('/private/tmp/afoa-spark-alert-runbook-20261030/docs/examples/alert-feishu/protocol-evidence-20261031')
records={};field_redactions={}
def add(path,name=None,raw=None):
 assert path.is_file(),path
 key=name or str(path.relative_to(ROOT))
 assert key not in records,key
 records[key]=(path,path.read_bytes() if raw is None else raw)
R=ROOT/'remote-export'
for directory in ['baseline-seeded','force-search-first','force-search-first-no-thinking']:
 for name in ['metadata.json','direct-hybrid-search.json','trace-summary.json','agent-state.private.json','host-observation.json','request-observations.json','process.stdout.private','process.stderr.private']:
  src=R/directory/name
  if src.exists():add(src,'agent-cases/'+directory+'/'+name.replace('.private',''))
for parent in ['normalization','node-candidate']:
 for case in (R/parent).iterdir():
  if not case.is_dir():continue
  for name in ['metadata.json','direct-hybrid-search.json','trace-summary.json','agent-state.private.json','host-observation.json','request-observations.json','process.stdout.private','process.stderr.private','trace-error.json']:
   src=case/name
   if src.exists():add(src,parent+'/'+case.name+'/'+name.replace('.private',''))
 for name in ['case-observations.json','run-exit.json','pod-before.json']:
  src=R/parent/name
  if src.exists():add(src,parent+'/'+name)
for src in (ROOT/'named-wire-originals').rglob('*'):
 if not src.is_file() or '-request.private.json' in src.name:continue
 name=str(src.relative_to(ROOT/'named-wire-originals')).replace('-response.private','-response.raw')
 add(src,name)
for src in (R/'native-endpoints-revision14').rglob('*'):
 if not src.is_file() or src.name.endswith('.tar.gz'):continue
 if src.name in ['host.stdout.private','host.stderr.private','process.stdout.private','process.stderr.private']:
  add(src,'native-endpoints-revision14/'+src.name.replace('.private',''))
 elif '.private' not in src.name:add(src,'native-endpoints-revision14/'+src.name)
for directory in ['native-ui','native-ui-attempt2','native-alert-research-revision15','alerts-restored-final']:
 for src in (ROOT/directory).iterdir():
  if src.is_file() and '.private.' not in src.name and src.suffix in {'.json','.jsonl','.log'}:
   add(src)
for src in (R/'native-ui-transcripts').iterdir():
 if src.is_file() and (src.suffix=='.jsonl' or src.name=='manifest.json'):
  add(src,'native-ui-transcripts/'+src.name)
for directory in ['persistent-compat','persistent-compat-attempt2','persistent-compat-attempt3','persistent-compat-final']:
 if not (R/directory).exists():continue
 for src in (R/directory).iterdir():
  if src.name in ['prepare-summary.json','apply-exit.json','apply-validation-summary.json','apply-final-summary.json','startup-failure.json','startup-hotfix-summary.json','revision13-audit-empty.json','history-validation.json','history-final.json','apply-host.stderr.private','host.stderr.private','upgrade.stderr.private','lint.stdout.private','lint.stderr.private','preview.stderr.private']:
   add(src,directory+'/'+src.name.replace('.private',''))
for name in ['node-candidate-provenance.json','node-candidate-launch.json','native-proxy-provenance-revision14.json','resources-after-normalization.json','parser-support.stdout.private','parser-support.stderr.private','case-observations.json','run-exit.json','pod-before.json','controller.stdout.private','controller.stderr.private','named-wire-host.stdout.private','named-wire-host.stderr.private','named-wire-thinking-host.stdout.private','named-wire-thinking-host.stderr.private','named-wire-launch.json','llm-compat-candidate.mjs','llm-compat-fixed.mjs','llm-compat-candidate.yaml']:
 add(R/name,'remote-metadata/'+name.replace('.private',''))
for src in ROOT.iterdir():
 if not src.is_file() or '.private.' in src.name or src.name in ['STATUS.md','protocol-publication-summary.json','publish-protocol-evidence-attempt2.log','native-proxy-provenance-export.log']:continue
 if src.suffix in {'.py','.diff','.log','.json'}:
  add(src)
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
ip_map = {ip: f'protocol-private-address-{i:02d}.example.invalid' for i, ip in enumerate(sorted(ip_map, key=ipaddress.ip_address), 1)}
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
    'scope': 'Complete selected protocol outputs, all direct-search hits/scores, every selected message/tool result, all named-wire response bytes, native endpoint responses, provenance rows, failure attempts, actual scripts and patches. The tables in the companion document are additional summaries.',
    'redactions': ['Private addresses, actual OS/SSH account/hostnames and private registry organization replaced consistently.', 'Actual Secret values scanned in memory only; matches, if any, replaced and counted per file.', 'Full original/forwarded model request bodies and agent event traces include proprietary system prompts and are retained in the private archive. Selected generated answers/messages, complete wire response bytes and all runtime result fields remain public after identity/credential redaction.'],
    'excludedFromPublic': ['Credentials, raw Helm values/manifests/server render and private child-chart package stay on Spark under protected permissions.', 'Complete agent event/request traces, original raw-completion inputs and tokenizer IDs include proprietary system prompts and remain in the internal evidence bundle.', 'Whole browser DOM/screenshots, full all-alert snapshots and unrelated private events stay in the internal bundle. The full selected test alert and complete selected session/tool records are included; unrelated page content stays private.'],
    'files': manifest,
}
(DEST/'manifest.json').write_text(json.dumps(policy, indent=2)+'\n')
(ROOT/'protocol-publication-summary.json').write_text(json.dumps({'files': len(manifest), 'publishedBytes': sum(x['publishedBytes'] for x in manifest), 'credentialRedactions': secret_counts}, indent=2)+'\n')
print(json.dumps({'files': len(manifest), 'publishedBytes': sum(x['publishedBytes'] for x in manifest), 'credentialRedactions': secret_counts}))
