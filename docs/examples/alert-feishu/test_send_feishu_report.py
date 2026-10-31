# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import send_feishu_report as report


class ReportTests(unittest.TestCase):
    def test_roundtrip_preserves_full_chinese_analysis_and_alert_fields(self):
        alert = {"id": "alertmanager:test", "payload": "测试", "annotations": {"all": "保留"}, "extra": [1, 2, 3]}
        analysis = "分析第一行\n第二行，含完整证据\n"
        payload = report.make_payload(alert, analysis, "agent:default:test", "run-1")
        decoded = json.loads(report.encode_payload(payload))
        text = decoded["content"]["text"]
        self.assertIn(json.dumps(alert, ensure_ascii=False, indent=2), text)
        self.assertIn(analysis, text)
        self.assertIn("run-1", text)

    def test_signature_uses_timestamp_secret_as_key_and_empty_message(self):
        stamp, secret = 1599360473, "test-secret"
        expected = base64.b64encode(hmac.digest(f"{stamp}\n{secret}".encode(), b"", hashlib.sha256)).decode()
        body = json.loads(report.encode_payload({"msg_type": "text"}, secret, stamp))
        self.assertEqual(body["timestamp"], str(stamp))
        self.assertEqual(body["sign"], expected)
        self.assertNotEqual(body["sign"], base64.b64encode(hmac.digest(secret.encode(), str(stamp).encode(), hashlib.sha256)).decode())

    def test_oversized_report_fails_instead_of_truncating(self):
        with self.assertRaisesRegex(ValueError, "Nothing was sent or truncated"):
            report.encode_payload({"content": {"text": "中" * 7000}})

    def test_http_success_requires_explicit_bot_success(self):
        for value in [{"code": 0}, {"StatusCode": 0}, {"code": 0, "StatusCode": 0}]:
            report.require_success(value)
        for value in [{}, {"code": 19021}, {"code": "0"}, {"code": False}, {"code": 0, "StatusCode": 1}, []]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                report.require_success(value)

    def test_credentials_only_go_to_official_webhook_without_redirects(self):
        report.validate_webhook("https://open.feishu.cn/open-apis/bot/v2/hook/test")
        report.validate_webhook("https://open.larksuite.com/open-apis/bot/v2/hook/test")
        for value in ["http://open.feishu.cn/open-apis/bot/v2/hook/test", "https://example.com/open-apis/bot/v2/hook/test", "https://open.feishu.cn/open-apis/bot/v2/hook/", "https://user:pass@open.feishu.cn/open-apis/bot/v2/hook/test"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                report.validate_webhook(value)
        with self.assertRaises(ValueError):
            report.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_cli_dry_run_needs_no_credentials_and_retains_full_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "alert.json").write_text('{"id":"test","payload":"test"}')
            (root / "analysis.md").write_text("完整分析\n", encoding="utf-8")
            process = subprocess.run(
                [sys.executable, str(Path(report.__file__)), "--alert", str(root / "alert.json"), "--analysis", str(root / "analysis.md"), "--session-key", "test", "--run-id", "run-1", "--output", str(root / "payload.json")],
                capture_output=True, text=True, check=True,
            )
            self.assertIn("no network request", process.stdout)
            self.assertIn("完整分析", (root / "payload.json").read_text())


if __name__ == "__main__":
    unittest.main()
