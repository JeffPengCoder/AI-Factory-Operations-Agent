# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import importlib.util
import inspect
import subprocess
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class FakeToolManager:
    def __init__(self):
        self._tools = {}


class FakeMCP:
    def __init__(self, *_args, **_kwargs):
        self._tool_manager = FakeToolManager()

    def tool(self, name=None):
        def register(function):
            self._tool_manager._tools[name or function.__name__] = function
            return function

        return register

    def custom_route(self, path, methods):
        def register(function):
            self._tool_manager._tools[(path, tuple(methods))] = function
            return function

        return register


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


class FakeBCMServer:
    def __init__(self, *_args, **_kwargs):
        self.mcp = FakeMCP()

    def _register_tools(self):
        return None


def load_server_module():
    modules = {name: types.ModuleType(name) for name in [
        "mcp", "mcp.server", "mcp.server.auth", "mcp.server.auth.provider",
        "mcp.server.auth.settings", "mcp.server.fastmcp", "starlette",
        "starlette.requests", "starlette.responses", "bcm_mcp_tools",
        "bcm_mcp_tools.cli", "bcm_mcp_tools.cli.support_mcp",
        "bcm_mcp_tools.cli.support_mcp.main", "bcm_mcp_tools.cli.support_mcp.options",
        "bcm_mcp_tools.notes", "bcm_mcp_tools.server",
    ]}
    modules["mcp.server.auth.provider"].AccessToken = object
    modules["mcp.server.auth.settings"].AuthSettings = object
    modules["mcp.server.fastmcp"].FastMCP = FakeMCP
    modules["starlette.requests"].Request = object
    modules["starlette.responses"].JSONResponse = FakeResponse
    modules["bcm_mcp_tools.cli.support_mcp.main"].configure_logging = lambda _level: None
    modules["bcm_mcp_tools.cli.support_mcp.options"].get_env_bool = lambda _name, default: default
    modules["bcm_mcp_tools.cli.support_mcp.options"].get_env_int = lambda _name, default: default
    modules["bcm_mcp_tools.cli.support_mcp.options"].get_env_str = lambda _name, default: default
    modules["bcm_mcp_tools.notes"].NotesManager = object
    modules["bcm_mcp_tools.server"].BCMServer = FakeBCMServer
    sys.modules.update(modules)
    path = Path(__file__).parents[1] / "files" / "bcm-mcp-ssh-server.py"
    spec = importlib.util.spec_from_file_location("bcm_server_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_server_module()

    def server(self):
        server = self.module.MosaicBCMServer.__new__(self.module.MosaicBCMServer)
        server.mcp = FakeMCP()
        server.cmsh_username = "readonly-user"
        server.cmsh_profile = "readonly"
        server.cmsh_setup_timeout = 240
        server.cmsh_exec_timeout = 120
        server.cmsh_path = "/opt/example/cmsh"
        server.cmsh_enabled = True
        server.cmsh_admin_enabled = False
        server.hardware_compat_enabled = True
        server.bcm_head_host = "head.example"
        server._cmsh_ready = False
        server._cmsh_setup_lock = threading.Lock()
        return server

    def test_ssh_always_targets_the_configured_head(self):
        server = self.server()
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        with patch.object(self.module.subprocess, "run", return_value=completed) as run:
            server._ssh("uname -m", 30)
        self.assertEqual(run.call_args.args[0][:2], ["ssh", "head.example"])
        self.assertNotIn("pip", run.call_args.args[0][-1])

    def test_cmsh_identity_is_checked_once(self):
        server = self.server()
        server._ssh = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
        server._ensure_cmsh_user()
        server._ensure_cmsh_user()
        server._ensure_cmsh_user()
        server._ssh.assert_called_once()

    def test_blocking_cmsh_calls_run_concurrently(self):
        server = self.server()
        server.mcp._tool_manager._tools["execute_cmsh"] = object()

        def blocking(_commands):
            time.sleep(0.1)
            return "ok"

        server._run_cmsh = blocking
        server.slurm_job_evidence = Mock(return_value="ok")
        server.register_mosaic_tools()
        execute = server.mcp._tool_manager._tools["execute_cmsh"]
        self.assertTrue(inspect.iscoroutinefunction(execute))

        async def run():
            started = time.monotonic()
            results = await asyncio.gather(execute("device; list"), execute("device; status"))
            return time.monotonic() - started, results

        elapsed, results = asyncio.run(run())
        self.assertLess(elapsed, 0.18)
        self.assertEqual(results, ["ok", "ok"])

    def test_parses_interchangeable_bcm_inventory_and_credentials(self):
        inventory = """Type Hostname MAC Category InternalIP Network Status
PhysicalNode atlas-01 aa:bb compute 10.20.0.11 internal UP
PhysicalNode atlas-02 aa:cc compute 10.20.0.12 internal UP
VirtualNode atlas-vm aa:dd virtual 10.20.0.13 internal UP
"""
        self.assertEqual(self.module.parse_device_list(inventory), [
            {"hostname": "atlas-01", "internal_ip": "10.20.0.11", "type": "PhysicalNode"},
            {"hostname": "atlas-02", "internal_ip": "10.20.0.12", "type": "PhysicalNode"},
        ])
        output = """================ atlas-02 ================
+(atlas-02:bmcsettings) get username
operator
+(atlas-02:bmcsettings) get password
example-secret
+(atlas-02:interfaces) list bmc -f ip
ip
----------
10.30.0.12
"""
        self.assertEqual(self.module.parse_bmc_lookup(output), {
            "hostname": "atlas-02", "bmc_ip": "10.30.0.12",
            "bmc_username": "operator", "bmc_password": "example-secret",
        })

    def test_hardware_bmc_resolves_missing_credentials_from_category(self):
        cases = [
            ("node-user", "node-pass", "category-user", "category-pass", ("node-user", "node-pass")),
            ("", "", "category-user", "category-pass", ("category-user", "category-pass")),
            ("node-user", "", "category-user", "category-pass", ("node-user", "category-pass")),
            ("", "node-pass", "category-user", "category-pass", ("category-user", "node-pass")),
            ("", "", "category-user", "", None),
            ("", "", "", "category-pass", None),
        ]
        for username, password, category_user, category_pass, expected in cases:
            with self.subTest(device=(bool(username), bool(password)), category=(bool(category_user), bool(category_pass))):
                server = self.server()

                def cmsh(command):
                    if command.startswith("device; foreach"):
                        return f"""================ node-02 ================
+(node-02:bmcsettings) get username
{username}
+(node-02:bmcsettings) get password
{password}
+(node-02:interfaces) list bmc -f ip
ip
10.40.0.12
"""
                    if command.startswith("device; get"):
                        return "compute"
                    return category_user if command.endswith("get username") else category_pass

                server._run_hardware_cmsh = Mock(side_effect=cmsh)
                result = server.hardware_bmc("node-02")
                if expected is None:
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result, {
                        "hostname": "node-02", "bmc_ip": "10.40.0.12",
                        "bmc_username": expected[0], "bmc_password": expected[1],
                    })
                if username and password:
                    server._run_hardware_cmsh.assert_called_once()

    def test_hardware_bmc_requires_a_device_bmc_address(self):
        server = self.server()
        for output in ("", "================ node-02 ================\n"):
            with self.subTest(output=output):
                server._run_hardware_cmsh = Mock(return_value=output)
                self.assertIsNone(server.hardware_bmc("node-02"))
                server._run_hardware_cmsh.assert_called_once()
        server._run_hardware_cmsh.reset_mock()
        with self.assertRaises(ValueError):
            server.hardware_bmc("node-02; invalid")
        server._run_hardware_cmsh.assert_not_called()

    def test_hardware_bmc_requires_credentials_when_category_is_unset(self):
        server = self.server()
        server._run_hardware_cmsh = Mock(side_effect=["""================ node-02 ================
+(node-02:interfaces) list bmc -f ip
10.40.0.12
""", ""])
        self.assertIsNone(server.hardware_bmc("node-02"))

    def test_hardware_routes_require_the_bearer_token(self):
        server = self.server()
        server.hardware_devices = Mock(return_value=[])
        server.register_hardware_routes("generated-token")
        route = server.mcp._tool_manager._tools[("/list", ("GET",))]

        class Request:
            def __init__(self, authorization=""):
                self.path_params = {}
                self.headers = {"authorization": authorization}

        denied = asyncio.run(route(Request()))
        allowed = asyncio.run(route(Request("Bearer generated-token")))
        self.assertEqual((denied.status_code, denied.content), (401, {"detail": "unauthorized"}))
        self.assertEqual((allowed.status_code, allowed.content), (200, {"devices": [], "count": 0}))


if __name__ == "__main__":
    unittest.main()
