#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Download an immutable public ONNX embedding model for the local test."""
import hashlib
import json
from pathlib import Path
from huggingface_hub import HfApi, hf_hub_download

root = Path.home()/'.local/share/mosaic-validation-20261031/embedding'
repo = 'sentence-transformers/all-MiniLM-L6-v2'
info = HfApi().model_info(repo, token=False)
revision = info.sha
names = ['config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','vocab.txt','onnx/model.onnx']
available = {x.rfilename for x in info.siblings}
files = []
for name in names:
    if name not in available:
        if name in ['config.json','tokenizer.json','onnx/model.onnx']:
            raise RuntimeError('Required public model file missing: '+name)
        continue
    path = Path(hf_hub_download(repo, name, revision=revision, local_dir=root/'model', token=False))
    files.append({'file':name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
manifest = {'model':repo,'revision':revision,'provider':'CPUExecutionProvider','dimension':384,'maxTokens':256,'files':files}
(root/'model-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
