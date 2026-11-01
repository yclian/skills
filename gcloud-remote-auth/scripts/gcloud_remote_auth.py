#!/usr/bin/env python3
"""
Non-interactive 2-step gcloud + Application Default Credentials (ADC) login
helper for remote or headless AI agents whose shell tools cannot send interactive
stdin (`--no-launch-browser`).

Subcommands:
  status                                           Check gcloud CLI + ADC token health
  start [--account EMAIL] [--adc-only] [--enable-gdrive-access]
                                                   Spawn detached worker and print AUTH_URL
  finish [<CODE> | --stdin]                        Send verification code to worker and complete login
"""
import argparse
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from typing import Optional

EXIT_SENTINEL_PREFIX = "__GCLOUD_REMOTE_AUTH_EXIT__:"
OAUTH_URL_RE = re.compile(r"(https://accounts\.google\.com/\S+)")
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def get_state_dir(override: Optional[str] = None) -> str:
    """Return a user-private (0700) state directory, rejecting symlinks and foreign UIDs."""
    path = (
        override
        or os.environ.get("GCLOUD_REMOTE_AUTH_STATE_DIR")
        or os.path.join(os.path.expanduser("~"), ".cache", "gcloud-remote-auth")
    )
    path = os.path.abspath(path)
    os.makedirs(path, mode=0o700, exist_ok=True)

    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise RuntimeError(f"Security error: state directory {path} must not be a symlink.")
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise RuntimeError(f"Security error: state directory {path} is not owned by current user.")
    if os.name != "nt":
        os.chmod(path, 0o700)
    return path


def state_paths(state_dir: str) -> tuple[str, str, str]:
    return (
        os.path.join(state_dir, "code.txt"),
        os.path.join(state_dir, "out.log"),
        os.path.join(state_dir, "worker.pid"),
    )


def resolve_gcloud_bin(override: Optional[str] = None) -> str:
    """Resolve the gcloud executable, honoring explicit overrides for testing."""
    explicit = override or os.environ.get("GCLOUD_REMOTE_AUTH_GCLOUD_BIN")
    if explicit:
        return explicit
    if os.name == "nt":
        for candidate in ("gcloud.cmd", "gcloud.exe", "gcloud"):
            found = shutil.which(candidate)
            if found:
                return found
    return shutil.which("gcloud") or "gcloud"


def extract_oauth_url(text: str) -> Optional[str]:
    """Pure transform: extract Google OAuth URL from gcloud output."""
    match = OAUTH_URL_RE.search(text)
    return match.group(1).strip() if match else None


def parse_exit_sentinel(text: str) -> Optional[int]:
    """Pure transform: extract worker exit code sentinel from log text."""
    for line in reversed(text.splitlines()):
        if line.startswith(EXIT_SENTINEL_PREFIX):
            try:
                return int(line[len(EXIT_SENTINEL_PREFIX) :].strip())
            except ValueError:
                return 1
    return None


