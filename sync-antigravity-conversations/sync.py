import os
import sys
import sqlite3
import shutil
import argparse
import subprocess
import tempfile
import zipfile
import time
from datetime import datetime, timezone, timedelta

# Fix console encoding on Windows to prevent UnicodeEncodeError with emojis/special chars
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def is_app_running():
    if sys.platform == 'win32':
        try:
            output = subprocess.check_output('tasklist /FI "IMAGENAME eq Antigravity.exe"', shell=True)
            return b"Antigravity.exe" in output
        except Exception:
            pass
    return False

def test_db_writable(db_path):
    if not os.path.exists(db_path):
        return True
    try:
        conn = sqlite3.connect(db_path, timeout=1.0)
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        conn.rollback()
        conn.close()
        return True
    except Exception:
        return False

def merge_databases(src_db, dst_db, dry_run=False):
    print(f"    Merging conversation database {os.path.basename(src_db)}...")
    if dry_run:
        return
    if not os.path.exists(dst_db + ".bak"):
        shutil.copy2(dst_db, dst_db + ".bak")
    
    conn = sqlite3.connect(dst_db)
    cursor = conn.cursor()
    try:
        cursor.execute("ATTACH DATABASE ? AS src", (src_db,))
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall() if r[0] != 'sqlite_sequence']
        
        for table in tables:
            cursor.execute(f"SELECT count(*) FROM src.sqlite_master WHERE type='table' AND name='{table}'")
            if cursor.fetchone()[0] > 0:
                cursor.execute(f"INSERT OR IGNORE INTO {table} SELECT * FROM src.{table}")
        conn.commit()
    except Exception as e:
        print(f"      Warning merging db tables: {e}")
    finally:
        conn.close()

def parse_iso_datetime(dt_str):
    if not dt_str:
        return None
    try:
        s = dt_str.strip()
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def copy_tree_contents(src_dir, dst_dir, dry_run=False):
    if not os.path.exists(src_dir):
        return 0
    copied = 0
    for root, dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        target_root = os.path.join(dst_dir, rel)
        if not dry_run:
            os.makedirs(target_root, exist_ok=True)
        for f in files:
            src_f = os.path.join(root, f)
            dst_f = os.path.join(target_root, f)
            if not os.path.exists(dst_f):
                if not dry_run:
                    shutil.copy2(src_f, dst_f)
                copied += 1
            else:
                try:
                    if os.path.getmtime(src_f) > os.path.getmtime(dst_f):
                        if not dry_run:
                            shutil.copy2(src_f, dst_f)
                        copied += 1
                except Exception:
                    pass
    return copied

