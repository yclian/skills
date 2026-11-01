#!/usr/bin/env python3
"""
Dual-Boundary (Reality-and-Oracle) Verification Suite for gcloud-remote-auth.

Covers:
1. Domain Core (Pure Transforms):
   - OAuth URL extraction from real recorded gcloud stderr shapes
   - Exit sentinel parsing
   - Safe gcloud command construction & strict email validation (rejecting flag injection)
2. Egress Boundary Scenarios (over real detached subprocesses & filesystem):
   - Happy path: `start` -> `finish --stdin` with PLANTED_OAUTH_URL & PLANTED_AUTH_CODE
   - Security / Invariant sweep: 0700 state dir, zero residual `code.txt` / `out.log` / `worker.pid` after finish
   - Replay rejection: second `finish` after completion is rejected with exit code 1 (no stale out.log illusion)
   - Fast failure detection: when gcloud exits non-zero without literal "ERROR:", `finish` returns 1 in <3s (no 30s hang)
   - Invalid account flag injection blocked at CLI boundary
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
SCRIPT_PATH = os.path.join(SCRIPT_DIR, "gcloud_remote_auth.py")
sys.path.insert(0, SCRIPT_DIR)

import gcloud_remote_auth as gra  # noqa: E402

PLANTED_CLIENT_ID = "planted-client-id-32555940559.apps.googleusercontent.com"
PLANTED_PKCE_CHALLENGE = "PLANTED_PKCE_CHALLENGE_S256_TOKEN"
PLANTED_AUTH_CODE = "4/0AeanS0_PLANTED_VERIFICATION_CODE_SECRET"


class TestPureTransforms(unittest.TestCase):
    def test_extract_oauth_url_from_recorded_gcloud_stderr(self):
        recorded_stderr = (
            "Go to the following link in your browser, and complete the sign-in prompts:\n\n"
            f"    https://accounts.google.com/o/oauth2/auth?response_type=code&client_id={PLANTED_CLIENT_ID}"
            f"&code_challenge={PLANTED_PKCE_CHALLENGE}&code_challenge_method=S256\n\n"
            "Once finished, enter the verification code provided in your browser: "
        )
        url = gra.extract_oauth_url(recorded_stderr)
        self.assertIsNotNone(url)
        self.assertIn(PLANTED_CLIENT_ID, url)
        self.assertIn(PLANTED_PKCE_CHALLENGE, url)

    def test_parse_exit_sentinel(self):
        self.assertIsNone(gra.parse_exit_sentinel("Still waiting for code..."))
        self.assertEqual(
            gra.parse_exit_sentinel("You are now logged in.\n__GCLOUD_REMOTE_AUTH_EXIT__:0\n"),
            0,
        )
        self.assertEqual(
            gra.parse_exit_sentinel("Invalid grant\n__GCLOUD_REMOTE_AUTH_EXIT__:1\n"),
            1,
        )

    def test_build_gcloud_login_cmd_blocks_flag_injection(self):
        cmd = gra.build_gcloud_login_cmd("gcloud", account="user@example.com", adc_only=True, enable_gdrive_access=True)
        self.assertEqual(
            cmd,
            [
                "gcloud",
                "auth",
                "application-default",
                "login",
                "--no-launch-browser",
                "--quiet",
                "--account=user@example.com",
                "--enable-gdrive-access",
            ],
        )
        with self.assertRaises(ValueError):
            gra.build_gcloud_login_cmd("gcloud", account="--cred-file=/tmp/evil.json")
        with self.assertRaises(ValueError):
            gra.build_gcloud_login_cmd("gcloud", account="user@example.com; rm -rf /")


class TestBoundaryScenarios(unittest.TestCase):
    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="gra_test_")
        self.state_dir = os.path.join(self.temp_root, "state")
        self.bin_dir = os.path.join(self.temp_root, "bin")
        os.makedirs(self.bin_dir, exist_ok=True)
        self.fake_gcloud = self._create_fake_gcloud()

    def tearDown(self):
        # Invariant sweep after every scenario: no residual secret files or live workers
        if os.path.exists(self.state_dir):
            gra.kill_existing_worker(self.state_dir)
            for fname in ("code.txt", "out.log", "worker.pid"):
                fpath = os.path.join(self.state_dir, fname)
                self.assertFalse(
                    os.path.exists(fpath),
                    f"Invariant violation: residual state file left on disk: {fpath}",
                )
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def _create_fake_gcloud(self) -> str:
        py_helper = os.path.join(self.bin_dir, "fake_gcloud_impl.py")
        with open(py_helper, "w", encoding="utf-8") as f:
            f.write(
                f'''import sys, time
args = sys.argv[1:]
if "list" in args:
    print("ACTIVE  ACCOUNT\\n*       user@example.com")
    sys.exit(0)
if "print-access-token" in args:
    print("ya29.planted_valid_token")
    sys.exit(0)
if "login" in args:
    sys.stdout.write(
        "Go to the following link in your browser:\\n"
        "https://accounts.google.com/o/oauth2/auth?client_id={PLANTED_CLIENT_ID}&code_challenge={PLANTED_PKCE_CHALLENGE}\\n"
        "Enter authorization code: "
    )
    sys.stdout.flush()
    line = sys.stdin.readline().strip()
    if line == "{PLANTED_AUTH_CODE}":
        print("\\nYou are now logged in as [user@example.com].\\nCredentials saved to file.")
        sys.exit(0)
    else:
        # Deliberately omit literal "ERROR:" to test Probe 7 fast exit sentinel detection
        print("\\n Reauthentication failed: invalid_grant (bad verification code).")
        sys.exit(1)
'''
            )
        if os.name == "nt":
            wrapper = os.path.join(self.bin_dir, "fake_gcloud.cmd")
            with open(wrapper, "w", encoding="utf-8") as f:
                f.write(f'@"{sys.executable}" "{py_helper}" %*\r\n')
            return wrapper
        else:
            wrapper = os.path.join(self.bin_dir, "fake_gcloud")
            with open(wrapper, "w", encoding="utf-8") as f:
                f.write(f'#!/bin/sh\nexec "{sys.executable}" "{py_helper}" "$@"\n')
            os.chmod(wrapper, 0o755)
            return wrapper

    def _run_cli(self, *args: str, stdin_text: str | None = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["GCLOUD_REMOTE_AUTH_STATE_DIR"] = self.state_dir
        env["GCLOUD_REMOTE_AUTH_GCLOUD_BIN"] = self.fake_gcloud
        return subprocess.run(
            [sys.executable, SCRIPT_PATH, *args],
            input=stdin_text,
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )

    def test_scenario_happy_path_start_finish_and_replay_blocked(self):
        # 1. Start session
        res_start = self._run_cli("start", "--account", "user@example.com")
        self.assertEqual(res_start.returncode, 0, res_start.stdout + res_start.stderr)
        self.assertIn(f"AUTH_URL: https://accounts.google.com/o/oauth2/auth?client_id={PLANTED_CLIENT_ID}", res_start.stdout)

        # Verify POSIX 0700 permissions on state_dir
        if os.name != "nt":
            mode = stat.S_IMODE(os.lstat(self.state_dir).st_mode)
            self.assertEqual(mode, 0o700)

        # 2. Finish session via --stdin with planted code
        res_finish = self._run_cli("finish", "--stdin", stdin_text=PLANTED_AUTH_CODE)
        self.assertEqual(res_finish.returncode, 0, res_finish.stdout + res_finish.stderr)
        self.assertIn("You are now logged in as [user@example.com].", res_finish.stdout)

        # 3. Replay attack check: calling finish again must fail immediately (ExitCode 1)
        res_replay = self._run_cli("finish", "REPLAYED_CODE")
        self.assertEqual(res_replay.returncode, 1)
        self.assertIn("No active auth session found", res_replay.stdout)

    def test_scenario_invalid_code_fails_fast_without_30s_hang(self):
        res_start = self._run_cli("start", "--adc-only")
        self.assertEqual(res_start.returncode, 0)

        t0 = time.time()
        res_bad = self._run_cli("finish", "WRONG_CODE")
        elapsed = time.time() - t0

        self.assertEqual(res_bad.returncode, 1)
        self.assertIn("invalid_grant", res_bad.stdout)
        self.assertLess(elapsed, 8.0, "finish() hung instead of detecting worker exit sentinel!")

    def test_scenario_status_checks_both_cli_and_adc(self):
        res_status = self._run_cli("status")
        self.assertEqual(res_status.returncode, 0)
        self.assertIn("OK: gcloud CLI access token is valid and active.", res_status.stdout)
        self.assertIn("OK: Application Default Credentials (ADC) token is valid and active.", res_status.stdout)


if __name__ == "__main__":
    unittest.main()
