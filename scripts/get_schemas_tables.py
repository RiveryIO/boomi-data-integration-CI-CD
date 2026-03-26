#!/usr/bin/env python3
"""
Export schemas and tables for a given connection.

Reads env:
  ACCOUNT_ID          (required)
  ENV_ID or ENVIRONMENT_ID (required)
  TOKEN               (required; raw token or 'Bearer ...')

Usage examples:
  python scripts/get_schemas_tables.py --connection-id <id>
  python scripts/get_schemas_tables.py --connection-id <id> --out exports/schemas_tables.json
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

API_BASE = "https://api.rivery.io"


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"ERROR: missing env var {name}")
    return val


def bearer() -> str:
    tok = require_env("TOKEN")
    return tok if tok.lower().startswith("bearer ") else f"Bearer {tok}"


def extract_schema_name(item: Dict[str, Any]) -> Optional[str]:
    for key in ("schema_name", "name", "id"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def extract_table_name(item: Dict[str, Any]) -> Optional[str]:
    for key in ("table_name", "name", "id"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def fetch_paginated(url: str, headers: Dict[str, str], params: Dict[str, Any], rps: float) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        params = {}

        if resp.status_code != 200:
            try:
                err = resp.json()
            except Exception:
                err = resp.text
            raise RuntimeError(f"HTTP {resp.status_code}: {err}")

        data = resp.json()
        if not isinstance(data, dict) or "items" not in data:
            raise RuntimeError(f"Unexpected response shape: {str(data)[:500]}")

        items.extend(data.get("items", []))
        next_page = data.get("next_page")
        if not next_page:
            break

        if rps and rps > 0:
            time.sleep(max(0.0, 1.0 / rps))

        url = next_page

    return items


def fetch_schemas(account_id: str, env_id: str, connection_id: str, auth: str, items_per_page: int, rps: float) -> List[Dict[str, Any]]:
    url = f"{API_BASE}/v1/accounts/{account_id}/environments/{env_id}/connections/{connection_id}/schemas"
    headers = {"Authorization": auth, "Accept": "application/json"}
    params = {"items_per_page": items_per_page}
    return fetch_paginated(url, headers, params, rps)


def fetch_tables(
    account_id: str,
    env_id: str,
    connection_id: str,
    schema_name: str,
    auth: str,
    items_per_page: int,
    rps: float,
) -> List[Dict[str, Any]]:
    url = f"{API_BASE}/v1/accounts/{account_id}/environments/{env_id}/connections/{connection_id}/tables"
    headers = {"Authorization": auth, "Accept": "application/json"}
    params = {"schema_name": schema_name, "items_per_page": items_per_page}
    return fetch_paginated(url, headers, params, rps)


def main() -> int:
    ap = argparse.ArgumentParser(description="Export schemas and tables for a connection")
    ap.add_argument("--connection-id", required=True, help="Connection cross_id")
    ap.add_argument("--out", help="Write JSON to this path (default: stdout)")
    ap.add_argument("--schemas-items-per-page", type=int, default=500, help="Items per page for schemas")
    ap.add_argument("--tables-items-per-page", type=int, default=100, help="Items per page for tables")
    ap.add_argument("--rps", type=float, default=1.0, help="Requests per second (lower to avoid 429s; e.g., 0.8)")
    args = ap.parse_args()

    account_id = require_env("ACCOUNT_ID")
    env_id = os.environ.get("ENV_ID") or require_env("ENVIRONMENT_ID")
    auth = bearer()

    start = time.time()
    try:
        schema_items = fetch_schemas(
            account_id, env_id, args.connection_id, auth, args.schemas_items_per_page, args.rps
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    schemas_output: List[Dict[str, Any]] = []
    for schema in schema_items:
        schema_name = extract_schema_name(schema)
        if not schema_name:
            continue
        try:
            table_items = fetch_tables(
                account_id,
                env_id,
                args.connection_id,
                schema_name,
                auth,
                args.tables_items_per_page,
                args.rps,
            )
        except Exception as e:
            print(f"ERROR: failed to fetch tables for schema {schema_name}: {e}", file=sys.stderr)
            return 1

        table_names: List[str] = []
        for table in table_items:
            table_name = extract_table_name(table)
            if table_name:
                table_names.append(table_name)

        schemas_output.append({
            "name": schema_name,
            "tables": table_names,
            "table_count": len(table_names),
        })

    payload = {
        "__generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "account_id": account_id,
        "environment_id": env_id,
        "connection_id": args.connection_id,
        "schema_count": len(schemas_output),
        "elapsed_seconds": round(max(0.001, time.time() - start), 3),
        "schemas": schemas_output,
    }

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {len(schemas_output)} schemas to {args.out}")
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