def sync_profile(src_profile, dst_profile, cutoff_dt=None, file_timestamps=None, dry_run=False):
    profile_name = os.path.basename(src_profile)
    print(f"\n==========================================")
    print(f"Processing Profile: {profile_name}")
    print(f"  Source: {src_profile}")
    print(f"  Target: {dst_profile}")
    print(f"==========================================")
    
    if not os.path.exists(src_profile):
        print(f"Source profile directory does not exist: {src_profile}")
        return set(), 0

    if not dry_run:
        os.makedirs(dst_profile, exist_ok=True)

    src_conv_dir = os.path.join(src_profile, "conversations")
    dst_conv_dir = os.path.join(dst_profile, "conversations")
    src_brain_dir = os.path.join(src_profile, "brain")
    dst_brain_dir = os.path.join(dst_profile, "brain")
    src_ann_dir = os.path.join(src_profile, "annotations")
    dst_ann_dir = os.path.join(dst_profile, "annotations")
    
    src_sum_db = os.path.join(src_profile, "conversation_summaries.db")
    dst_sum_db = os.path.join(dst_profile, "conversation_summaries.db")
    
    selected_cids = {}  # cid -> metadata dict
    known_db_cids = set()
    all_projects = set()

    # 1. Discover conversations from conversation_summaries.db
    if os.path.exists(src_sum_db):
        try:
            conn = sqlite3.connect(src_sum_db)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM conversation_summaries")
            for row in cursor.fetchall():
                cid = row["conversation_id"]
                known_db_cids.add(cid)
                
                lmt_str = row["last_modified_time"]
                luit_str = row["last_user_input_time"] if "last_user_input_time" in row.keys() else None
                
                lmt = parse_iso_datetime(lmt_str)
                luit = parse_iso_datetime(luit_str)
                
                match = True
                if cutoff_dt:
                    match = False
                    if lmt and lmt >= cutoff_dt:
                        match = True
                    elif luit and luit >= cutoff_dt:
                        match = True
                
                if match:
                    selected_cids[cid] = dict(row)
                    if "project_id" in row.keys() and row["project_id"]:
                        all_projects.add(row["project_id"])
            conn.close()
        except Exception as e:
            print(f"Warning reading source summaries db: {e}")

    # 2. Check conversations/ folder for sessions NOT in conversation_summaries.db
    if os.path.exists(src_conv_dir):
        for f in os.listdir(src_conv_dir):
            if f.endswith('.db-shm') or f.endswith('.db-wal'):
                continue
            base, ext = os.path.splitext(f)
            if ext in ('.db', '.pb', '.tmp'):
                cid = base
                # ONLY consider files that are NOT tracked in conversation_summaries.db
                if cid not in known_db_cids:
                    mtime = None
                    if file_timestamps:
                        rel_path = f"{profile_name}/conversations/{f}".replace('\\', '/')
                        for k, v in file_timestamps.items():
                            if k.endswith(rel_path):
                                mtime = v
                                break
                    if mtime is None:
                        filepath = os.path.join(src_conv_dir, f)
                        try:
                            mtime = datetime.fromtimestamp(os.path.getmtime(filepath), timezone.utc)
                        except Exception:
                            pass
                    
                    if not cutoff_dt or (mtime and mtime >= cutoff_dt):
                        selected_cids[cid] = {"conversation_id": cid, "file_only": True}

    print(f"Found {len(selected_cids)} conversations matching criteria.")
    if not selected_cids:
        return all_projects, 0

    # 3. Check destination locks if target exists
    if os.path.exists(dst_sum_db) and not test_db_writable(dst_sum_db):
        print(f"ERROR: Destination database {dst_sum_db} is locked! Please close Antigravity.")
        if not dry_run:
            sys.exit(1)

    # 4. Copy & merge conversation files
    if not dry_run:
        os.makedirs(dst_conv_dir, exist_ok=True)
    conv_files_synced = 0
    for cid in selected_cids:
        if os.path.exists(src_conv_dir):
            for ext in ('.db', '.pb', '.tmp'):
                fname = cid + ext
                src_file = os.path.join(src_conv_dir, fname)
                dst_file = os.path.join(dst_conv_dir, fname)
                if os.path.exists(src_file):
                    if not os.path.exists(dst_file):
                        if not dry_run:
                            shutil.copy2(src_file, dst_file)
                        conv_files_synced += 1
                    elif ext == '.db':
                        merge_databases(src_file, dst_file, dry_run=dry_run)
                        conv_files_synced += 1

    print(f"Synced {conv_files_synced} conversation data files.")

    # 5. Copy Brain folders
    brain_synced = 0
    if os.path.exists(src_brain_dir):
        if not dry_run:
            os.makedirs(dst_brain_dir, exist_ok=True)
        for cid in selected_cids:
            src_b = os.path.join(src_brain_dir, cid)
            dst_b = os.path.join(dst_brain_dir, cid)
            if os.path.exists(src_b):
                copied = copy_tree_contents(src_b, dst_b, dry_run=dry_run)
                if copied > 0:
                    brain_synced += 1

    print(f"Synced brain artifacts for {brain_synced} conversations.")

    # 6. Copy Annotations
    ann_synced = 0
    if os.path.exists(src_ann_dir):
        if not dry_run:
            os.makedirs(dst_ann_dir, exist_ok=True)
        for cid in selected_cids:
            src_a = os.path.join(src_ann_dir, f"{cid}.pbtxt")
            dst_a = os.path.join(dst_ann_dir, f"{cid}.pbtxt")
            if os.path.exists(src_a):
                if not os.path.exists(dst_a) or os.path.getmtime(src_a) > os.path.getmtime(dst_a):
                    if not dry_run:
                        shutil.copy2(src_a, dst_a)
                    ann_synced += 1

    print(f"Synced {ann_synced} annotation files.")

    # 7. Merge conversation_summaries.db
    summaries_merged = 0
    if os.path.exists(src_sum_db) and any("title" in meta for meta in selected_cids.values()):
        if not dry_run:
            if os.path.exists(dst_sum_db):
                backup_path = dst_sum_db + ".bak"
                if not os.path.exists(backup_path):
                    shutil.copy2(dst_sum_db, backup_path)
            else:
                conn_src = sqlite3.connect(src_sum_db)
                conn_dst = sqlite3.connect(dst_sum_db)
                for line in conn_src.iterdump():
                    if "INSERT INTO" not in line:
                        try:
                            conn_dst.execute(line)
                        except Exception:
                            pass
                conn_dst.commit()
                conn_src.close()
                conn_dst.close()

            conn_dst = sqlite3.connect(dst_sum_db)
            cursor_dst = conn_dst.cursor()
            
            cursor_dst.execute("PRAGMA table_info(conversation_summaries)")
            cols = [r[1] for r in cursor_dst.fetchall()]
            cols_str = ", ".join(cols)
            placeholders = ", ".join(["?"] * len(cols))
            
            for cid, meta in selected_cids.items():
                if "title" not in meta:
                    continue
                cursor_dst.execute("SELECT last_modified_time FROM conversation_summaries WHERE conversation_id = ?", (cid,))
                existing = cursor_dst.fetchone()
                
                values = [meta.get(col, None) for col in cols]
                if not existing:
                    cursor_dst.execute(f"INSERT INTO conversation_summaries ({cols_str}) VALUES ({placeholders})", values)
                    summaries_merged += 1
                else:
                    src_lmt = parse_iso_datetime(meta.get("last_modified_time"))
                    dst_lmt = parse_iso_datetime(existing[0])
                    if src_lmt and dst_lmt and src_lmt > dst_lmt:
                        set_clause = ", ".join([f"{col} = ?" for col in cols if col != "conversation_id"])
                        update_values = [meta.get(col, None) for col in cols if col != "conversation_id"] + [cid]
                        cursor_dst.execute(f"UPDATE conversation_summaries SET {set_clause} WHERE conversation_id = ?", update_values)
                        summaries_merged += 1
            conn_dst.commit()
            conn_dst.close()
        else:
            summaries_merged = sum(1 for m in selected_cids.values() if "title" in m)

    print(f"Merged {summaries_merged} records in conversation_summaries.db.")

    # 8. Merge proto summaries index
    proto_name = "jetbox_summaries_proto.pb" if "cli" in profile_name else "agyhub_summaries_proto.pb"
    src_proto = os.path.join(src_profile, proto_name)
    dst_proto = os.path.join(dst_profile, proto_name)
    
    if os.path.exists(src_proto) or any(meta.get("raw_summary") for meta in selected_cids.values()):
        if not dry_run:
            dst_proto_data = b""
            if os.path.exists(dst_proto):
                backup_proto = dst_proto + ".bak"
                if not os.path.exists(backup_proto):
                    shutil.copy2(dst_proto, backup_proto)
                with open(dst_proto, "rb") as f:
                    dst_proto_data = f.read()

            appended_count = 0
            new_blobs = []
            for cid, meta in selected_cids.items():
                raw = meta.get("raw_summary")
                if raw and isinstance(raw, (bytes, bytearray)):
                    if raw not in dst_proto_data:
                        new_blobs.append(raw)
                        appended_count += 1
            
            if new_blobs:
                with open(dst_proto, "ab" if dst_proto_data else "wb") as f:
                    for b in new_blobs:
                        f.write(b)
                print(f"Appended {appended_count} summaries to {proto_name}.")
            elif not os.path.exists(dst_proto) and os.path.exists(src_proto):
                shutil.copy2(src_proto, dst_proto)
                print(f"Copied {proto_name} to target.")
        else:
            proto_count = sum(1 for m in selected_cids.values() if m.get("raw_summary"))
            print(f"Would append {proto_count} summaries to {proto_name}.")

    return all_projects, len(selected_cids)

