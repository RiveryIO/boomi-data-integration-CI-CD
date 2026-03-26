#!/usr/bin/env python3
"""
Update a Boomi Data Integration (Rivery) river using a YAML pipeline config.

Rules:
- The pipeline YAML is the single source of truth for updates.
- The river id (cross_id) MUST exist in the YAML (top-level 'cross_id' or 'advanced.cross_id').
- Schemas are taken ONLY from the YAML (no CLI fallbacks).
"""

import os, sys, json, argparse
from typing import List, Dict, Any
import requests
import yaml

API_BASE = "https://api.rivery.io"

# Keys that should never appear in CI logs
_LOG_REDACT = frozenset({
    "password", "token", "access_token", "refresh_token",
    "client_secret", "secret", "credentials", "key", "private_key",
    "authorization", "auth", "headers", "connection_string",
})

def _redact(obj):
    """Recursively drop known-secret keys before printing to CI logs."""
    if isinstance(obj, dict):
        return {k: _redact(v) for k, v in obj.items() if k.lower() not in _LOG_REDACT}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj

# ---------- helpers ----------
def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"ERROR: {name} env var is required.")
    return v

def bearer() -> str:
    tok = os.environ.get("TOKEN")
    if not tok:
        sys.exit("ERROR: TOKEN env var is required (GitHub Secret).")
    return tok if tok.lower().startswith("bearer ") else f"Bearer {tok}"

def rivery_get(url: str, auth: str) -> dict:
    r = requests.get(url, headers={"Authorization": auth, "Accept": "application/json"}, timeout=60)
    try:
        data = r.json()
    except Exception:
        print(f"HTTP {r.status_code}: {r.text[:500]}", file=sys.stderr)
        r.raise_for_status()
    if r.status_code != 200:
        print(json.dumps(data, indent=2)[:2000], file=sys.stderr)
        r.raise_for_status()
    return data

