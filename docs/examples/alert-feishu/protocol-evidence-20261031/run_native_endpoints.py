#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Detach-safe host driver; preserve complete native endpoint artifacts."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

BASE = Path.home()/'.local/share/mosaic-validation-20261031'
ROOT = BASE/'research-protocol-20261031/native-endpoints-revision14'
ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
ROOT.chmod(0o700)
K = [str(Path.home()/'.local/bin/kubectl'), '--context', 'kind-mosaic-poc', '-n', 'mosaic']
SOURCE = BASE/'native_endpoints_20261031.py'
POD_ROOT = '/tmp/mosaic-protocol-20261031/native-endpoints-revision14'

def protected(name, raw):
    p = ROOT/name
    p.write_bytes(raw)
    p.chmod(0o600)

def main():
    assert not (ROOT/'run-launch.json').exists(), 'Inspect the previous run before retrying.'
    applied = json.loads((ROOT.parent/'persistent-compat-attempt3/apply-validation-summary.json').read_text())
    assert applied['afterRevision'] == 14 and applied['status'] == 'deployed'
    pods = json.loads(subprocess.check_output(K+['get', 'pods', '-o', 'json']))['items']
    pod = next(p for p in pods if p['metadata']['name'].startswith('iraop-') and not p['metadata'].get('deletionTimestamp') and all(c['ready'] for c in p['status'].get('containerStatuses', [])))
    protected('run-launch.json', json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'pod': pod['metadata']['name'], 'uid': pod['metadata']['uid'], 'modelMonkeypatch': False}, indent=2).encode()+b'\n')
    install = 'import pathlib,sys; p=pathlib.Path("'+POD_ROOT+'/client.py"); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(sys.stdin.buffer.read())'
    p = subprocess.run(K+['exec', '-i', pod['metadata']['name'], '--', 'python', '-c', install], input=SOURCE.read_bytes(), capture_output=True)
    assert p.returncode == 0, p.stderr.decode()
    started = time.monotonic()
    p = subprocess.run(K+['exec', pod['metadata']['name'], '--', 'python', POD_ROOT+'/client.py', POD_ROOT+'/results'], capture_output=True, timeout=750)
    protected('process.stdout.private', p.stdout)
    protected('process.stderr.private', p.stderr)
    protected('host-result.json', json.dumps({'exitCode': p.returncode, 'elapsedSeconds': time.monotonic()-started}, indent=2).encode()+b'\n')
    exporter = 'import pathlib,sys,tarfile; r=pathlib.Path("'+POD_ROOT+'/results"); t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz"); [t.add(p,arcname=str(p.relative_to(r))) for p in sorted(r.rglob("*")) if p.is_file() and not p.is_symlink()];t.close()'
    raw = subprocess.check_output(K+['exec', pod['metadata']['name'], '--', 'python', '-c', exporter], timeout=90)
    protected('complete-originals.private.tar.gz', raw)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as t:
        t.extractall(ROOT, filter='data')
    for path in ROOT.rglob('*'):
        if path.is_file(): path.chmod(0o600)
    assert p.returncode == 0, 'Native endpoint client failed; all originals retained.'
    print((ROOT/'case-observations.json').read_text(), flush=True)

if __name__ == '__main__':
    main()
