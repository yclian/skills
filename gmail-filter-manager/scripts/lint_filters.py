#!/usr/bin/env python3
"""
Gmail Filter Architecture Linter
Validates Gmail filter queries in Terraform tfvars against known Gmail SMTP
delivery engine quirks and limits to prevent silent forwarding or archiving failures.

Exit codes:
0 = Clean (All invariants satisfied)
1 = Lint violations detected (Do not apply)
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

def lint_filter_query(key, query, criteria):
    errors = []
    warnings = []

    if "negated_query" in criteria:
        errors.append(
            f"[{key}] Uses 'negated_query' in criteria. In Gmail API/Terraform, "
            f"'negated_query' silently breaks email forwarding (incident 2026.W37). "
            f"Always use positive 'query' with disjoint partition."
        )

    if not query:
        return errors, warnings

    if query.count("(") != query.count(")"):
        errors.append(f"[{key}] Unbalanced parentheses: {query.count('(')} open vs {query.count(')')} close.")
    if query.count('"') % 2 != 0:
        errors.append(f"[{key}] Unbalanced double quotes.")

    if key == "filter_001":
        idx = 0
        while True:
            pos = query.find("-(", idx)
            if pos == -1:
                break
            depth = 0
            start = pos + 1
            end = -1
            for i in range(start, len(query)):
                if query[i] == '(':
                    depth += 1
                elif query[i] == ')':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end != -1:
                neg_content = query[pos + 2:end]
                if ("to:" in neg_content or "from:" in neg_content) and ("subject:" in neg_content or "filename:" in neg_content):
                    errors.append(
                        f"[{key}] Prohibited nested compound boolean inside negation: -({neg_content[:70]}...). "
                        f"Gmail SMTP delivery engine silently aborts filter execution on compound conditions. "
                        f"Keep top-level negations flat (e.g. -subject:(...) -filename:ics)."
                    )
                idx = end + 1
            else:
                break

    if len(query) > 2800:
        warnings.append(
            f"[{key}] Query length is {len(query)} characters. Queries approaching 3000 chars "
            f"risk hitting Gmail filter query truncation limits."
        )

    return errors, warnings

def check_partition_symmetry(filters_dict):
    errors = []
    warnings = []
    if "filter_001" not in filters_dict or "filter_003" not in filters_dict:
        return errors, warnings

    q1 = filters_dict["filter_001"].get("criteria", {}).get("query", "")
    q3 = filters_dict["filter_003"].get("criteria", {}).get("query", "")

    f1_matches = re.findall(r'-subject:\(([^)]+)\)', q1)
    f3_matches = re.findall(r'\(subject:\(([^)]+)\)', q3)

    if f1_matches and f3_matches:
        f1_tail = f1_matches[-1].strip()
        f3_tail = f3_matches[-1].strip()
        if f1_tail != f3_tail:
            errors.append(
                "[Partition Symmetry Error] Discrepancy between F1 (-subject) tail and F3 (+subject) pullback terms. "
                "Any life-planning/receipt term excluded in F1 must be pulled back symmetrically in F3."
            )
    elif bool(f1_matches) != bool(f3_matches):
        errors.append("[Partition Symmetry Error] Missing symmetric subject clause between F1 and F3.")

    return errors, warnings

def main():
    parser = argparse.ArgumentParser(description="Lint Gmail Terraform filter definitions against Gmail engine quirks.")
    parser.add_argument("--path", default=None, help="Path to filters.auto.tfvars.json (auto-detected if omitted)")
    args = parser.parse_args()

    tfvars_path = args.path or find_default_tfvars()
    if not os.path.exists(tfvars_path):
        print(f"Error: Target tfvars file not found: {tfvars_path}", file=sys.stderr)
        print("Please provide --path <path/to/filters.auto.tfvars.json>", file=sys.stderr)
        sys.exit(2)

    with open(tfvars_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"Error parsing JSON from {tfvars_path}: {e}", file=sys.stderr)
            sys.exit(2)

    filters = data.get("filters", [])
    filters_dict = {flt.get("key", f"filter_{i}"): flt for i, flt in enumerate(filters)}

    total_errors = []
    total_warnings = []

    for flt in filters:
        key = flt.get("key", "unknown")
        crit = flt.get("criteria", {})
        q = crit.get("query", "")
        errs, warns = lint_filter_query(key, q, crit)
        total_errors.extend(errs)
        total_warnings.extend(warns)

    sym_errs, sym_warns = check_partition_symmetry(filters_dict)
    total_errors.extend(sym_errs)
    total_warnings.extend(sym_warns)

    if total_warnings:
        print("WARNINGS:")
        for w in total_warnings:
            print(f"  - {w}")

    if total_errors:
        print("\nLINT FAILURES DETECTED:")
        for e in total_errors:
            print(f"  - {e}")
        print("\nDo not apply this configuration to Terraform until resolved.")
        sys.exit(1)

    print(f"PASSED: All {len(filters)} filters in {os.path.basename(tfvars_path)} satisfy Gmail delivery-engine compiler invariants.")
    sys.exit(0)

if __name__ == "__main__":
    main()
