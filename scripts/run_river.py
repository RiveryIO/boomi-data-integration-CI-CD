#!/usr/bin/env python3
import os, sys, json, argparse, requests, yaml, re

API_BASE = "https://api.rivery.io"

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

def load_yaml(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        sys.exit(f"ERROR: pipeline config not found: {path}")
    except Exception as e:
        sys.exit(f"ERROR: failed to read YAML '{path}': {e}")

def read_cross_id_from_yaml(pipeline_yaml: str) -> str:
    cfg = load_yaml(pipeline_yaml)
    rid = (cfg.get("cross_id") or (cfg.get("advanced") or {}).get("cross_id") or "").strip().strip('"').strip("'")
    if not re.fullmatch(r"[0-9a-fA-F]{24}", rid or ""):
        sys.exit("ERROR: No valid 24-hex cross_id in pipeline YAML. Run the 'create' action first so it stamps cross_id.")
    return rid

def post(url: str, auth: str) -> requests.Response:
    return requests.post(
        url,
        headers={"Authorization": auth, "Accept": "application/json", "Content-Type": "application/json"},
        json={},  # API expects an empty JSON body
        timeout=60,
    )

# ---------- main ----------
def main() -> int:
    p = argparse.ArgumentParser(description="Trigger a river run (reads cross_id from pipeline YAML).")
    p.add_argument("--pipeline-config", required=True, help="Path to pipeline YAML (must contain cross_id or advanced.cross_id)")
    # account/env are taken from env; flags allow local override if desired
    p.add_argument("--account-id", default=os.environ.get("ACCOUNT_ID"))
    p.add_argument("--environment-id", default=os.environ.get("ENV_ID") or os.environ.get("ENVIRONMENT_ID"))
    args = p.parse_args()

    account_id = args.account_id or require_env("ACCOUNT_ID")
    env_id     = args.environment_id or require_env("ENV_ID") or require_env("ENVIRONMENT_ID")
    auth       = bearer()

    river_id = read_cross_id_from_yaml(args.pipeline_config)
    url = f"{API_BASE}/v1/accounts/{account_id}/environments/{env_id}/rivers/{river_id}/run"

    resp = post(url, auth)

    print("HTTP", resp.status_code)
    try:
        data = resp.json()
    except Exception:
        print(resp.text)
        sys.exit(1)

    # Human-friendly
    print(json.dumps(data, indent=2))

    if resp.status_code not in (200, 201, 202):
        print("❌ Run request failed.", file=sys.stderr)
        print(json.dumps({"status": "error", "river_cross_id": river_id, "http": resp.status_code}))
        return 1

    # Summary
    runs = data.get("runs", []) or []
    run_group_id = data.get("run_group_id")
    print("\nSummary:")
    print(f"- run_group_id: {run_group_id}")
    if not runs:
        print("- No sub-runs returned (river may not have runnable subcomponents).")
    else:
        for i, r in enumerate(runs, 1):
            print(f"  {i}. sub_river_id={r.get('sub_river_id')} run_id={r.get('run_id')} "
                  f"status={r.get('status')} msg={r.get('message')}")

    # Machine-readable line for Actions
    out = {
        "status": "ok",
        "river_cross_id": river_id,
        "run_group_id": run_group_id,
        "sub_runs": [
            {
                "sub_river_id": r.get("sub_river_id"),
                "run_id": r.get("run_id"),
                "status": r.get("status"),
                "message": r.get("message"),
            } for r in runs
        ],
        "http": resp.status_code
    }
    print(json.dumps(out))
    return 0

if __name__ == "__main__":
    sys.exit(main())