#!/usr/bin/env python3
"""
Antigravity Scheduled Task Manager CLI
Manages persistent scheduled tasks (sidecars) for the Antigravity desktop application.
"""

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path


def get_gemini_dir() -> Path:
    return Path(os.path.expanduser("~/.gemini"))


def get_config_json_path() -> Path:
    return get_gemini_dir() / "config" / "config.json"


def get_sidecars_dir() -> Path:
    return get_gemini_dir() / "config" / "sidecars"


def get_sidecar_data_dir() -> Path:
    return get_gemini_dir() / "antigravity" / "sidecar_data"


def get_projects_dir() -> Path:
    return get_gemini_dir() / "config" / "projects"


def load_config() -> dict:
    cfg_path = get_config_json_path()
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict):
    cfg_path = get_config_json_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def list_projects() -> dict:
    projects = {}
    p_dir = get_projects_dir()
    if p_dir.exists():
        for p_file in p_dir.glob("*.json"):
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pid = data.get("id", p_file.stem)
                    name = data.get("name", "Unnamed")
                    projects[pid] = name
            except Exception:
                pass
    return projects


def cmd_list(args):
    cfg = load_config()
    registered = cfg.get("sidecars", {})
    sidecars_dir = get_sidecars_dir()

    tasks = {}
    # Scan filesystem sidecars
    if sidecars_dir.exists():
        for sc_folder in sidecars_dir.iterdir():
            if sc_folder.is_dir():
                sc_file = sc_folder / "sidecar.json"
                if sc_file.exists():
                    try:
                        with open(sc_file, "r", encoding="utf-8") as f:
                            tasks[sc_folder.name] = json.load(f)
                    except Exception as e:
                        tasks[sc_folder.name] = {"error": str(e)}

    all_keys = sorted(set(list(registered.keys()) + list(tasks.keys())))
    if not all_keys:
        print("No scheduled tasks found.")
        return

    print(f"{'NAME':<26} {'ENABLED':<9} {'CRON':<14} {'DISPLAY NAME':<26} {'PROJECT ID'}")
    print("-" * 105)

    projects = list_projects()

    for name in all_keys:
        reg_info = registered.get(name, {})
        enabled = reg_info.get("enabled", False)
        pid = reg_info.get("projectId", "")
        p_label = f"{projects.get(pid, pid[:8])}" if pid else "None"

        task_def = tasks.get(name, {})
        display_name = task_def.get("display_name", name)
        cron_expr = "N/A"
        args_list = task_def.get("args", [])
        if args_list and len(args_list) > 0:
            cron_expr = args_list[0]

        status_str = "Yes" if enabled else "No"
        print(f"{name:<26} {status_str:<9} {cron_expr:<14} {display_name:<26} {p_label} ({pid})")


def cmd_add(args):
    name = args.name.strip().lower().replace(" ", "-")
    cron = args.cron.strip()
    prompt = args.prompt.strip()
    display_name = (args.display_name or args.name).strip()

    # Determine project ID
    cfg = load_config()
    sidecars = cfg.setdefault("sidecars", {})
    pid = args.project_id
    if not pid:
        # Default to existing projectId if present in any active sidecar
        for sc in sidecars.values():
            if isinstance(sc, dict) and sc.get("projectId"):
                pid = sc["projectId"]
                break
        if not pid:
            projects = list_projects()
            if projects:
                pid = next(iter(projects.keys()))

    if not pid:
        print("Error: No project ID provided and could not automatically detect a default project.", file=sys.stderr)
        sys.exit(1)

    # 1. Write sidecar.json
    sc_dir = get_sidecars_dir() / name
    sc_dir.mkdir(parents=True, exist_ok=True)
    sc_file = sc_dir / "sidecar.json"

    sidecar_data = {
        "builtin": "schedule",
        "args": [
            cron,
            "agentapi",
            "new-conversation",
            prompt
        ],
        "display_name": display_name
    }

    with open(sc_file, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, indent=2)
    print(f"Wrote sidecar definition: {sc_file}")

    # 2. Register in config.json
    sidecars[name] = {
        "enabled": not args.disabled,
        "projectId": pid
    }
    save_config(cfg)
    print(f"Registered and enabled task '{name}' in config.json (projectId: {pid})")

    # 3. Check for scheduler activation
    print("Waiting 2 seconds for Antigravity scheduler daemon to pick up the task...")
    time.sleep(2)
    cmd_status(argparse.Namespace(name=name))


def cmd_status(args):
    name = args.name
    data_dir = get_sidecar_data_dir() / name / "logs"
    if not data_dir.exists():
        print(f"No execution logs found yet at {data_dir}")
        return

    logs = sorted(glob.glob(str(data_dir / "*.log")), key=os.path.getmtime)
    if not logs:
        print(f"No logs found in {data_dir}")
        return

    latest = logs[-1]
    print(f"\n--- Latest scheduler log: {os.path.basename(latest)} ---")
    try:
        with open(latest, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            for line in lines[-15:]:
                print(line.rstrip())
    except Exception as e:
        print(f"Error reading log: {e}")


def cmd_remove(args):
    name = args.name
    cfg = load_config()
    sidecars = cfg.get("sidecars", {})

    if name in sidecars:
        del sidecars[name]
        save_config(cfg)
        print(f"Deregistered '{name}' from config.json")
    else:
        print(f"Task '{name}' not found in config.json")

    sc_file = get_sidecars_dir() / name / "sidecar.json"
    if sc_file.exists():
        try:
            sc_file.unlink()
            (get_sidecars_dir() / name).rmdir()
            print(f"Removed sidecar file: {sc_file}")
        except Exception as e:
            print(f"Notice: Could not remove directory {sc_file.parent}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Manage Antigravity Scheduled Tasks (Sidecars)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    subparsers.add_parser("list", help="List all scheduled tasks")

    # add
    p_add = subparsers.add_parser("add", help="Add or update a scheduled task")
    p_add.add_argument("--name", required=True, help="Task identifier (e.g. gmail-forward-watchdog)")
    p_add.add_argument("--cron", required=True, help="Cron expression (e.g. '15 7 * * *')")
    p_add.add_argument("--prompt", required=True, help="Prompt executed on trigger")
    p_add.add_argument("--display-name", help="Display name in Antigravity UI")
    p_add.add_argument("--project-id", help="Antigravity Project UUID")
    p_add.add_argument("--disabled", action="store_true", help="Register as disabled")

    # status
    p_status = subparsers.add_parser("status", help="Check status and latest log of a task")
    p_status.add_argument("--name", required=True, help="Task identifier")

    # remove
    p_rem = subparsers.add_parser("remove", help="Remove a scheduled task")
    p_rem.add_argument("--name", required=True, help="Task identifier")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "remove":
        cmd_remove(args)


if __name__ == "__main__":
    main()
