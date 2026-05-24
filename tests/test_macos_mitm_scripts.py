import os
import stat
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class MacosMitmScriptsTest(unittest.TestCase):
    def assert_executable_script_contains(self, relative_path, expected_snippets):
        script_path = ROOT_DIR / relative_path

        self.assertTrue(script_path.exists(), f"{relative_path} should exist")
        mode = script_path.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, f"{relative_path} should be executable")

        content = script_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("#!/usr/bin/env bash\n"))
        for snippet in expected_snippets:
            self.assertIn(snippet, content)

    def test_start_script_runs_mitmproxy_in_background(self):
        self.assert_executable_script_contains(
            "start_mitm_proxy.sh",
            [
                "mitmdump",
                "launchctl bootstrap",
                "com.daoyufan.mitmproxy",
                "LOCAL_MITM_BLOCK_UNREWRITTEN",
                "<string>0</string>",
                "--listen-host",
                "127.0.0.1",
                "--listen-port",
                "rewrite_addon.py",
                "mitmproxy.plist",
                "Installing mitmproxy dependencies",
                "--no-cache-dir",
                "Waiting for mitmproxy",
            ],
        )

    def test_stop_script_unloads_launch_agent(self):
        self.assert_executable_script_contains(
            "stop_mitm_proxy.sh",
            [
                "launchctl bootout",
                "com.daoyufan.mitmproxy",
            ],
        )

    def test_chrome_script_uses_isolated_profile_and_proxy(self):
        self.assert_executable_script_contains(
            "open_chrome_with_mitm.sh",
            [
                "Google Chrome",
                "--user-data-dir",
                "--proxy-server=http://127.0.0.1:",
                "start_mitm_proxy.sh",
                "https://daoyu.fan/4687.html",
            ],
        )

    def test_certificate_script_installs_mitmproxy_ca_to_login_keychain(self):
        self.assert_executable_script_contains(
            "install_mitm_ca_macos.sh",
            [
                "mitmproxy-ca-cert.cer",
                "security add-trusted-cert",
                "login.keychain-db",
            ],
        )


if __name__ == "__main__":
    unittest.main()
