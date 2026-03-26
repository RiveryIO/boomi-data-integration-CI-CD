#!/usr/bin/env python3
"""
Export Boomi Data Integration (Rivery) connections as JSON.

Reads env:
  ACCOUNT_ID          (required)
  ENV_ID or ENVIRONMENT_ID (required)
  TOKEN               (required; raw token or 'Bearer ...')

Usage examples:
  # Print to stdout (pretty JSON)
  python get_connections.py

  # Write to a file (repo inventory pattern)
  python get_connections.py --out inventory/connections.dev.json

  # Slow down requests if you hit rate limits (e.g., 0.8 rps)
  python get_connections.py --rps 0.8

  # Keep only a safe subset of fields (default behavior)
  python get_connections.py --out inventory/connections.dev.json

  # Or export full items but sanitize common secret keys
  python get_connections.py --out inventory/connections.dev.json --all --sanitize
"""

import os
import sys
import json
import time
import argparse
from typing import Dict, Any, List
import requests

API_BASE = "https://api.rivery.io"

SAFE_FIELDS_DEFAULT = [
    "account_id",
    "environment_id",
    "cross_id",
    "_id",
    "connection_name",
    "connection_type",
    "connection_type_id",
    "is_test_connection",
    "connection_update_by",
    "connection_update_time",
]

SUSPECT_KEYS = {
    # keys to remove when --sanitize is on
    "password", "token", "access_token", "refresh_token",
    "client_secret", "secret", "credentials", "key", "private_key",
    "authorization", "auth", "headers", "connection_string",
}


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"ERROR: missing env var {name}")
    return val


def bearer() -> str:
    tok = require_env("TOKEN")
    return tok if tok.lower().startswith("bearer ") else f"Bearer {tok}"


def sanitize(obj: Any) -> Any:
    """Recursively remove common secret-looking keys from dicts/lists."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in SUSPECT_KEYS:
                continue
            out[k] = sanitize(v)
        return out
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    return obj


def select_fields(item: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    return {k: item.get(k) for k in fields}


def fetch_connections(account_id: str, env_id: str, auth: str, items_per_page: int, rps: float) -> Dict[str, Any]:
    url = f"{API_BASE}/v1/accounts/{account_id}/environments/{env_id}/connections"
    params = {"items_per_page": items_per_page}
    headers = {"Authorization": auth, "Accept": "application/json"}

    items: List[Dict[str, Any]] = []
    page_count = 0
    start = time.time()

    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        # After first request, params are only needed if the next_page is not absolute; most APIs return full URLs
        params = {}

        if resp.status_code != 200:
            # Surface meaningful error
            try:
                err = resp.json()
            except Exception:
                err = resp.text
            raise RuntimeError(f"HTTP {resp.status_code}: {err}")

        data = resp.json()
        if not isinstance(data, dict) or "items" not in data:
            raise RuntimeError(f"Unexpected response shape: {str(data)[:500]}")

        batch = data.get("items", [])
        items.extend(batch)
        page_count += 1

        next_page = data.get("next_page")
        if not next_page:
            break

        # Respect RPS
        if rps and rps > 0:
            time.sleep(max(0.0, 1.0 / rps))

        # The API commonly returns a full URL in next_page; use it as-is
        url = next_page

    total_seconds = max(0.001, time.time() - start)
    return {
        "count": len(items),
        "pages": page_count,
        "elapsed_seconds": round(total_seconds, 3),
        "items": items,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Export connections inventory as JSON")
    ap.add_argument("--out", help="Write JSON to this path (default: stdout)")
    ap.add_argument("--items-per-page", type=int, default=500, help="Items per page (API max typically 500)")
    ap.add_argument("--rps", type=float, default=1.0, help="Requests per second (lower to avoid 429s; e.g., 0.8)")
    ap.add_argument("--all", action="store_true", help="Export full item objects (not just safe fields)")
    ap.add_argument(
        "--fields",
        help=f"Comma-separated field list (default: {','.join(SAFE_FIELDS_DEFAULT)})",
    )
    ap.add_argument("--sanitize", action="store_true", help="Remove common secret-looking keys from output")
    args = ap.parse_args()

    account_id = require_env("ACCOUNT_ID")
    env_id = os.environ.get("ENV_ID") or require_env("ENVIRONMENT_ID")
    auth = bearer()

    try:
        result = fetch_connections(account_id, env_id, auth, args.items_per_page, args.rps)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    items = result["items"]

    # Choose output shape
    if args.all:
        out_items = items
    else:
        fields = [f.strip() for f in (args.fields.split(",") if args.fields else SAFE_FIELDS_DEFAULT)]
        out_items = [select_fields(it, fields) for it in items]

    if args.sanitize:
        out_items = sanitize(out_items)

    payload = {
        "__generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "account_id": account_id,
        "environment_id": env_id,
        "count": len(out_items),
        "items": out_items,
    }

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {len(out_items)} connections to {args.out}")
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())