#!/usr/bin/env python3
"""
Antigravity Browser Debug & CDP Helper CLI
Manages Chrome / Chrome Beta DevTools Protocol instances for Antigravity's /browser subagent.
"""

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Safe stdout encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_PORT = 9222
DEFAULT_DEBUG_PROFILE = Path(os.path.expanduser("~/.chrome-debug"))


def get_browser_paths() -> dict:
    """Returns detected paths for Chrome variants across platforms."""
    os_name = platform.system()
    paths = {
        "beta": [],
        "stable": [],
        "canary": [],
        "edge": []
    }

    if os_name == "Windows":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))

        paths["beta"].extend([
            Path(program_files) / "Google" / "Chrome Beta" / "Application" / "chrome.exe",
            Path(program_files_x86) / "Google" / "Chrome Beta" / "Application" / "chrome.exe",
        ])
        paths["stable"].extend([
            Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ])
        paths["canary"].extend([
            Path(local_app_data) / "Google" / "Chrome SxS" / "Application" / "chrome.exe",
        ])
        paths["edge"].extend([
            Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ])
    elif os_name == "Darwin":
        paths["beta"].append(Path("/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"))
        paths["stable"].append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        paths["canary"].append(Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"))
        paths["edge"].append(Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"))
    else:  # Linux
        paths["beta"].extend([Path("/usr/bin/google-chrome-beta"), Path("/opt/google/chrome-beta/google-chrome-beta")])
        paths["stable"].extend([Path("/usr/bin/google-chrome"), Path("/usr/bin/google-chrome-stable"), Path("/opt/google/chrome/google-chrome")])
        paths["edge"].extend([Path("/usr/bin/microsoft-edge"), Path("/usr/bin/microsoft-edge-stable")])

    # Filter to existing binaries
    detected = {}
    for channel, candidates in paths.items():
        found = [p for p in candidates if p.exists()]
        if found:
            detected[channel] = found[0]

    return detected


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a TCP port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def fetch_json(url: str):
    """Fetches JSON from local CDP HTTP endpoint."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Antigravity-CDP-Helper"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def sync_devtools_active_port(port: int = DEFAULT_PORT) -> list:
    """
    Syncs the active CDP port and WebSocket browser context path to DevToolsActivePort
    across standard Chrome and Chrome Beta user data directories.
    This fulfills the exact file requirement of Antigravity's chrome_devtools subagent tool.
    """
    version_info = fetch_json(f"http://127.0.0.1:{port}/json/version")
    if not version_info:
        return []

    ws_url = version_info.get("webSocketDebuggerUrl", "")
    ws_path = ""
    if "/devtools/browser/" in ws_url:
        ws_path = ws_url[ws_url.index("/devtools/browser/"):]

    content = f"{port}\n{ws_path}\n"

    target_dirs = []
    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        target_dirs.extend([
            Path(local_app_data) / "Google" / "Chrome" / "User Data",
            Path(local_app_data) / "Google" / "Chrome Beta" / "User Data",
        ])
    elif platform.system() == "Darwin":
        app_support = Path(os.path.expanduser("~/Library/Application Support"))
        target_dirs.extend([
            app_support / "Google" / "Chrome",
            app_support / "Google" / "Chrome Beta",
        ])
    else:
        config_dir = Path(os.path.expanduser("~/.config"))
        target_dirs.extend([
            config_dir / "google-chrome",
            config_dir / "google-chrome-beta",
        ])

    target_dirs.append(DEFAULT_DEBUG_PROFILE)

    synced = []
    for d in target_dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            port_file = d / "DevToolsActivePort"
            port_file.write_text(content, encoding="ascii")
            synced.append(port_file)
        except Exception:
            pass

    return synced


def cmd_status(args):
    """Checks the status of the CDP debugging port."""
    port = args.port
    print(f"Checking CDP status on http://127.0.0.1:{port}...")

    if not is_port_open(port):
        print(f"[FAIL] Port {port} is NOT listening.")
        print("\nWhy this usually happens:")
        print("  1. Chrome was launched WITHOUT --remote-debugging-port.")
        print("  2. CHROME SECURITY GUARDRAIL: Chrome was launched targeting the default user profile")
        print("     or an existing Chrome instance is running. Chrome silently disables the debugging")
        print("     port on the default user profile to protect saved credentials and active sessions.")
        print(f"\nFix: Launch with an isolated profile, e.g.:")
        print(f"  python scripts/browser_debug.py launch --channel beta")
        print(f"  or manual:")
        print(f'  chrome.exe --remote-debugging-port={port} --user-data-dir="{DEFAULT_DEBUG_PROFILE}"')
        return 1

    version_info = fetch_json(f"http://127.0.0.1:{port}/json/version")
    if not version_info:
        print(f"[WARN] Port {port} is open, but failed to return JSON from /json/version.")
        return 1

    print(f"[OK] CDP is ACTIVE and responding on port {port}!")
    print(f"     Browser:        {version_info.get('Browser')}")
    print(f"     Protocol:       {version_info.get('Protocol-Version')}")
    print(f"     V8 Version:     {version_info.get('V8-Version')}")
    print(f"     WebSocket URL:  {version_info.get('webSocketDebuggerUrl')}")

    tabs = fetch_json(f"http://127.0.0.1:{port}/json/list") or []
    page_tabs = [t for t in tabs if t.get("type") == "page"]
    print(f"     Active Pages:   {len(page_tabs)} open tab(s)")

    # Auto-sync DevToolsActivePort
    synced = sync_devtools_active_port(port)
    if synced:
        print(f"     DevTools Sync:  DevToolsActivePort refreshed for {len(synced)} profile directory(ies)")
    return 0


def cmd_sync(args):
    """Refreshes DevToolsActivePort files for Antigravity subagent discovery."""
    port = args.port
    print(f"Querying active browser session at port {port}...")
    synced = sync_devtools_active_port(port)
    if not synced:
        print(f"[FAIL] Could not query port {port} or write DevToolsActivePort.")
        return 1

    print(f"[OK] Successfully synchronized DevToolsActivePort to {len(synced)} location(s):")
    for p in synced:
        print(f"  * {p}")
    return 0


def cmd_list_tabs(args):
    """Lists inspectable browser tabs."""
    port = args.port
    tabs = fetch_json(f"http://127.0.0.1:{port}/json/list")
    if tabs is None:
        print(f"[FAIL] Cannot connect to http://127.0.0.1:{port}/json/list. Is Chrome running with debug port?")
        return 1

    page_tabs = [t for t in tabs if t.get("type") == "page"]
    if not page_tabs:
        print("No open browser pages found (only internal service workers / extensions).")
        return 0

    print(f"Found {len(page_tabs)} open tab(s):")
    for i, tab in enumerate(page_tabs, 1):
        title = tab.get("title", "(No title)")
        url = tab.get("url", "(Blank)")
        tab_id = tab.get("id", "")
        print(f"  [{i}] {title}")
        print(f"      URL: {url}")
        print(f"      ID:  {tab_id}")
    return 0


def cmd_find_browsers(args):
    """Lists detected browser executables on the system."""
    detected = get_browser_paths()
    print("Detected Browser Binaries on System:")
    if not detected:
        print("  No standard browser installations detected.")
        return 1

    for channel, path in detected.items():
        print(f"  * {channel.upper():<7}: {path}")
    return 0


def cmd_launch(args):
    """Launches Chrome with remote debugging and isolated profile."""
    port = args.port
    profile_dir = Path(os.path.expanduser(args.profile_dir)).resolve()
    channel = args.channel.lower()
    url = args.url

    detected = get_browser_paths()
    if channel not in detected:
        # Fallback to available
        if "beta" in detected:
            print(f"Channel '{channel}' not found; falling back to 'beta'.")
            channel = "beta"
        elif "stable" in detected:
            print(f"Channel '{channel}' not found; falling back to 'stable'.")
            channel = "stable"
        else:
            print(f"[FAIL] No executable found for channel '{channel}'. Detected: {list(detected.keys())}")
            return 1

    browser_exe = detected[channel]
    profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(browser_exe),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    if url:
        cmd.append(url)

    print(f"Launching {channel.upper()} for Antigravity /browser...")
    print(f"  Binary:  {browser_exe}")
    print(f"  Port:    {port}")
    print(f"  Profile: {profile_dir}")

    # Launch detached process
    if platform.system() == "Windows":
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(cmd, creationflags=DETACHED_PROCESS, close_fds=True)
    else:
        subprocess.Popen(cmd, start_new_session=True)

    print("Waiting for CDP endpoint to become ready...")
    for _ in range(10):
        time.sleep(0.5)
        if is_port_open(port):
            version_info = fetch_json(f"http://127.0.0.1:{port}/json/version")
            if version_info:
                print(f"[OK] Success! Chrome {channel.upper()} is ready on port {port}.")
                print(f"     Browser: {version_info.get('Browser')}")
                synced = sync_devtools_active_port(port)
                if synced:
                    print(f"     DevTools Sync: DevToolsActivePort synced to {len(synced)} profile directory(ies)")
                print(f"     Antigravity `/browser` can now connect and inspect tabs.")
                return 0

    print(f"[WARN] Launched process, but port {port} did not respond within 5 seconds.")
    print("Check if another instance is locking the profile or if security software blocked the port.")
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Antigravity Browser Debug & Chrome DevTools Protocol (CDP) Helper"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="CDP remote debugging port (default: 9222)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Check CDP port status and connected browser info")
    p_status.set_defaults(func=cmd_status)

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize DevToolsActivePort files for Antigravity subagent")
    p_sync.set_defaults(func=cmd_sync)

    # list-tabs
    p_list = subparsers.add_parser("list-tabs", help="List active inspectable browser tabs")
    p_list.set_defaults(func=cmd_list_tabs)

    # find-browsers
    p_find = subparsers.add_parser("find-browsers", help="Find installed Chrome/Edge binaries on host")
    p_find.set_defaults(func=cmd_find_browsers)

    # launch
    p_launch = subparsers.add_parser("launch", help="Launch Chrome with debugging port and isolated profile")
    p_launch.add_argument("--channel", choices=["beta", "stable", "canary", "edge"], default="beta",
                          help="Browser channel to launch (default: beta)")
    p_launch.add_argument("--profile-dir", default=str(DEFAULT_DEBUG_PROFILE),
                          help=f"Isolated user data directory (default: {DEFAULT_DEBUG_PROFILE})")
    p_launch.add_argument("--url", default="", help="Optional initial URL to open")
    p_launch.set_defaults(func=cmd_launch)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
