#!/usr/bin/env python3
import os, sys, json, datetime, argparse, requests, yaml

API_BASE = "https://api.rivery.io"

def require_env(name: str) -> str:
    """Read a required environment variable or exit with a clear error."""
    val = os.environ.get(name)
    if not val:
        sys.exit(f"ERROR: {name} env var required")
    return val

def bearer(tok: str) -> str:
    """Return a properly formatted Bearer token."""
    return tok if tok.lower().startswith("bearer ") else f"Bearer {tok}"

def load_yaml(path: str) -> dict:
    """Load and parse a YAML file safely."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def main():
    ap = argparse.ArgumentParser(description="Create river from pipeline YAML (IDs embedded)")
    ap.add_argument("--pipeline-config", required=True)
    args = ap.parse_args()

    account_id = require_env("ACCOUNT_ID")
    env_id     = os.getenv("ENV_ID") or require_env("ENVIRONMENT_ID")
    auth       = bearer(require_env("TOKEN"))

    pipe = load_yaml(args.pipeline_config)

    # Basic validation
    for k in ("source","target","run_type"):
        if k not in pipe: sys.exit(f"ERROR: pipeline YAML missing '{k}'")
    for k in ("type","connection_id"):
        if k not in pipe["source"]: sys.exit("ERROR: source requires type & connection_id")
    for k in ("type","connection_id","database_name","schema_name"):
        if k not in pipe["target"]: sys.exit("ERROR: target requires type, connection_id, database_name, schema_name")

    river_name = f"{pipe['name']}_{datetime.datetime.utcnow():%Y%m%d_%H%M%S}"
    notif = pipe.get("notifications", {}) or {}
    email = notif.get("email","")

    payload = {
      "name": river_name,
      "kind": "main_river",
      "type": "source_to_target",
      "metadata": {
        "description": pipe.get("description",""),
        "river_status": pipe.get("river_status","disabled"),
      },
      "settings": {
        "run_timeout_seconds": 43200,
        "notification": {
          "warning": {"email": email, "is_enabled": bool(notif.get("warning_enabled",True)), "execution_time_limit_seconds": None},
          "failure": {"email": email, "is_enabled": bool(notif.get("failure_enabled",True)), "execution_time_limit_seconds": None},
          "run_threshold": {"email": email, "is_enabled": bool(notif.get("threshold_enabled",True)), "execution_time_limit_seconds": notif.get("run_threshold_seconds",43200)}
        }
      },
      "properties": {
        "properties_type": "source_to_target",
        "source": {
          "name": pipe["source"]["type"],
          "connection_id": pipe["source"]["connection_id"],
          "run_type": pipe.get("run_type","multi_tables"),
          **({"cdc_settings": pipe["cdc_settings"]} if pipe.get("cdc_settings") else {}),
          "additional_settings": pipe.get("additional_settings", {})
        },
        "target": {
          "name": pipe["target"]["type"],
          "connection_id": pipe["target"]["connection_id"],
          "database_name": pipe["target"]["database_name"],
          "schema_name":   pipe["target"]["schema_name"],
          "table_prefix":  pipe["target"].get("table_prefix",""),
          "loading_method":pipe["target"].get("loading_method","merge"),
          "merge_method":  pipe["target"].get("merge_method","merge"),
          "is_ordered_merge_key": pipe["target"].get("is_ordered_merge_key", False),
          "order_expression":     pipe["target"].get("order_expression")
        },
        "schemas": pipe.get("schemas", [])
      },
      "schedulers": [{
        "cron_expression": pipe.get("schedule",{}).get("cron","0 2 * * *"),
        "is_enabled": bool(pipe.get("schedule",{}).get("enabled", False))
      }]
    }

    url = f"{API_BASE}/v1/accounts/{account_id}/environments/{env_id}/rivers"
    resp = requests.post(url, headers={"Authorization":auth,"Content-Type":"application/json"}, json=payload, timeout=60)

    try: data = resp.json()
    except Exception: data = {"raw": resp.text}

    print(resp.status_code)
    print(json.dumps(data, indent=2))

    rid = data.get("river_cross_id") or data.get("cross_id")
    print(json.dumps({"river_cross_id": rid}))
    sys.exit(0 if resp.ok else 1)

if __name__ == "__main__":
    main()