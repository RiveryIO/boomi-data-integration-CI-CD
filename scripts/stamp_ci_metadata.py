#!/usr/bin/env python3
"""
Stamp CI run metadata into the pipeline YAML's advanced.ci_metadata block.

Reads from env vars (set by the calling CI job):
  PIPELINE_CONFIG   – path to the pipeline YAML file (required)
  PIPELINE_ACTION   – e.g. "create" | "update" | "activate" (required)
  CHANGE_NOTE       – free-text description of the change (optional)

CI context env vars (populated automatically on GitHub Actions, Bitbucket, GitLab, etc.):
  CI_COMMIT_SHA / GITHUB_SHA / BITBUCKET_COMMIT
  CI_ACTOR        / GITHUB_ACTOR / BITBUCKET_STEP_TRIGGERER_UUID
  CI_RUN_ID       / GITHUB_RUN_ID / BITBUCKET_BUILD_NUMBER

The script writes back to the YAML file in-place; the caller is responsible
for committing the change if desired.

Usage (standalone):
  PIPELINE_CONFIG=configs/pipelines/team-a/demo.yml \
  PIPELINE_ACTION=update \
  CHANGE_NOTE="schema refresh" \
  python scripts/stamp_ci_metadata.py
"""

import os
import sys
import datetime
from pathlib import Path

import yaml


def _get_env(*names: str, default: str = "") -> str:
    for name in names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return default


def main() -> int:
    pipeline_config = os.environ.get("PIPELINE_CONFIG", "").strip()
    if not pipeline_config:
        sys.exit("ERROR: PIPELINE_CONFIG env var is required.")

    action = os.environ.get("PIPELINE_ACTION", "unknown").strip()
    note   = os.environ.get("CHANGE_NOTE", "").strip()

    # Resolve CI context – check GitHub Actions, Bitbucket, GitLab, and generic vars
    sha   = _get_env("CI_COMMIT_SHA", "GITHUB_SHA", "BITBUCKET_COMMIT", default="unknown")
    actor = _get_env("CI_ACTOR", "GITHUB_ACTOR", "BITBUCKET_STEP_TRIGGERER_UUID", default="unknown")
    run_id = _get_env("CI_RUN_ID", "GITHUB_RUN_ID", "BITBUCKET_BUILD_NUMBER", default="unknown")
    ci_server = _get_env("GITHUB_ACTIONS", default="")
    if ci_server == "true":
        ci_server = "github-actions"
    else:
        ci_server = _get_env("CI_SERVER_NAME", "BITBUCKET_CI", default="ci")
        if ci_server == "1":
            ci_server = "bitbucket-pipelines"

    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    path = Path(pipeline_config)
    if not path.is_file():
        sys.exit(f"ERROR: pipeline config not found: {pipeline_config}")

    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Write metadata into advanced.ci_metadata
    if "advanced" not in cfg or not isinstance(cfg.get("advanced"), dict):
        cfg["advanced"] = {}

    cfg["advanced"]["ci_metadata"] = {
        "last_action":    action,
        "stamped_at_utc": timestamp,
        "ci_actor":       actor,
        "ci_run_id":      run_id,
        "ci_sha":         sha[:12] if sha != "unknown" else sha,
        "ci_server":      ci_server,
        **({"change_note": note} if note else {}),
    }

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    print(f"Stamped ci_metadata ({action}) into {pipeline_config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
