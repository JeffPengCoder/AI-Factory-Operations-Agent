#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run on Spark. Provision a user service and a narrowly forced SSH key."""
from datetime import datetime, timezone
import base64
import json
from pathlib import Path
import shlex
import subprocess

root = Path.home()/'.local/share/mosaic-validation-20261031/repair'
root.mkdir(parents=True,exist_ok=True)
root.chmod(0o700)
unit_name = 'mosaic-repair-validation.service'
unit_path = Path.home()/'.config/systemd/user'/unit_name
if unit_path.exists():
    raise SystemExit('Fixture unit already exists; inspect before reprovisioning')

wrapper = root/'repair.sh'
wrapper.write_text(f'''#!/bin/sh
set -eu
[ "$#" -eq 0 ] || exit 64
/usr/bin/install -m 0600 /dev/null {root}/ready
/usr/bin/systemctl --user reset-failed {unit_name}
/usr/bin/systemctl --user start {unit_name}
/usr/bin/systemctl --user show {unit_name} -p ActiveState -p SubState -p Result -p ExecMainStatus -p InvocationID -p ActiveEnterTimestamp
/usr/bin/systemctl --user is-active --quiet {unit_name}
''')
wrapper.chmod(0o700)
unit_path.parent.mkdir(parents=True,exist_ok=True)
unit_path.write_text(f'''[Unit]
Description=MOSAIC isolated user-service repair validation

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/test -f {root}/ready
MemoryMax=64M
''')

dispatcher = root/'ssh_dispatch.py'
dispatcher.write_text('''#!/usr/bin/python3
from datetime import datetime, timezone
import json, os, pathlib, shlex, subprocess, sys
root = pathlib.Path(__file__).resolve().parent
unit = "mosaic-repair-validation.service"
allowed = {
 ("systemctl","status","--user",unit,"--no-pager"),
 ("journalctl","--user","-u",unit,"--no-pager","-n","50"),
 (str(root/"repair.sh"),),
}
os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/"+str(os.getuid()))
os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path="+os.environ["XDG_RUNTIME_DIR"]+"/bus")
argv = shlex.split(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
event = {"at":datetime.now(timezone.utc).isoformat(),"argv":argv,"allowed":tuple(argv) in allowed}
if event["allowed"]:
 p = subprocess.run(argv, capture_output=True, text=True)
 event.update(exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr)
else:
 event.update(exitCode=126,stdout="",stderr="Outside the isolated demo SSH scope")
with (root/"ssh-audit.jsonl").open("a") as f:f.write(json.dumps(event)+"\\n")
print(json.dumps(event))
sys.exit(event["exitCode"])
''')
dispatcher.chmod(0o700)

key = root/'client_ed25519'
subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','mosaic-validation-20261031','-f',str(key)],check=True)
public = key.with_suffix('.pub').read_text().strip()
ssh_dir = Path.home()/'.ssh'
ssh_dir.mkdir(exist_ok=True)
authorized = ssh_dir/'authorized_keys'
old = authorized.read_bytes() if authorized.exists() else b''
(root/'authorized_keys.before').write_bytes(old)
line = f'restrict,command="{dispatcher}" {public}\n'
with authorized.open('ab') as f:
    if old and not old.endswith(b'\n'):f.write(b'\n')
    f.write(line.encode())
authorized.chmod(0o600)
(root/'installed-authorized-key-line.txt').write_text(line)

host_key = Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()[1]
scan = subprocess.run(['ssh-keyscan','-p','22','-t','ed25519','spark-kind-bridge.example.invalid'],capture_output=True,text=True,check=True)
lines = [x for x in scan.stdout.splitlines() if x and not x.startswith('#')]
assert lines and all(x.split()[2] == host_key for x in lines)
known_hosts = root/'known_hosts'
known_hosts.write_text('\n'.join(lines)+'\n')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
start = subprocess.run(['systemctl','--user','start',unit_name],capture_output=True,text=True)
state = subprocess.run(['systemctl','--user','show',unit_name,'-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus','-p','InvocationID','-p','ActiveEnterTimestamp'],capture_output=True,text=True,check=True)
assert start.returncode != 0 and 'ActiveState=failed' in state.stdout

base_ssh = ['ssh','-i',str(key),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known_hosts),'spark-user@spark-kind-bridge.example.invalid']
status = subprocess.run(base_ssh+[shlex.join(['systemctl','status','--user',unit_name,'--no-pager'])],capture_output=True,text=True)
status_event=json.loads(status.stdout)
assert status_event['allowed'] and 'failed' in status_event['stdout']
denied = subprocess.run(base_ssh+[shlex.join(['touch',str(root/'must-not-exist')])],capture_output=True,text=True)
assert denied.returncode == 126 and not (root/'must-not-exist').exists()

k=['/home/spark-user/.local/bin/kubectl','--context','kind-mosaic-poc','-n','mosaic']
check=subprocess.run(k+['get','secret','mosaic-validation-ssh','-o','name'],capture_output=True,text=True)
if check.returncode == 0:raise SystemExit('Unexpected existing SSH Secret; inspect before replacing')
secret={'apiVersion':'v1','kind':'Secret','metadata':{'name':'mosaic-validation-ssh','namespace':'mosaic'},'type':'Opaque','data':{'privateKey':base64.b64encode(key.read_bytes()).decode(),'knownHosts':base64.b64encode(known_hosts.read_bytes()).decode()}}
subprocess.run(k+['apply','-f','-'],input=json.dumps(secret),capture_output=True,text=True,check=True)
evidence={'at':datetime.now(timezone.utc).isoformat(),'unit':unit_name,'initialStart':{'exitCode':start.returncode,'stdout':start.stdout,'stderr':start.stderr},'initialState':state.stdout,'restrictedSshStatus':{'exitCode':status.returncode,'event':status_event},'outOfScopeDenied':{'exitCode':denied.returncode,'stdout':denied.stdout,'stderr':denied.stderr,'unexpectedFileExists':False},'sshSecret':'mosaic/mosaic-validation-ssh','forcedCommand':str(dispatcher),'allowedArgv':[list(x) for x in [("systemctl","status","--user",unit_name,"--no-pager"),("journalctl","--user","-u",unit_name,"--no-pager","-n","50"),(str(wrapper),)]]}
(root/'provision-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({'fixture':'failed as expected','restrictedSsh':'passed','outOfScope':'denied','secret':'mosaic-validation-ssh'}))