def open_private_write(path: str):
    """Open a file for writing with 0600 permissions and O_NOFOLLOW where supported."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", buffering=1)


def atomic_write_private(path: str, content: str) -> None:
    """Atomically write content to a 0600 file via temporary file + os.replace."""
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open_private_write(tmp_path) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def safe_unlink(path: str) -> None:
    """Remove a file if it exists; raise if removal fails and file still exists."""
    try:
        if os.path.lexists(path):
            os.remove(path)
    except OSError:
        if os.path.lexists(path):
            raise


def is_pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    if os.name == "nt":
        res = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return str(pid) in res.stdout
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return False


def kill_existing_worker(state_dir: str) -> None:
    _, _, pid_file = state_paths(state_dir)
    if not os.path.lexists(pid_file):
        return
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        if pid > 1:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
            else:
                # Worker is spawned with start_new_session=True, so PGID == PID
                try:
                    os.killpg(pid, signal.SIGTERM)
                except OSError:
                    os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    safe_unlink(pid_file)


def build_gcloud_login_cmd(
    gcloud_bin: str,
    account: Optional[str] = None,
    adc_only: bool = False,
    enable_gdrive_access: bool = False,
) -> list[str]:
    """Pure transform: construct safe gcloud login command list."""
    if account and not ACCOUNT_RE.match(account):
        raise ValueError(f"Invalid email format for --account: {account!r}")

    if adc_only:
        cmd = [gcloud_bin, "auth", "application-default", "login", "--no-launch-browser", "--quiet"]
    else:
        cmd = [gcloud_bin, "auth", "login", "--update-adc", "--no-launch-browser", "--quiet"]

    if account:
        cmd.append(f"--account={account}")
    if enable_gdrive_access:
        cmd.append("--enable-gdrive-access")
    return cmd


def worker(
    state_dir: str,
    account: Optional[str] = None,
    adc_only: bool = False,
    enable_gdrive_access: bool = False,
    timeout_sec: float = 600.0,
) -> int:
    code_file, out_file, pid_file = state_paths(state_dir)
    atomic_write_private(pid_file, str(os.getpid()))

    gcloud_bin = resolve_gcloud_bin()
    cmd = build_gcloud_login_cmd(
        gcloud_bin,
        account=account,
        adc_only=adc_only,
        enable_gdrive_access=enable_gdrive_access,
    )

    exit_code = 1
    proc: Optional[subprocess.Popen] = None
    try:
        with open_private_write(out_file) as log_out:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=log_out,
                stderr=subprocess.STDOUT,
                text=True,
            )

            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                if os.path.exists(code_file):
                    try:
                        with open(code_file, "r", encoding="utf-8") as cf:
                            code = cf.read().strip()
                    except OSError:
                        code = ""
                    if code:
                        safe_unlink(code_file)
                        try:
                            proc.communicate(input=code + "\n", timeout=45)
                            exit_code = proc.returncode if proc.returncode is not None else 1
                        except Exception as exc:
                            log_out.write(f"\nERROR communicating verification code: {exc}\n")
                            exit_code = 1
                        break
                if proc.poll() is not None:
                    exit_code = proc.returncode if proc.returncode is not None else 1
                    break
                time.sleep(0.25)
            else:
                log_out.write("\nERROR: Timed out waiting for verification code.\n")
                exit_code = 124

            log_out.write(f"\n{EXIT_SENTINEL_PREFIX}{exit_code}\n")
            log_out.flush()
    finally:
        if proc is not None and proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                    )
                else:
                    proc.kill()
            except Exception:
                pass
        safe_unlink(code_file)
        safe_unlink(pid_file)
    return exit_code


def start(
    state_dir: str,
    account: Optional[str] = None,
    adc_only: bool = False,
    enable_gdrive_access: bool = False,
    wait_seconds: float = 16.0,
) -> int:
    code_file, out_file, pid_file = state_paths(state_dir)
    kill_existing_worker(state_dir)
    for path in (code_file, out_file, pid_file):
        safe_unlink(path)

    worker_args = [sys.executable, os.path.abspath(__file__), "_worker", "--state-dir", state_dir]
    if account:
        worker_args.extend(["--account", account])
    if adc_only:
        worker_args.append("--adc-only")
    if enable_gdrive_access:
        worker_args.append("--enable-gdrive-access")

    spawn_kwargs: dict = {"close_fds": True}
    if os.name == "nt":
        spawn_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        spawn_kwargs["start_new_session"] = True

    subprocess.Popen(
        worker_args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **spawn_kwargs,
    )

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            url = extract_oauth_url(text)
            if url:
                print(f"AUTH_URL: {url}")
                return 0
            rc = parse_exit_sentinel(text)
            if rc is not None:
                print(text.strip())
                safe_unlink(out_file)
                return rc if rc != 0 else 1
        time.sleep(0.25)

    out_text = ""
    if os.path.exists(out_file):
        with open(out_file, "r", encoding="utf-8", errors="replace") as f:
            out_text = f.read()
    kill_existing_worker(state_dir)
    safe_unlink(out_file)
    print(f"ERROR: Timed out waiting for gcloud OAuth URL.\n{out_text}".strip())
    return 1


def finish(state_dir: str, code: str, wait_seconds: float = 30.0) -> int:
    code_file, out_file, pid_file = state_paths(state_dir)
    clean_code = code.strip()
    if not clean_code:
        print("ERROR: Verification code cannot be empty.")
        return 1

    if not os.path.exists(pid_file) or not os.path.exists(out_file):
        safe_unlink(out_file)
        safe_unlink(code_file)
        print("ERROR: No active auth session found. Run `start` first.")
        return 1

    try:
        with open(pid_file, "r", encoding="utf-8") as pf:
            worker_pid = int(pf.read().strip())
    except ValueError:
        worker_pid = -1

    if not is_pid_alive(worker_pid):
        safe_unlink(pid_file)
        safe_unlink(out_file)
        safe_unlink(code_file)
        print("ERROR: Auth worker is no longer running (expired or already used). Run `start` again.")
        return 1

    atomic_write_private(code_file, clean_code)

    deadline = time.time() + wait_seconds
    try:
        while time.time() < deadline:
            time.sleep(0.25)
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                rc = parse_exit_sentinel(text)
                if rc is not None:
                    clean_output = "\n".join(
                        line for line in text.splitlines() if not line.startswith(EXIT_SENTINEL_PREFIX)
                    ).strip()
                    print(clean_output)
                    return 0 if rc == 0 else 1
    finally:
        kill_existing_worker(state_dir)
        safe_unlink(code_file)
        safe_unlink(out_file)

    print("ERROR: Timed out waiting for gcloud to finish token exchange.")
    return 1


def status() -> int:
    gcloud_bin = resolve_gcloud_bin()
    try:
        res_list = subprocess.run(
            [gcloud_bin, "auth", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        print("=== gcloud auth list ===")
        print((res_list.stdout + res_list.stderr).strip())

        res_cli = subprocess.run(
            [gcloud_bin, "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        cli_ok = res_cli.returncode == 0 and bool(res_cli.stdout.strip())
        print("\n=== CLI Access Token Status ===")
        if cli_ok:
            print("OK: gcloud CLI access token is valid and active.")
        else:
            print("EXPIRED/MISSING: gcloud CLI token could not be printed.")
            print((res_cli.stdout + res_cli.stderr).strip())

        res_adc = subprocess.run(
            [gcloud_bin, "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        adc_ok = res_adc.returncode == 0 and bool(res_adc.stdout.strip())
        print("\n=== ADC Token Status ===")
        if adc_ok:
            print("OK: Application Default Credentials (ADC) token is valid and active.")
        else:
            print("EXPIRED/MISSING: ADC token could not be printed.")
            print((res_adc.stdout + res_adc.stderr).strip())

        return 0 if (cli_ok and adc_ok) else 1
    except subprocess.TimeoutExpired:
        print("ERROR: Timed out querying gcloud credential status.")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gcloud_remote_auth.py",
        description="Non-interactive 2-step gcloud + ADC login helper for AI agents.",
    )
    sub = parser.add_subparsers(dest="subcommand")

    p_status = sub.add_parser("status", help="Check current gcloud CLI and ADC token health")
    p_status.add_argument("--state-dir", default=None, help=argparse.SUPPRESS)

    for name in ("start", "_worker"):
        p = sub.add_parser(
            name,
            help="Start background gcloud login session and print AUTH_URL" if name == "start" else argparse.SUPPRESS,
        )
        p.add_argument("--account", default=None, help="Google account email to pre-select")
        p.add_argument(
            "--adc-only",
            action="store_true",
            help="Run `gcloud auth application-default login` instead of `gcloud auth login --update-adc`",
        )
        p.add_argument(
            "--enable-gdrive-access",
            action="store_true",
            help="Request Google Drive scope for BigQuery federated Drive tables",
        )
        p.add_argument("--state-dir", default=None, help=argparse.SUPPRESS)
        p.add_argument("--timeout", type=float, default=600.0, help=argparse.SUPPRESS)

    p_finish = sub.add_parser("finish", help="Submit verification code to complete login")
    p_finish.add_argument("code", nargs="?", default=None, help="Verification code from Google OAuth page")
    p_finish.add_argument("--stdin", action="store_true", help="Read verification code from stdin")
    p_finish.add_argument("--state-dir", default=None, help=argparse.SUPPRESS)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.subcommand:
        parser.print_help()
        return 1

    try:
        state_dir = get_state_dir(getattr(args, "state_dir", None))
        if args.subcommand == "status":
            return status()
        elif args.subcommand == "_worker":
            return worker(
                state_dir,
                account=args.account,
                adc_only=args.adc_only,
                enable_gdrive_access=args.enable_gdrive_access,
                timeout_sec=args.timeout,
            )
        elif args.subcommand == "start":
            return start(
                state_dir,
                account=args.account,
                adc_only=args.adc_only,
                enable_gdrive_access=args.enable_gdrive_access,
            )
        elif args.subcommand == "finish":
            code = sys.stdin.read() if args.stdin else args.code
            if not code:
                print("ERROR: Missing verification code. Usage: gcloud_remote_auth.py finish '<CODE>'")
                return 1
            return finish(state_dir, code)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