def rivery_put(url: str, auth: str, payload: dict) -> requests.Response:
    return requests.put(
        url,
        headers={"Authorization": auth, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def shallow_clean(d):
    if isinstance(d, dict):
        return {k: shallow_clean(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [shallow_clean(x) for x in d]
    return d

def build_tables_block_from_list(tables: List[str]) -> List[Dict[str, Any]]:
    """
    ["t1","t2"] -> [
      {"run_type_and_datasource":"multi_tables","details":{"name":"t1","is_selected":True}},
      {"run_type_and_datasource":"multi_tables","details":{"name":"t2","is_selected":True}}
    ]
    """
    out: List[Dict[str, Any]] = []
    for t in (tables or []):
        t = str(t).strip()
        if not t:
            continue
        out.append({
            "run_type_and_datasource": "multi_tables",
            "details": {"name": t, "is_selected": True}
        })
    return out

def normalize_schemas_from_yaml(cfg: Dict[str, Any]) -> (List[Dict[str, Any]], bool):
    """
    Expect YAML like:
      schemas:
        - name: my_schema
          tables: [table1, table2]
      # or tables already in the river shape (objects with 'details.name')

    Returns (schemas_list, provided_flag)
    """
    if "schemas" not in cfg:
        return [], False

    schemas_yaml = cfg.get("schemas")
    if schemas_yaml is None:
        # user explicitly set null -> treat as empty
        return [], True

    if not isinstance(schemas_yaml, list):
        sys.exit("ERROR: 'schemas' must be a list in the pipeline YAML.")

    normalized: List[Dict[str, Any]] = []
    for s in schemas_yaml:
        if not isinstance(s, dict):
            sys.exit("ERROR: each entry in 'schemas' must be an object with at least 'name' and 'tables'.")
        sname = s.get("name") or s.get("schema_name")
        if not sname:
            sys.exit("ERROR: schema entry missing 'name'.")
        tables = s.get("tables") or []
        if tables and isinstance(tables[0], str):
            tblock = build_tables_block_from_list(tables)
        else:
            # assume already river-shaped (validate a bit)
            tblock = []
            for t in (tables or []):
                if not isinstance(t, dict) or not (t.get("details") or {}).get("name"):
                    sys.exit("ERROR: schema.tables must be strings or objects with details.name.")
                tblock.append(t)
        normalized.append({"name": sname, "tables": tblock})

    return normalized, True

def validate_cross_id(cid: str) -> str:
    cid = (cid or "").strip().strip('"').strip("'")
    if len(cid) != 24 or any(c not in "0123456789abcdef" for c in cid.lower()):
        import re
        m = re.search(r"([0-9a-f]{24})", cid.lower())
        if not m:
            sys.exit("ERROR: pipeline config is missing a valid 24-hex 'cross_id'. Run the Create step first to stamp it.")
        cid = m.group(1)
    return cid

# ---------- main ----------
def main() -> int:
    p = argparse.ArgumentParser(description="Update river from pipeline YAML (YAML is the only source of truth).")
    p.add_argument("--account-id", default=os.environ.get("ACCOUNT_ID"))
    p.add_argument("--environment-id", default=os.environ.get("ENV_ID") or os.environ.get("ENVIRONMENT_ID"))
    p.add_argument("--pipeline-config", required=True, help="Path to pipeline YAML (must include cross_id)")
    p.add_argument("--dry-run", action="store_true", help="Show planned payload, no PUT")
    args = p.parse_args()

    account_id = args.account_id or require_env("ACCOUNT_ID")
    env_id     = args.environment_id or require_env("ENV_ID")
    auth       = bearer()

    # Load YAML (single source of truth)
    cfg = load_yaml(args.pipeline_config)

    # Enforce cross_id FROM YAML ONLY (top-level or advanced.cross_id)
    river_id = cfg.get("cross_id") or (cfg.get("advanced") or {}).get("cross_id")
    if not river_id:
        sys.exit("ERROR: pipeline config file does not have 'cross_id'. Run the Create step to stamp it, then retry Update.")
    river_id = validate_cross_id(river_id)

    base = f"{API_BASE}/v1/accounts/{account_id}/environments/{env_id}"
    river_url = f"{base}/rivers/{river_id}"

    # Pull current to preserve platform-managed values
    current  = rivery_get(river_url, auth)
    props    = current.get("properties", {}) or {}
    src_cur  = props.get("source", {}) or {}
    tgt_cur  = props.get("target", {}) or {}
    sched_cur= current.get("schedulers", []) or []
    settings = current.get("settings", {}) or {}

    # ---------- Build desired from YAML ----------
    # metadata / status / description
    desired_status = cfg.get("river_status", current.get("metadata", {}).get("river_status", "disabled"))
    description    = cfg.get("description", current.get("metadata", {}).get("description"))

    # source (prefer source.run_type; fallback to root run_type; fallback to current)
    src_cfg  = cfg.get("source", {}) or {}
    run_type = src_cfg.get("run_type", cfg.get("run_type", src_cur.get("run_type")))
    src_desired = {
        "name": src_cfg.get("type") or src_cur.get("name"),
        "connection_id": src_cfg.get("connection_id") or src_cur.get("connection_id"),
        "run_type": run_type,
    }
    # source additional settings (prefer source.additional_settings; then legacy root additional_settings)
    add_src = (src_cfg.get("additional_settings") or cfg.get("additional_settings") or {})
    if add_src:
        src_desired["additional_settings"] = {
            **(src_cur.get("additional_settings") or {}),
            **add_src
        }
    # cdc_settings only when provided AND using CDC
    cdc_cfg = src_cfg.get("cdc_settings", cfg.get("cdc_settings"))
    if run_type == "cdc" and cdc_cfg:
        src_desired["cdc_settings"] = cdc_cfg

    # target
    tgt_cfg = cfg.get("target", {}) or {}
    target_prefix = tgt_cfg.get("target_prefix", tgt_cfg.get("table_prefix"))
    tgt_desired = {
        "name": tgt_cfg.get("type") or tgt_cur.get("name"),
        "connection_id": tgt_cfg.get("connection_id") or tgt_cur.get("connection_id"),
        "database_name": tgt_cfg.get("database_name") or tgt_cur.get("database_name"),
        "schema_name":   tgt_cfg.get("schema_name")   or tgt_cur.get("schema_name"),
        "target_prefix": target_prefix if target_prefix is not None else tgt_cur.get("target_prefix"),
        "loading_method": tgt_cfg.get("loading_method") or tgt_cur.get("loading_method"),
        "merge_method":   tgt_cfg.get("merge_method")   or tgt_cur.get("merge_method"),
        "is_ordered_merge_key": tgt_cfg.get("is_ordered_merge_key", tgt_cur.get("is_ordered_merge_key")),
        "order_expression":     tgt_cfg.get("order_expression",     tgt_cur.get("order_expression")),
    }
    if "file_zone_settings" in tgt_cfg:
        tgt_desired["file_zone_settings"] = tgt_cfg.get("file_zone_settings") or {}
    if "file_path_destination" in tgt_cfg:
        tgt_desired["file_path_destination"] = tgt_cfg.get("file_path_destination")
    if "additional_settings" in tgt_cfg:
        tgt_desired["additional_settings"] = tgt_cfg.get("additional_settings") or {}

    # schemas (MUST come from YAML; if not provided, we leave existing unchanged)
    schemas_desired, schemas_provided = normalize_schemas_from_yaml(cfg)

    # schedulers: support either full list `schedulers:` or simple `schedule:`
    schedulers_out = sched_cur
    if isinstance(cfg.get("schedulers"), list):
        schedulers_out = cfg["schedulers"]
    elif "schedule" in cfg:
        sch = cfg.get("schedule") or {}
        schedulers_out = [{
            "cron_expression": sch.get("cron", "0 2 * * *"),
            "is_enabled": bool(sch.get("enabled", False))
        }]

    # notifications (optional)
    notif_cfg = cfg.get("notifications")
    if notif_cfg:
        settings["notification"] = {
            "warning": {
                "email": notif_cfg.get("email"),
                "is_enabled": True if notif_cfg.get("warning_enabled") is None else bool(notif_cfg.get("warning_enabled")),
                "execution_time_limit_seconds": None,
            },
            "failure": {
                "email": notif_cfg.get("email"),
                "is_enabled": True if notif_cfg.get("failure_enabled") is None else bool(notif_cfg.get("failure_enabled")),
                "execution_time_limit_seconds": None,
            },
            "run_threshold": {
                "email": notif_cfg.get("email"),
                "is_enabled": True if notif_cfg.get("threshold_enabled") is None else bool(notif_cfg.get("threshold_enabled")),
                "execution_time_limit_seconds": notif_cfg.get("run_threshold_seconds", 43200),
            },
        }

    # ---------- Final payload ----------
    payload = {
        "name": current.get("name"),
        "kind": current.get("kind", "main_river"),
        "type": current.get("type"),
        "metadata": {
            "description": description,
            "river_status": desired_status
        },
        "settings": settings,
        "properties": {
            "properties_type": "source_to_target",
            "source": {**src_cur, **shallow_clean(src_desired)},
            "target": {**tgt_cur, **shallow_clean(tgt_desired)},
            "schemas": schemas_desired if schemas_provided else (props.get("schemas") or []),
        },
        "schedulers": schedulers_out
    }

    # Dry-run?
    if args.dry_run:
        print("DRY-RUN payload (not sent):")
        print(json.dumps(payload, indent=2))
        print(json.dumps({"status": "dry-run", "river_cross_id": river_id}))
        return 0

    # PUT update
    url = f"{API_BASE}/v1/accounts/{account_id}/environments/{env_id}/rivers/{river_id}"
    resp = rivery_put(url, auth, payload)
    print("PUT status:", resp.status_code)
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    print(json.dumps(_redact(body), indent=2))
    if resp.status_code >= 300:
        sys.exit(1)

    print(json.dumps({
        "status": "ok",
        "river_cross_id": river_id,
        "schemas_applied": len(payload["properties"]["schemas"] or []),
        "river_status": desired_status
    }))
    return 0

if __name__ == "__main__":
    sys.exit(main())