# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Reuse this experiment's verified Spark control connection; never store auth."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'live-validation-20261031'))
import probe_access
probe_access.SSH=['ssh','-S','/private/tmp/mosaic-gpu-spark-20261031/ssh.sock','-o','BatchMode=yes','-o','ConnectTimeout=20','spark-user@spark.example.invalid']
SSH=probe_access.SSH
BASE=probe_access.BASE
read_ui_credentials=probe_access.read_ui_credentials
request=probe_access.request
