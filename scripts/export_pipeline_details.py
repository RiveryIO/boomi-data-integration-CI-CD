#!/usr/bin/env python3
"""
Export a river's details to JSON and generate a YAML pipeline config
that can be used for updates.

Usage:
  TOKEN/ACCOUNT_ID/ENV_ID must be set as env vars (GitHub Secrets).
  python scripts/export_pipeline_details.py \
    --river-id <cross_id> \
    --json-out exports/pipeline-details.json \
    --yaml-out configs/pipelines/exported/pipeline.yml
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
import yaml

API_BASE = "https://api.rivery.io"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"ERROR: {name} env var required")
    return value


def bearer() -> str:
    token = os.environ.get("TOKEN")
    if not token:
        sys.exit("ERROR: TOKEN env var required")
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


def rivery_get(url: str, auth: str) -> dict:
    resp = requests.get(url, headers={"Authorization": auth, "Accept": "application/json"}, timeout=60)
    try:
        data = resp.json()
    except Exception:
        print(f"HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        resp.raise_for_status()
    if resp.status_code != 200:
        print(json.dumps(data, indent=2)[:2000], file=sys.stderr)
        resp.raise_for_status()
    return data


def dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def dump_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)


def build_pipeline_yaml(river: dict) -> dict:
    metadata = river.get("metadata", {}) or {}
    props = river.get("properties", {}) or {}
    source = props.get("source", {}) or {}
    target = props.get("target", {}) or {}
    settings = river.get("settings", {}) or {}
    notifications = settings.get("notification", {}) or {}
    schedulers = river.get("schedulers") or []

    cfg: dict = {
        "name": river.get("name"),
    }

    if metadata.get("description") is not None:
        cfg["description"] = metadata.get("description")
    if metadata.get("river_status") is not None:
        cfg["river_status"] = metadata.get("river_status")

    source_cfg = {}
    if source.get("name"):
        source_cfg["type"] = source.get("name")
    if source.get("connection_id"):
        source_cfg["connection_id"] = source.get("connection_id")
    if source.get("connection_name"):
        source_cfg["connection_name"] = source.get("connection_name")
    if source_cfg:
        cfg["source"] = source_cfg

    run_type = source.get("run_type") or (props.get("source") or {}).get("run_type")
    if run_type:
        cfg["run_type"] = run_type

    extract_method = (source.get("additional_settings") or {}).get("extract_method")
    if extract_method is not None:
        cfg["additional_settings"] = {"extract_method": extract_method}

    if source.get("cdc_settings") is not None:
        cfg["cdc_settings"] = source.get("cdc_settings") or {}

    target_cfg = {}
    if target.get("name"):
        target_cfg["type"] = target.get("name")
    if target.get("connection_id"):
        target_cfg["connection_id"] = target.get("connection_id")
    if target.get("connection_name"):
        target_cfg["connection_name"] = target.get("connection_name")
    for key in (
        "database_name",
        "schema_name",
        "target_prefix",
        "loading_method",
        "merge_method",
        "is_ordered_merge_key",
        "order_expression",
    ):
        if target.get(key) is not None:
            target_cfg[key] = target.get(key)
    if target_cfg:
        cfg["target"] = target_cfg

    if props.get("schemas") is not None:
        cfg["schemas"] = props.get("schemas") or []

    if notifications:
        def enabled(val, default=None):
            return default if val is None else bool(val)

        cfg["notifications"] = {
            "email": (notifications.get("warning") or {}).get("email")
            or (notifications.get("failure") or {}).get("email")
            or (notifications.get("run_threshold") or {}).get("email"),
        }
        if "warning" in notifications:
            cfg["notifications"]["warning_enabled"] = enabled(notifications["warning"].get("is_enabled"), True)
        if "failure" in notifications:
            cfg["notifications"]["failure_enabled"] = enabled(notifications["failure"].get("is_enabled"), True)
        if "run_threshold" in notifications:
            cfg["notifications"]["threshold_enabled"] = enabled(
                notifications["run_threshold"].get("is_enabled"), True
            )
            cfg["notifications"]["run_threshold_seconds"] = notifications["run_threshold"].get(
                "execution_time_limit_seconds", 43200
            )

    if schedulers:
        first = schedulers[0]
        cfg["schedule"] = {}
        if first.get("cron_expression") is not None:
            cfg["schedule"]["cron"] = first.get("cron_expression")
        if first.get("is_enabled") is not None:
            cfg["schedule"]["enabled"] = bool(first.get("is_enabled"))

    cfg["advanced"] = {
        "cross_id": river.get("cross_id"),
        "actual_name": river.get("name"),
    }

    return cfg


def main() -> int:
    parser = argparse.ArgumentParser(description="Export river details to JSON and YAML.")
    parser.add_argument("--river-id", required=True, help="river cross_id to export")
    parser.add_argument("--json-out", required=True, help="path for raw JSON output")
    parser.add_argument("--yaml-out", required=True, help="path for YAML pipeline config")
    args = parser.parse_args()

    account_id = require_env("ACCOUNT_ID")
    env_id = os.environ.get("ENV_ID") or require_env("ENVIRONMENT_ID")
    auth = bearer()

    url = f"{API_BASE}/v1/accounts/{account_id}/environments/{env_id}/rivers/{args.river_id}"
    river = rivery_get(url, auth)

    json_path = Path(args.json_out)
    yaml_path = Path(args.yaml_out)

    dump_json(json_path, river)
    pipeline_cfg = build_pipeline_yaml(river)
    dump_yaml(yaml_path, pipeline_cfg)

    print(
        json.dumps(
            {
                "status": "ok",
                "river_cross_id": river.get("cross_id"),
                "json_out": str(json_path),
                "yaml_out": str(yaml_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
