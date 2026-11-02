#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Inject only into a new private-socket DCGM core; stop exactly our own child."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SSH=['ssh','-S','/private/tmp/mosaic-gpu-rca-l20-root-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=15','root@target-node-1.example.invalid']
assert not (ROOT/'isolated-dcgm-attempt3-started.json').exists(), 'One-shot experiment; inspect previous attempt first.'
from datetime import datetime,timezone
(ROOT/'isolated-dcgm-attempt3-started.json').write_text(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'scope':'new child hostengine, private Unix socket only; no production cache injection, no GPU stress/reset/config writes'},indent=2)+'\n')
remote=r'''import os,json,subprocess,pathlib,time,xml.etree.ElementTree as E
from datetime import datetime,timezone
run='gpu-rca-20261031t121240z';directory=pathlib.Path('/var/tmp/mosaic-'+run+'-attempt3')
assert not directory.exists(),'Refuse to reuse an existing engine directory'
directory.mkdir(mode=0o700);socket=directory/'engine.sock';rows=[];child=None
def execute(argv,timeout=30,required=True):
 start=time.monotonic();p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 row={'at':datetime.now(timezone.utc).isoformat(),'argv':argv,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'elapsedSeconds':time.monotonic()-start};rows.append(row)
 if required and p.returncode:raise RuntimeError('Command failed: '+repr(argv))
 return p.stdout
result={'runId':run,'at':datetime.now(timezone.utc).isoformat(),'engineDirectory':str(directory),'physicalHardwareErrorInjected':False,'commands':rows}
try:
 assert execute(['hostname']).strip()=='target-node-1'
 apps=execute(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name,used_gpu_memory','--format=csv,noheader'])
 assert not apps.strip(),'Compute processes appeared; stop before any isolated engine launch'
 execute(['dcgmi','dmon','--host','127.0.0.1:5555','-i','0','-e','230,311,313','-c','2'])
 xml_before=execute(['nvidia-smi','-q','-x'])
 args=['nv-hostengine','--no-daemon','--domain-socket',str(socket),'--pid',str(directory/'engine.pid'),'--log-filename',str(directory/'engine.log'),'--denylist-modules','1,2,3,4,5,6,7,8,9']
 env=dict(os.environ);env['DCGM_ENABLE_INJECTION_APIS']='1'
 log=open(directory/'engine-stdio.log','w')
 child=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 result['child']={'pid':child.pid,'argv':args,'protectedOperationEnvironment':{'DCGM_ENABLE_INJECTION_APIS':'1'}}
 for _ in range(80):
  if child.poll() is not None:raise RuntimeError('Isolated engine exited before readiness')
  if socket.exists():break
  time.sleep(.25)
 else:raise TimeoutError('Private DCGM socket was not created')
 host='unix://'+str(socket)
 discovery=execute(['dcgmi','discovery','--host',host,'-l'],required=False)
 assert 'GPU-REDACTED-11' in discovery,'GPU identity not confirmed'
 execute(['dcgmi','dmon','--host',host,'-i','0','-e','230,311,313','-c','2'])
 for field,value in [('230','95'),('311','1'),('313','1')]:
  execute(['dcgmi','test','--host',host,'--inject','--gpuid','0','-f',field,'-v',value,'--offset','60'])
 for field in ['230','311','313']:
  execute(['dcgmi','test','--host',host,'--introspect','--gpuid','0','-f',field])
 execute(['dcgmi','dmon','--host',host,'-i','0','-e','230,311,313','-c','3'])
 execute(['dcgmi','dmon','--host','127.0.0.1:5555','-i','0','-e','230,311,313','-c','2'])
 xml_after=execute(['nvidia-smi','-q','-x'])
 def ecc(xml):
  root=E.fromstring(xml);return [{'uuid':g.findtext('uuid'),'ecc':{k.tag:{v.tag:v.text for v in k} for k in g.find('ecc_errors') if list(k)},'remappedRows':{x.tag:x.text for x in g.find('remapped_rows') if not list(x)}} for g in root.findall('gpu')]
 result['allEightGpuEccAndRemapBefore']=ecc(xml_before);result['allEightGpuEccAndRemapAfter']=ecc(xml_after)
 result['allEightGpuEccAndRemapUnchanged']=ecc(xml_before)==ecc(xml_after)
 assert result['allEightGpuEccAndRemapUnchanged'],'Unexpected baseline change, stop test'
 result['success']=True
except Exception as e:result.update(success=False,errorType=type(e).__name__,error=str(e))
finally:
 if child is not None:
  result['childExitBeforeCleanup']=child.poll()
  if child.poll() is None:
   child.terminate()
   try:child.wait(timeout=20)
   except subprocess.TimeoutExpired:child.kill();child.wait(timeout=10)
  result['childExitAfterCleanup']=child.returncode
  log.close()
 result['logs']={p.name:p.read_text(errors='replace') for p in directory.glob('*.log')}
 result['atCompleted']=datetime.now(timezone.utc).isoformat()
print(json.dumps(result,ensure_ascii=False))
if not result['success']:raise SystemExit(1)
'''
p=subprocess.run(SSH+['python3 -'],input=remote,text=True,capture_output=True,timeout=240)
(ROOT/'isolated-dcgm.private.stderr').write_text(p.stderr)
try:result=json.loads(p.stdout)
except ValueError:
 (ROOT/'isolated-dcgm-unparsed.private.stdout').write_text(p.stdout);raise
(ROOT/'isolated-dcgm.private.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'success':result.get('success'),'error':result.get('error'),'allEightGpuEccAndRemapUnchanged':result.get('allEightGpuEccAndRemapUnchanged'),'childExitAfterCleanup':result.get('childExitAfterCleanup'),'commandCount':len(result['commands'])}),flush=True)
assert p.returncode==0 and result['success']
