import os
import sys
import sqlite3
import shutil
import argparse
import subprocess

def is_app_running():
    if sys.platform == 'win32':
        try:
            output = subprocess.check_output('tasklist /FI "IMAGENAME eq Antigravity.exe"', shell=True)
            return b"Antigravity.exe" in output
        except Exception:
            pass
    return False

def merge_databases(src_db, dst_db):
    print(f"Merging workspace database {os.path.basename(src_db)}...")
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
        print("  Workspace database merged successfully.")
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            print("  ERROR: Database is locked! Please close the Antigravity application and try again.")
            sys.exit(1)
        else:
            print(f"  Error merging workspace database: {e}")
    except Exception as e:
        print(f"  Error merging workspace database: {e}")
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Sync and merge Antigravity 2.0 conversations and summaries.")
    parser.add_argument("--source", required=True, help="Path to source Antigravity profile directory (e.g. C:\\Users\\username\\.gemini-machine-a\\antigravity)")
    parser.add_argument("--target", required=True, help="Path to target Antigravity profile directory (e.g. C:\\Users\\username\\.gemini\\antigravity)")
    parser.add_argument("--force", action="store_true", help="Force execution even if Antigravity is detected running.")
    args = parser.parse_args()
    
    src_dir = os.path.abspath(args.source)
    dst_dir = os.path.abspath(args.target)
    
    if not os.path.exists(src_dir):
        print(f"Source directory '{src_dir}' does not exist.")
        return
        
    # Check if Antigravity is running to prevent database lock issues
    if is_app_running() and not args.force:
        print("="*65)
        print("WARNING: Antigravity desktop application is currently running!")
        print("Running this script while the app is open can lock the SQLite and index files, causing failures.")
        print("="*65)
        print("\nTo avoid this issue, please:")
        print("  1. Close the Antigravity desktop application.")
        print("  2. Run the sync command in an external terminal:")
        print(f"     python sync.py --source \"{src_dir}\" --target \"{dst_dir}\"")
        print("\n(Or pass --force to run anyway.)")
        sys.exit(1)
        
    src_conv_dir = os.path.join(src_dir, "conversations")
    dst_conv_dir = os.path.join(dst_dir, "conversations")

    src_proj_dir = os.path.join(src_dir, "config", "projects")
    dst_proj_dir = os.path.join(dst_dir, "config", "projects")

    src_proto = os.path.join(src_dir, "agyhub_summaries_proto.pb")
    dst_proto = os.path.join(dst_dir, "agyhub_summaries_proto.pb")

    # Step 1: Projects
    print("--- STEP 1: Copying project config files ---")
    if os.path.exists(src_proj_dir):
        os.makedirs(dst_proj_dir, exist_ok=True)
        for f in os.listdir(src_proj_dir):
            if f.endswith('.json'):
                src_file = os.path.join(src_proj_dir, f)
                dst_file = os.path.join(dst_proj_dir, f)
                if not os.path.exists(dst_file):
                    print(f"Copying project config {f}...")
                    shutil.copy2(src_file, dst_file)
    else:
        print("No source projects folder found. Skipping.")

    # Step 2: Conversations
    print("\n--- STEP 2: Copying and merging conversations ---")
    if os.path.exists(src_conv_dir):
        os.makedirs(dst_conv_dir, exist_ok=True)
        for f in os.listdir(src_conv_dir):
            src_path = os.path.join(src_conv_dir, f)
            dst_path = os.path.join(dst_conv_dir, f)
            
            if f.endswith('.db-shm') or f.endswith('.db-wal'):
                continue
                
            if f.endswith('.pb') or f.endswith('.tmp'):
                if not os.path.exists(dst_path):
                    print(f"Copying conversation file {f}...")
                    shutil.copy2(src_path, dst_path)
            elif f.endswith('.db'):
                if not os.path.exists(dst_path):
                    print(f"Copying database file {f}...")
                    shutil.copy2(src_path, dst_path)
                else:
                    merge_databases(src_path, dst_path)
    else:
        print("No source conversations folder found.")

    # Step 3: Summaries Index
    print("\n--- STEP 3: Merging conversation summaries index ---")
    if os.path.exists(src_proto) and os.path.exists(dst_proto):
        shutil.copy2(dst_proto, dst_proto + ".bak")
        print(f"Backup created: {dst_proto}.bak")
        
        with open(src_proto, 'rb') as f_src:
            src_bytes = f_src.read()
        with open(dst_proto, 'rb') as f_dst:
            dst_bytes = f_dst.read()
            
        merged_bytes = dst_bytes + src_bytes
        with open(dst_proto, 'wb') as f_dst:
            f_dst.write(merged_bytes)
        print("Merged agyhub_summaries_proto.pb successfully.")
    elif os.path.exists(src_proto):
        print("Target summaries index not found, copying source summaries index directly.")
        shutil.copy2(src_proto, dst_proto)
    else:
        print("No summaries index file found to merge.")

    print("\nDone! Sync and merge completed successfully.")

if __name__ == '__main__':
    main()
