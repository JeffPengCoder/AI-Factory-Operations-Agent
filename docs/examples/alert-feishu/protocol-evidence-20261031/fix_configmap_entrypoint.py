#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Repair only the verified CLI symlink difference during the pending upgrade."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

PARENT=Path.home()/'.local/share/mosaic-validation-20261031/research-protocol-20261031'
ROOT=PARENT/'persistent-compat-attempt2'
K=[str(Path.home()/'.local/bin/kubectl'),'--context','kind-mosaic-poc','-n','mosaic']
assert not (ROOT/'startup-hotfix-summary.json').exists()
cm=json.loads(subprocess.check_output(K+['get','cm','llm-openai-compat','-o','json']))
old=cm['data']['server.mjs'].encode()
new=(PARENT/'llm-compat-fixed.mjs').read_bytes()
assert hashlib.sha256(old).hexdigest()==json.loads((ROOT/'prepare-summary.json').read_text())['renderedProxySha256']
assert new.replace(b"import { realpathSync } from 'node:fs';\n",b'').replace(b'realpathSync(resolve(process.argv[1]))',b'resolve(process.argv[1])')==old
backup=ROOT/'configmap-before-startup-hotfix.private.json'
backup.write_text(json.dumps(cm,indent=2)+'\n');backup.chmod(0o600)
cm['data']['server.mjs']=new.decode()
raw=subprocess.check_output(K+['replace','-f','-'],input=json.dumps(cm).encode())
subprocess.check_call(K+['delete','pod','llm-openai-compat-54dcdf8ffc-87l6q','--wait=false'])
summary={'at':datetime.now(timezone.utc).isoformat(),
         'scope':'Correct CLI realpath detection while Helm waits; persist the same correction in the next real chart upgrade.',
         'beforeSha256':hashlib.sha256(old).hexdigest(),'afterSha256':hashlib.sha256(new).hexdigest(),
         'replacedFailedPod':'llm-openai-compat-54dcdf8ffc-87l6q','sharedModelChanged':False,'replaceOutput':raw.decode()}
(ROOT/'startup-hotfix-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
