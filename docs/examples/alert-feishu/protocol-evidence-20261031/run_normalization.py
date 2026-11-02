#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run paired read-only research experiments detached on Spark."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

ROOT=Path.home()/'.local/share/mosaic-validation-20261031/research-protocol-20261031/normalization'
ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
ROOT.chmod(0o700)
K=[str(Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
SOURCE=Path.home()/'.local/share/mosaic-validation-20261031/trace_normalization_20261031.py'
assert SOURCE.is_file()
assert not (ROOT/'run-exit.json').exists(), 'Inspect completed records rather than overwrite them.'
POD_ROOT='/tmp/mosaic-protocol-20261031/normalization'

def protected(path,raw):
    path.write_bytes(raw);path.chmod(0o600)

def main():
    pods=json.loads(subprocess.check_output(K+['get','pods','-o','json']))['items']
    pod=next(p for p in pods if p['metadata']['name'].startswith('iraop-') and p['status']['phase']=='Running' and not p['metadata'].get('deletionTimestamp'))
    pod_name=pod['metadata']['name']
    protected(ROOT/'pod-before.json',json.dumps({'name':pod_name,'uid':pod['metadata']['uid'],'containerStatuses':pod['status']['containerStatuses']},indent=2).encode()+b'\n')
    install='import pathlib,sys; p=pathlib.Path("'+POD_ROOT+'/trace_protocol.py"); p.parent.mkdir(exist_ok=True); p.write_bytes(sys.stdin.buffer.read())'
    p=subprocess.run(K+['exec','-i',pod_name,'--','python','-c',install],input=SOURCE.read_bytes(),capture_output=True)
    assert p.returncode==0,p.stderr.decode()
    results=[]
    for label,mode,seed in [('baseline','baseline-seeded',101),('normalized-101','normalize-first-search',101),('normalized-202','normalize-first-search',202)]:
        case=ROOT/label
        assert not case.exists(),str(case)
        case.mkdir(mode=0o700)
        started=time.monotonic()
        p=subprocess.run(K+['exec',pod_name,'--','python',POD_ROOT+'/trace_protocol.py',POD_ROOT+'/'+label,mode,str(seed)],capture_output=True,timeout=300)
        protected(case/'process.stdout.private',p.stdout);protected(case/'process.stderr.private',p.stderr)
        metadata={'at':datetime.now(timezone.utc).isoformat(),'mode':mode,'case':label,'seed':seed,'hostElapsedSeconds':time.monotonic()-started,'exitCode':p.returncode}
        exporter='import pathlib,sys,tarfile; root=pathlib.Path("'+POD_ROOT+'/'+label+'"); t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz"); [(t.add(p,arcname=str(p.relative_to(root)))) for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()]; t.close()'
        archive=subprocess.check_output(K+['exec',pod_name,'--','python','-c',exporter],timeout=90)
        protected(case/'complete-originals.private.tar.gz',archive)
        with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as t:t.extractall(case,filter='data')
        for path in case.rglob('*'):
            if path.is_file():path.chmod(0o600)
        summary_path=case/'trace-summary.json'
        if summary_path.exists():
            summary=json.loads(summary_path.read_text())
            metadata.update({k:summary.get(k) for k in ['elapsedSeconds','messageCount','toolEvents']})
            answer=summary.get('answer','')
            metadata.update({'sourceCount':len(summary.get('sources',[])),'sourceSinkCount':len(summary.get('sourceSink',[])),'answerContainsOracle':'CEDAR-NEBULA-E720C8C9' in answer,'answerHasSourceFilename':'mosaic-validation-control.pdf' in answer})
        protected(case/'host-observation.json',json.dumps(metadata,indent=2).encode()+b'\n')
        results.append(metadata)
        protected(ROOT/'case-observations.json',json.dumps(results,indent=2).encode()+b'\n')
        print(json.dumps({k:v for k,v in metadata.items() if k!='toolEvents'}),flush=True)
    protected(ROOT/'run-exit.json',b'{"exitCode":0}\n')

if __name__=='__main__':
    try:main()
    except BaseException:
        protected(ROOT/'run-exit.json',b'{"exitCode":1}\n');raise
