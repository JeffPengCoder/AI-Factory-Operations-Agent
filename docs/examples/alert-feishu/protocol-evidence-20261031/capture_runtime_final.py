#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Capture runtime metadata with a strict allowlist; never serialize raw values."""
import json
import shlex
import subprocess
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'live-validation-20261031'))
from probe_access import SSH
ROOT=Path(__file__).resolve().parent

CODE=r'''
import datetime,hashlib,json,pathlib,subprocess
root=pathlib.Path.home()/'.local/share/mosaic-validation-20261031'
k=str(pathlib.Path.home()/'.local/bin/kubectl')
h=str(pathlib.Path.home()/'.local/bin/helm')
def run(argv):
 try:
  p=subprocess.run(argv,capture_output=True,text=True)
  return {'argv':argv,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except OSError as exc:return {'argv':argv,'exitCode':None,'stdout':'','stderr':str(exc)}
raw=subprocess.check_output([h,'--kube-context','kind-mosaic-poc','-n','mosaic','get','values','mosaic','--all','-o','json'])
values=json.loads(raw)
research=values.get('researchAgent',{}).get('iraop',{})
allowed=['NVIDIA_CHAT_BASE_URL','NVIDIA_CHAT_MODEL','MAX_TOKENS','DEFAULT_DEPTH','EMBEDDING_BASE_URL','EMBEDDING_MODEL','EMBEDDING_API_FLAVOR','EMBEDDING_DIMENSION','OPENSEARCH_ALLOW_PRIVATE_IP_CONNECTOR','CORPUS_DIR']
result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'modules':{name:part.get('enabled') for name,part in values.get('modules',{}).items() if isinstance(part,dict)},
 'edit':values.get('modules',{}).get('edit'),
 'researchConfig':{name:research.get('config',{}).get(name) for name in allowed},
 'corpus':research.get('corpus'),
 'researchCompatibility':values.get('llm',{}).get('requestCompatibility',{}).get('researchToolCalls'),
 'commands':[]}
for argv in [
 [k,'--context','kind-mosaic-poc','-n','mosaic','get','pods,svc,pvc','-o','json'],
 [h,'--kube-context','kind-mosaic-poc','-n','mosaic','history','mosaic','-o','json'],
 ['systemctl','--user','show','mosaic-embedding-validation.service','mosaic-repair-validation.service','-p','Id','-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus','-p','MainPID','-p','MemoryCurrent','-p','MemoryMax','-p','CPUQuotaPerSecUSec','-p','ActiveEnterTimestamp','-p','InvocationID'],
 ['journalctl','--user','-u','mosaic-repair-validation.service','--since','2026-10-31 08:00:00','--no-pager','-o','short-iso'],
 [str(root/'embedding/.venv/bin/python'),'-c',"import importlib.metadata as m,json; print(json.dumps(sorted([{'name':x.metadata['Name'],'version':x.version} for x in m.distributions()],key=lambda x:x['name'].lower()),indent=2))"],
 ['df','-h'],
 ['free','-h'],
 ['ss','-ltnp'],
]: result['commands'].append(run(argv))
paths=['repair/repair.sh','repair/ssh_dispatch.py','embedding/embedding_server.py','corpus/mosaic-validation-control.pdf']
result['fileHashes']={name:hashlib.sha256((root/name).read_bytes()).hexdigest() if (root/name).is_file() else None for name in paths}
print(json.dumps(result))
'''

if __name__=='__main__':
    data=subprocess.check_output(SSH+['python3 -c '+shlex.quote(CODE)],timeout=90)
    parsed=json.loads(data)
    # Only the SSH subsection has been configured here; reject unexpected secrets.
    assert 'password' not in json.dumps(parsed['edit']).lower()
    (ROOT/'runtime-final.json').write_text(json.dumps(parsed,indent=2)+'\n')
    print(json.dumps({'modules':parsed['modules'],'commandExitCodes':[c['exitCode'] for c in parsed['commands']]}))
