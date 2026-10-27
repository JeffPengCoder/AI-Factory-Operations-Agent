# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import importlib.util
import inspect
import json
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
        server.redfish_enabled = False
        server.redfish_verify_tls = False
        server.redfish_timeout = 20
        server.redfish_via_head_node = True
        server._redfish_members = {}
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

    def test_redfish_policy_allows_read_only_inventory(self):
        policy = self.module.RedfishPolicy
        for path in [
            "/redfish/v1",
            "/redfish/v1/",
            "/redfish/v1/Systems",
            "/redfish/v1/Systems/DGX",
            "/redfish/v1/Systems/System.Embedded.1/Processors/CPU.1",
            "/redfish/v1/Systems/DGX/LogServices/BIOS/Entries?$top=5",
            "/redfish/v1/Chassis/DGX/ThermalSubsystem/ThermalMetrics",
            "/redfish/v1/Chassis/DGX/PowerSubsystem/PowerSupplies?$expand=.($levels=1)",
            "/redfish/v1/Managers/BMC/LogServices/SEL/Entries?$skip=3467&$top=75",
            "/redfish/v1/Managers/BMC/EthernetInterfaces/eth0",
            "/redfish/v1/UpdateService/FirmwareInventory/CX7_0",
            "/redfish/v1/TaskService/Tasks/10",
        ]:
            self.assertTrue(policy.is_allowed("GET", path), path)

    def test_redfish_policy_rejects_writes_and_sensitive_resources(self):
        policy = self.module.RedfishPolicy
        self.assertFalse(policy.is_allowed("POST", "/redfish/v1/Systems/DGX"))
        self.assertFalse(policy.is_allowed("PATCH", "/redfish/v1/Systems/DGX"))
        for path in [
            "/redfish/v1/AccountService",
            "/redfish/v1/AccountService/Accounts/2",
            "/redfish/v1/SessionService/Sessions",
            "/redfish/v1/CertificateService",
            "/redfish/v1/EventService/Subscriptions",
            "/redfish/v1/Systems/DGX/Actions/ComputerSystem.Reset",
            "/redfish/v1/Managers/BMC/Actions/Manager.Reset",
            "/redfish/v1/Systems/DGX/LogServices/SEL/Actions/LogService.ClearLog",
            "/redfish/v1/Systems/DGX/SecureBoot",
            "/redfish/v1/Systems/DGX/Bios/Settings",
            "/redfish/v1/Managers/BMC/VirtualMedia/CD1",
            "/redfish/v1/Systems/../AccountService",
            "/redfish/v1/Systems/DGX/..",
            "/redfish/v1//Systems",
            "/redfish/v1/Systems/DGX%2F..",
            "/redfish/v1/Systems?$filter=Id",
            "/redfish/v1/Systems?$expand=*&$select=Id",
            "/redfish/v1/Systems?$top=1;rm",
            "/redfish/v1/Systems/DGX?",
            "/redfish/v1/Systems/DGX#x",
            "/redfish/v1/Systems/DGX/Oem",
            "/redfish/v1/Managers/BMC/NodeManager",
            "/redfish/v1/UpdateService",
            "/redfish/v1/Systems/DGX/LogServices/SEL/Entries/1/attachment",
            "/redfish/v2",
            "https://10.0.0.1/redfish/v1",
            "",
        ]:
            self.assertFalse(policy.is_allowed("GET", path), path)

    def test_redfish_denied_paths_never_resolve_bmc_credentials(self):
        server = self.server()
        server.hardware_bmc = Mock()
        with self.assertRaises(self.module.RedfishError) as raised:
            server.redfish_get("atlas-01", "/redfish/v1/AccountService")
        self.assertEqual(raised.exception.status, 403)
        server.hardware_bmc.assert_not_called()
        payload = json.loads(server.redfish_tool(server.redfish_get, "atlas-01", "/redfish/v1/Systems/DGX/Actions/ComputerSystem.Reset"))
        self.assertEqual(payload["status"], 403)

    def test_redfish_head_node_transport_keeps_credentials_off_the_command_line(self):
        server = self.server()
        server.hardware_bmc = Mock(return_value={
            "hostname": "atlas-01", "bmc_ip": "10.30.0.11", "bmc_username": "admin", "bmc_password": 'p"a\\ss',
        })
        body = b'{"@odata.type":"#ComputerSystem","Id":"DGX","PowerState":"On","Oem":{"UserPassword":"x","AuthToken":"y"}}'
        server._ssh = Mock(return_value=subprocess.CompletedProcess([], 0, body + b"\n200", b""))
        result = server.redfish_get("atlas-01", "/redfish/v1/Systems/DGX")
        script, timeout, stdin = server._ssh.call_args.args
        self.assertNotIn("p\"a", script)
        self.assertIn("-K /dev/stdin", script)
        self.assertIn("https://10.30.0.11/redfish/v1/Systems/DGX", script)
        self.assertEqual(stdin, b'user = "admin:p\\"a\\\\ss"\n')
        self.assertGreater(timeout, server.redfish_timeout)
        self.assertEqual(result, {"Id": "DGX", "PowerState": "On", "Oem": {"UserPassword": "[redacted]", "AuthToken": "[redacted]"}})

    def test_redfish_errors_omit_the_bmc_address(self):
        server = self.server()
        server.hardware_bmc = Mock(return_value={
            "hostname": "atlas-01", "bmc_ip": "10.30.0.11", "bmc_username": "admin", "bmc_password": "secret",
        })
        server._ssh = Mock(return_value=subprocess.CompletedProcess([], 7, b"", b"curl: (7) Failed to connect to 10.30.0.11 port 443"))
        text = server.redfish_tool(server.redfish_system_summary, "atlas-01")
        self.assertEqual(json.loads(text), {"error": "BMC is unreachable", "status": 502})
        server._ssh = Mock(return_value=subprocess.CompletedProcess([], 0, b"\n401", b""))
        text = server.redfish_tool(server.redfish_get, "atlas-01", "/redfish/v1/Systems")
        self.assertEqual(json.loads(text)["status"], 401)
        self.assertNotIn("10.30.0.11", text)
        self.assertNotIn("secret", text)

    def test_redfish_tools_register_only_when_enabled(self):
        names = {"redfish_get", "redfish_system_summary", "redfish_thermal", "redfish_power", "redfish_sel", "redfish_firmware"}
        for enabled in (False, True):
            server = self.server()
            server.redfish_enabled = enabled
            server.register_mosaic_tools()
            registered = set(server.mcp._tool_manager._tools) & names
            self.assertEqual(registered, names if enabled else set())

    def test_redfish_sel_merges_newest_entries_across_log_services(self):
        server = self.server()
        server.hardware_bmc = Mock(return_value={"bmc_ip": "10.30.0.11", "bmc_username": "u", "bmc_password": "p"})
        entry = lambda n, day: {"Id": str(n), "Created": f"2026-09-{day:02d}T00:00:00+00:00", "Severity": "OK", "Message": f"event {n}"}
        responses = {
            "/redfish/v1/Managers": {"Members": [{"@odata.id": "/redfish/v1/Managers/BMC"}]},
            "/redfish/v1/Systems": {"Members": [{"@odata.id": "/redfish/v1/Systems/DGX"}]},
            "/redfish/v1/Managers/BMC/LogServices": {"Members": [
                {"@odata.id": "/redfish/v1/Managers/BMC/LogServices/SEL"},
                {"@odata.id": "/redfish/v1/Managers/BMC/LogServices/Journal"},
            ]},
            "/redfish/v1/Systems/DGX/LogServices": {"Members": [{"@odata.id": "/redfish/v1/Systems/DGX/LogServices/BIOS"}]},
            "/redfish/v1/Managers/BMC/LogServices/SEL/Entries?$top=2": {"Members@odata.count": 5, "Members": [entry(1, 1), entry(2, 2)]},
            "/redfish/v1/Managers/BMC/LogServices/SEL/Entries?$skip=3&$top=2": {"Members": [entry(4, 4), entry(5, 5)]},
            "/redfish/v1/Systems/DGX/LogServices/BIOS/Entries?$top=2": {"Members@odata.count": 1, "Members": [entry(9, 3)]},
        }
        requested = []

        def fetch(_bmc, path):
            requested.append(path)
            return 200, json.dumps(responses[path]).encode()

        server._redfish_fetch = fetch
        result = server.redfish_sel("atlas-01", 2)
        self.assertEqual(result["sources"], ["Managers/BMC/SEL", "Systems/DGX/BIOS"])
        self.assertEqual([(e["source"], e["id"]) for e in result["entries"]], [("Managers/BMC/SEL", "5"), ("Managers/BMC/SEL", "4")])
        self.assertNotIn("/redfish/v1/Managers/BMC/LogServices/Journal/Entries?$top=2", requested)


if __name__ == "__main__":
    unittest.main()
