#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fetch an explicit allowlist; never copy values, manifests or render output."""
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'live-validation-20261031'))
from probe_access import SSH

ROOT = Path(__file__).resolve().parent
remote = r'''
import base64,hashlib,json,pathlib
r=pathlib.Path.home()/'.local/share/mosaic-validation-20261031/research-debug'
allowed={
 'query-guard-2':['prepare-summary.json','apply-exit.json','loaded-plugin.json','apply-host.stderr','apply-verification-summary.json','native-tool-results.jsonl'],
 'query-guard-final':['prepare-summary.json','apply-exit.json','apply-summary.json','loaded-plugin.json','apply-host.stderr','history-after.private.json','native-tool-results.jsonl','final-vs-original.diff','final-vs-revision11.diff'],
}
out={}
for directory,names in allowed.items():
 for name in names:
  p=r/directory/name
  if p.is_file():
   raw=p.read_bytes();out[directory+'/'+name.replace('.private.','.')]= {'base64':base64.b64encode(raw).decode(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
print(json.dumps(out))
'''
data = json.loads(subprocess.check_output(SSH+['python3 -c '+shlex.quote(remote)], timeout=90))
manifest = []
for name, meta in data.items():
    raw = base64.b64decode(meta.pop('base64'))
    assert len(raw) == meta['bytes'] and hashlib.sha256(raw).hexdigest() == meta['sha256']
    target = ROOT/name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    manifest.append({'path': name, **meta})
(ROOT/'guard-fetch-manifest.private.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(json.dumps({'files': len(manifest), 'bytes': sum(x['bytes'] for x in manifest)}))
