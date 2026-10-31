#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fetch only the enumerated diagnostic evidence; exclude credentialed charts/values."""
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parent
DEST=ROOT/'remote-export'
assert not DEST.exists(), 'Retain the earlier snapshot instead of overwriting it.'
SSH=['ssh','-S','/private/tmp/mosaic-live-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','spark-user@spark.example.invalid']
CODE=r'''
import io,json,pathlib,sys,tarfile
r=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-protocol-20261031'
paths=[]
for directory in ['baseline-seeded','force-search-first','force-search-first-no-thinking','normalization','node-candidate','native-endpoints-revision14','native-ui-transcripts']:
 d=r/directory
 if d.exists():paths.extend(p for p in d.rglob('*') if p.is_file() and not p.is_symlink())
for name in ['all-named-wire-originals.private.tar.gz','node-candidate-audits.private.json.gz','node-candidate-provenance.json','node-candidate-launch.json','native-proxy-audit-revision14.private.json.gz','native-proxy-provenance-revision14.json','resources-after-normalization.json','parser-support.stdout.private','parser-support.stderr.private','vllm-serving-source-attempt2.private.json','vllm-serving-source.private.json','pod-before.json','case-observations.json','run-exit.json','controller.stdout.private','controller.stderr.private','named-wire-host.stdout.private','named-wire-host.stderr.private','named-wire-thinking-host.stdout.private','named-wire-thinking-host.stderr.private','named-wire-launch.json','llm-compat-candidate.mjs','llm-compat-fixed.mjs','llm-compat-candidate.yaml']:
 p=r/name
 if p.is_file():paths.append(p)
allowed=['prepare-summary.json','apply-exit.json','apply-validation-summary.json','apply-final-summary.json','startup-failure.json','startup-hotfix-summary.json','revision13-audit-empty.json','history-validation.json','history-final.json','application-secret-fingerprints-before.private.json','application-secret-fingerprints-validation.private.json','application-secret-fingerprints-final.private.json','apply-host.stderr.private','host.stderr.private','upgrade.stderr.private','lint.stdout.private','lint.stderr.private','preview.stderr.private']
for directory in ['persistent-compat','persistent-compat-attempt2','persistent-compat-attempt3','persistent-compat-final']:
 for name in allowed:
  p=r/directory/name
  if p.is_file():paths.append(p)
t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz')
for p in sorted(set(paths)):t.add(p,arcname=str(p.relative_to(r)))
t.close()
'''
raw=subprocess.check_output(SSH+['python3 -c '+shlex.quote(CODE)],timeout=180)
archive=ROOT/'complete-protocol-originals.private.tar.gz'
archive.write_bytes(raw);archive.chmod(0o600)
DEST.mkdir(mode=0o700)
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as t:t.extractall(DEST,filter='data')
manifest=[]
for path in sorted(DEST.rglob('*')):
    if path.is_dir():path.chmod(0o700)
    if path.is_file():
        path.chmod(0o600);data=path.read_bytes()
        manifest.append({'path':str(path.relative_to(DEST)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
summary={'archiveBytes':len(raw),'archiveSha256':hashlib.sha256(raw).hexdigest(),'files':manifest,
         'excluded':'All Helm values, manifests, full server renders, Secret values and real private child charts remain in protected Spark deployment directories. Complete model prompts/traces are included privately.'}
(ROOT/'remote-export-manifest.private.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'files':len(manifest),'archiveBytes':len(raw),'archiveSha256':summary['archiveSha256']}))
