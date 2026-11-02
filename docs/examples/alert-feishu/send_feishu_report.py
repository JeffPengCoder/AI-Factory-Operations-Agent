#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prepare a full alert + reviewed analysis; send only with explicit --send.

This operator example is independent of the OpenClaw Feishu channel. It does not
watch alerts, start investigations, retry deliveries, or upload evidence files.
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


# Feishu documents a 20 KB request limit. Use 20,000 bytes conservatively.
MAX_BYTES = 20_000


def signature(timestamp, secret):
    key = f"{timestamp}\n{secret}".encode("utf-8")
    return base64.b64encode(hmac.new(key, b"", hashlib.sha256).digest()).decode("ascii")


def make_payload(alert, analysis, session_key, run_id, evidence_url=""):
    if not isinstance(alert, dict) or not alert.get("id") or not alert.get("payload"):
        raise ValueError("alert must be one full MOSAIC alert object with id and payload")
    if not analysis.strip() or not session_key.strip() or not run_id.strip():
        raise ValueError("analysis, session key and run ID are required")
    if evidence_url:
        url = urllib.parse.urlparse(evidence_url)
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            raise ValueError("evidence URL must be an HTTP(S) link without embedded credentials")
    text = (
        "MOSAIC alert investigation | test from Jeff Peng\n"
        f"Run ID: {run_id}\nSession: {session_key}\n"
        f"Alert ID: {alert['id']}\n\n"
        "Alert (complete JSON):\n"
        + json.dumps(alert, ensure_ascii=False, indent=2)
        + "\n\nAnalysis (complete reviewed text):\n"
        + analysis
        + (f"\n\nFull evidence: {evidence_url}\n" if evidence_url else "")
    )
    return {"msg_type": "text", "content": {"text": text}}


def encode_payload(payload, secret="", timestamp=None):
    body = dict(payload)
    if secret:
        stamp = int(time.time()) if timestamp is None else timestamp
        body.update(timestamp=str(stamp), sign=signature(stamp, secret))
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise ValueError(
            f"payload is {len(encoded)} bytes; limit is {MAX_BYTES}. Nothing was sent or truncated. "
            "Retain the full evidence and use an approved artifact/file delivery route."
        )
    return encoded


def validate_webhook(webhook):
    url = urllib.parse.urlparse(webhook)
    if (
        url.scheme != "https"
        or url.hostname not in {"open.feishu.cn", "open.larksuite.com"}
        or url.port not in {None, 443}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or not url.path.startswith("/open-apis/bot/v2/hook/")
        or not url.path.removeprefix("/open-apis/bot/v2/hook/")
    ):
        raise ValueError("expected an official Feishu/Lark custom-bot HTTPS webhook")


def require_success(response):
    # Do not interpret HTTP 200 or a missing status field as delivery success.
    if not isinstance(response, dict):
        raise ValueError("bot response is not a JSON object")
    codes = [response[k] for k in ("code", "StatusCode") if k in response]
    if not codes or any(type(code) is not int or code != 0 for code in codes):
        raise ValueError("bot rejected the message or returned an unknown status; inspect response file")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("webhook redirected; request was not forwarded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alert", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--session-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--evidence-url", default="")
    parser.add_argument("--output", required=True, type=Path, help="unsigned payload for review")
    parser.add_argument("--send", action="store_true", help="actually deliver the reviewed report")
    parser.add_argument("--response", type=Path, help="required with --send; save full bot JSON response")
    args = parser.parse_args()
    if args.send and not args.response:
        parser.error("--send requires --response")
    payload = make_payload(
        json.loads(args.alert.read_text(encoding="utf-8")),
        args.analysis.read_text(encoding="utf-8"),
        args.session_key, args.run_id, args.evidence_url,
    )
    # Always retain the complete unsigned report, including when it is too big.
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    encoded = encode_payload(payload)
    print(f"Review payload: {args.output} ({len(encoded)} UTF-8 bytes before signing)")
    if not args.send:
        print("Dry run: no network request made.")
        return
    webhook = os.environ.get("FEISHU_WEBHOOK") or getpass.getpass("Feishu bot webhook (hidden): ")
    secret = os.environ.get("FEISHU_SIGNING_SECRET")
    if secret is None:
        secret = getpass.getpass("Feishu signing secret (hidden; Enter if bot has none): ")
    validate_webhook(webhook)
    encoded = encode_payload(payload, secret)
    request = urllib.request.Request(webhook, data=encoded, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        args.response.write_bytes(exc.read())
        raise ValueError(f"webhook returned HTTP {exc.code}; inspect response file") from None
    except urllib.error.URLError:
        raise ValueError("webhook transport failed; check the group before retrying (delivery may be ambiguous)") from None
    args.response.write_bytes(raw)
    require_success(json.loads(raw))
    print("Bot API accepted the message. Verify the matching run ID in the destination group.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
