#!/usr/bin/env python3
"""
Helper script to safely add a new alias or sender domain to Tier-2 across F1, F2, and F3
maintaining exact partition symmetry and running the linter automatically.
"""

import argparse
import json
import os
import re
import sys

DEFAULT_LOCATIONS = [
    os.environ.get("GMAIL_FILTERS_TFVARS"),
    "filters.auto.tfvars.json",
    os.path.join("terraform", "envs", "gateway", "filters.auto.tfvars.json"),
    os.path.join("..", "terraform", "envs", "gateway", "filters.auto.tfvars.json"),
]

def find_default_tfvars():
    for loc in DEFAULT_LOCATIONS:
        if loc and os.path.exists(loc):
            return os.path.abspath(loc)
    return "filters.auto.tfvars.json"

def insert_into_clause(query, clause_name, token):
    pattern = rf'({clause_name}:\([^)]+)\)'
    match = re.search(pattern, query)
    if not match:
        raise ValueError(f"Could not find '{clause_name}:(...)' block in filter query.")
    
    inner = match.group(1)
    if token in inner:
        return query  # Already present
    
    updated_inner = f"{inner} OR {token})"
    return query[:match.start()] + updated_inner + query[match.end():]

def add_to_tier2(alias_or_domain, tfvars_path=None, is_sender=False):
    target_path = tfvars_path or find_default_tfvars()
    if not os.path.exists(target_path):
        print(f"Error: {target_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    filters = data.get("filters", [])
    f1 = next((f for f in filters if f.get("key") == "filter_001"), None)
    f2 = next((f for f in filters if f.get("key") == "filter_002"), None)
    f3 = next((f for f in filters if f.get("key") == "filter_003"), None)

    if not (f1 and f2 and f3):
        print("Error: Could not locate filter_001, filter_002, and filter_003 in tfvars.", file=sys.stderr)
        sys.exit(1)

    token = alias_or_domain.strip().lower()
    clause = "from" if is_sender else "to"

    for f in (f1, f2, f3):
        q = f["criteria"]["query"]
        try:
            f["criteria"]["query"] = insert_into_clause(q, clause, token)
        except ValueError as e:
            print(f"Error updating {f['key']}: {e}", file=sys.stderr)
            sys.exit(1)

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Successfully added '{token}' to F1, F2, and F3 in {target_path}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add alias or sender to Tier-2 with symmetry.")
    parser.add_argument("token", help="Alias (e.g. newsletter@yourdomain.com) or sender domain (e.g. promo@example.com)")
    parser.add_argument("--sender", action="store_true", help="Add as sender domain rather than recipient alias")
    parser.add_argument("--path", default=None, help="Path to filters.auto.tfvars.json (auto-detected if omitted)")
    args = parser.parse_args()

    add_to_tier2(args.token, args.path, is_sender=args.sender)
