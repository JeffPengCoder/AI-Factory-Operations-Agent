#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Private live-validation recorder. Credentials are used in memory only."""

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parent
SPARK = "spark-user@spark.example.invalid"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", SPARK]
CONTROL = Path('/private/tmp/mosaic-live-20261031/ssh.sock')
if CONTROL.exists():
    SSH = ["ssh", "-S", str(CONTROL), "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", SPARK]
BASE = "http://127.0.0.1:13000"


def command(argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    return {"argv": argv, "exitCode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}


def request(path, auth=None):
    started = time.monotonic()
    headers = {"Authorization": "Basic " + auth} if auth else {}
    req = urllib.request.Request(BASE + path, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=12) as r:
            status, body = r.status, r.read().decode()
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read().decode()
    except (OSError, urllib.error.URLError) as exc:
        return {"path": path, "httpStatus": None, "error": str(exc), "elapsedSeconds": time.monotonic()-started}
    try:
        body = json.loads(body)
    except ValueError:
        pass
    return {"path": path, "httpStatus": status, "body": body, "elapsedSeconds": time.monotonic()-started}


def read_ui_credentials():
    raw = subprocess.check_output(SSH + [
        "$HOME/.local/bin/kubectl --context kind-mosaic-poc -n mosaic get secret mosaic-ui-auth -o json"
    ])
    data = json.loads(raw)["data"]
    return {key: base64.b64decode(data[key]).decode() for key in ("username", "password")}


def main():
    phase = sys.argv[1]
    if not re.fullmatch(r"[a-z0-9-]+", phase):
        raise SystemExit("Invalid phase")
    result = {"phase": phase, "checkedAt": datetime.now(timezone.utc).isoformat()}
    result["localListener"] = command(["lsof", "-nP", "-iTCP:13000", "-sTCP:LISTEN"])
    result["sparkListener"] = command(SSH + ['ss -ltnp "( sport = :13000 )"'])
    result["health"] = request("/api/health")
    result["unauthenticatedApi"] = request("/api/alerts/alertmanager")
    if result["unauthenticatedApi"]["httpStatus"] is not None:
        credentials = read_ui_credentials()
        auth = base64.b64encode((credentials["username"] + ":" + credentials["password"]).encode()).decode()
        result["authenticatedApi"] = request("/api/alerts/alertmanager", auth)
    path = ROOT / (phase + ".json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "phase": phase,
        "localListenerExit": result["localListener"]["exitCode"],
        "remoteHasListener": "kubectl" in result["sparkListener"]["stdout"],
        "healthHttp": result["health"]["httpStatus"],
        "unauthenticatedApiHttp": result["unauthenticatedApi"]["httpStatus"],
        "authenticatedApiHttp": result.get("authenticatedApi", {}).get("httpStatus"),
        "evidence": str(path),
    }))


if __name__ == "__main__":
    main()