def main():
    parser = argparse.ArgumentParser(description="Sync and merge Antigravity conversations, summaries, and projects.")
    parser.add_argument("--source", required=True, help="Path to source Antigravity profile directory or .zip archive (e.g. gemini-aili.zip)")
    parser.add_argument("--target", default=r"C:\Users\yclian\.gemini", help="Path to target directory (default: C:\\Users\\yclian\\.gemini)")
    parser.add_argument("--days", type=int, default=None, help="Import conversations from the last N days (e.g. 30)")
    parser.add_argument("--since", default=None, help="Import conversations modified on or after ISO date (e.g. 2026-08-29)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and simulate sync without making changes.")
    parser.add_argument("--force", action="store_true", help="Force execution even if Antigravity is detected running.")
    args = parser.parse_args()

    cutoff_dt = None
    if args.days is not None:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=args.days)
        print(f"Cutoff filter: last {args.days} days (>= {cutoff_dt.isoformat()})")
    elif args.since is not None:
        cutoff_dt = parse_iso_datetime(args.since)
        if cutoff_dt and cutoff_dt.tzinfo is None:
            cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)
        print(f"Cutoff filter: since {args.since} (>= {cutoff_dt.isoformat()})")

    if is_app_running() and not args.force and not args.dry_run:
        print("="*65)
        print("WARNING: Antigravity desktop application is currently running!")
        print("Running this script while the app is open can lock SQLite and index files.")
        print("="*65)
        print("\nPlease close the Antigravity desktop application, or pass --force to run anyway.")
        sys.exit(1)

    source_path = os.path.abspath(args.source)
    target_path = os.path.abspath(args.target)

    temp_extract_dir = None
    file_timestamps = {}
    try:
        if zipfile.is_zipfile(source_path):
            print(f"Source is a zip archive: {source_path}")
            temp_extract_dir = tempfile.mkdtemp(prefix="agy_sync_extract_")
            print(f"Extracting zip to temporary folder: {temp_extract_dir} ...")
            with zipfile.ZipFile(source_path, 'r') as z:
                for info in z.infolist():
                    dt = datetime(*info.date_time, tzinfo=timezone.utc)
                    file_timestamps[info.filename.replace('\\', '/')] = dt
                    z.extract(info, temp_extract_dir)
                    extracted_path = os.path.join(temp_extract_dir, info.filename)
                    if not info.is_dir() and os.path.exists(extracted_path):
                        epoch = time.mktime(info.date_time + (0, 0, -1))
                        try:
                            os.utime(extracted_path, (epoch, epoch))
                        except Exception:
                            pass
            
            if os.path.exists(os.path.join(temp_extract_dir, ".gemini")):
                src_root = os.path.join(temp_extract_dir, ".gemini")
            else:
                src_root = temp_extract_dir
        else:
            src_root = source_path

        if not os.path.exists(src_root):
            print(f"Source root does not exist: {src_root}")
            sys.exit(1)

        print(f"Source root: {src_root}")
        print(f"Target root: {target_path}")

        known_profiles = ["antigravity", "antigravity-cli", "antigravity-ide"]
        
        is_src_single_profile = os.path.exists(os.path.join(src_root, "conversations")) or os.path.exists(os.path.join(src_root, "conversation_summaries.db"))
        is_dst_single_profile = os.path.exists(os.path.join(target_path, "conversations")) or os.path.exists(os.path.join(target_path, "conversation_summaries.db"))

        all_needed_projects = set()
        total_convs = 0

        if is_src_single_profile and is_dst_single_profile:
            projects, count = sync_profile(src_root, target_path, cutoff_dt=cutoff_dt, file_timestamps=file_timestamps, dry_run=args.dry_run)
            all_needed_projects.update(projects)
            total_convs += count
        else:
            for p in known_profiles:
                src_p = os.path.join(src_root, p)
                dst_p = os.path.join(target_path, p)
                if os.path.exists(src_p):
                    projects, count = sync_profile(src_p, dst_p, cutoff_dt=cutoff_dt, file_timestamps=file_timestamps, dry_run=args.dry_run)
                    all_needed_projects.update(projects)
                    total_convs += count

        print(f"\n==========================================")
        print(f"Processing Projects Configurations")
        print(f"==========================================")
        src_proj_dir = os.path.join(src_root, "config", "projects")
        dst_proj_dir = os.path.join(target_path, "config", "projects")
        
        if not os.path.exists(src_proj_dir):
            alt_src = os.path.abspath(os.path.join(src_root, "..", "config", "projects"))
            if os.path.exists(alt_src):
                src_proj_dir = alt_src
        if not os.path.exists(dst_proj_dir):
            alt_dst = os.path.abspath(os.path.join(target_path, "..", "config", "projects"))
            if os.path.exists(alt_dst):
                dst_proj_dir = alt_dst

        projects_copied = 0
        if os.path.exists(src_proj_dir):
            if not args.dry_run:
                os.makedirs(dst_proj_dir, exist_ok=True)
            for f in os.listdir(src_proj_dir):
                if f.endswith('.json'):
                    proj_id = os.path.splitext(f)[0]
                    if not all_needed_projects or proj_id in all_needed_projects:
                        src_f = os.path.join(src_proj_dir, f)
                        dst_f = os.path.join(dst_proj_dir, f)
                        if not os.path.exists(dst_f):
                            if not args.dry_run:
                                shutil.copy2(src_f, dst_f)
                            projects_copied += 1
            print(f"Synced {projects_copied} project configuration files.")
        else:
            print("No projects configuration folder found.")

        print(f"\n==========================================")
        print(f"Sync {'Simulation' if args.dry_run else 'Completed'} Successfully!")
        print(f"Total conversations processed: {total_convs}")
        print(f"==========================================")

    finally:
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            print("Cleaning up temporary extraction folder...")
            try:
                shutil.rmtree(temp_extract_dir)
            except Exception as e:
                print(f"Note: Could not completely remove temp dir: {e}")

if __name__ == '__main__':
    main()
