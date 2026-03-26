# Boomi Data Integration CI/CD Template

A CI-agnostic automation framework for Boomi Data Integration pipelines. YAML
files are the single source of truth; Python scripts call the Boomi Data
Integration API and can be invoked from **any CI platform** (Bitbucket
Pipelines, GitHub Actions, GitLab CI, Jenkins, …) or run **locally** from a
terminal.

## Repository structure

```
.
├─ scripts/                          # CI-agnostic Python scripts (the core)
│  ├─ create_river.py
│  ├─ update_river.py
│  ├─ activate_river.py
│  ├─ run_river.py
│  ├─ disable_river.py
│  ├─ export_pipeline_details.py
│  ├─ get_connections.py
│  ├─ get_schemas_tables.py
│  └─ stamp_ci_metadata.py
├─ configs/
│  ├─ pipelines/
│  │  └─ TEMPLATE.yml               # Copy this to define a new pipeline
│  ├─ sources/                      # Sample source config snippets
│  └─ targets/                      # Sample target config snippets
├─ bitbucket-pipelines.yml          # Ready-to-use Bitbucket Pipelines config
├─ examples/
│  └─ github-actions/               # Optional GitHub Actions workflow examples
│     ├─ README.md
│     ├─ river-create.yml
│     ├─ river-update.yml
│     ├─ river-activate.yml
│     ├─ river-run.yml
│     ├─ river-disable.yml
│     ├─ export-river.yml
│     ├─ export-connections.yml
│     └─ export-schemas-tables.yml
├─ requirements.txt                 # Pinned Python dependencies
├─ LICENSE
└─ SECURITY.md
```

Generated output directories (`connections/`, `exports/`) are gitignored.

## Required environment variables

Every script reads three variables at runtime. Set them in your CI secrets
manager or in a local `.env` file (never commit `.env`).

| Variable | Description |
|----------|-------------|
| `ACCOUNT_ID` | Boomi Data Integration account ID |
| `ENV_ID` | Target environment ID |
| `TOKEN` | API token (raw value or `Bearer <value>`) |

Use separate tokens per environment. For multi-environment repos, scope
variables to deployment environments or use a separate repo per environment.

### API base URL by region

| Region | Base URL |
|--------|----------|
| US | `https://api.rivery.io` |
| EU | `https://api.eu-west-1.rivery.io` |
| IL | `https://api.il-central-1.rivery.io` |
| AU | `https://api.ap-southeast-2.rivery.io` |

The scripts default to the US endpoint. Override by changing `API_BASE` at the
top of any script, or set a wrapper env var and patch the constant in your
deployment.

## Quick start — run locally

```bash
# 1. Install pinned dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Export credentials (or load from a .env file)
export ACCOUNT_ID=<your-account-id>
export ENV_ID=<your-environment-id>
export TOKEN=<your-api-token>

# 3. Discover what connections exist
python scripts/get_connections.py --out connections/connections.json --sanitize

# 4. Discover schemas and tables for a connection
python scripts/get_schemas_tables.py \
  --connection-id <connection-cross-id> \
  --out exports/schemas_tables.json

# 5. Create a new pipeline
cp configs/pipelines/TEMPLATE.yml configs/pipelines/my-team/my_pipeline.yml
# … edit the YAML …
python scripts/create_river.py \
  --pipeline-config configs/pipelines/my-team/my_pipeline.yml
# → prints river_cross_id; copy it into advanced.cross_id in the YAML

# 6. Update, activate, run, disable
python scripts/update_river.py   --pipeline-config configs/pipelines/my-team/my_pipeline.yml
python scripts/activate_river.py --pipeline-config configs/pipelines/my-team/my_pipeline.yml
python scripts/run_river.py      --pipeline-config configs/pipelines/my-team/my_pipeline.yml
python scripts/disable_river.py  --pipeline-config configs/pipelines/my-team/my_pipeline.yml

# Export a live river back to YAML (reverse-sync)
python scripts/export_pipeline_details.py \
  --river-id <cross-id> \
  --json-out exports/river.json \
  --yaml-out configs/pipelines/my-team/my_pipeline_exported.yml
```

## Running in CI

The scripts are plain Python with no CI-specific logic. Pass the three required
env vars through your CI secrets mechanism and invoke the scripts exactly as
shown above.

### Bitbucket Pipelines

`bitbucket-pipelines.yml` at the root of this repo defines all eight operations
as **custom manual pipelines**. Run them from:

> **Pipelines → Run pipeline → select branch → select pipeline**

Set the three required variables under **Repository settings → Repository
variables** (mark `TOKEN` as Secured).

### GitHub Actions (optional)

For teams using GitHub Actions, reference implementations are in
`examples/github-actions/`. Copy the workflows you need into `.github/workflows/`
and configure the three required repository secrets. See
[`examples/github-actions/README.md`](examples/github-actions/README.md) for
details.

### Other CI systems (GitLab CI, Jenkins, etc.)

Define a job that:
1. Checks out the repo.
2. Runs `pip install -r requirements.txt`.
3. Sets `ACCOUNT_ID`, `ENV_ID`, and `TOKEN` from the CI secrets store.
4. Calls the relevant `python scripts/<script>.py` command.

## Pipeline YAML format

Start from `configs/pipelines/TEMPLATE.yml`. Key fields:

```yaml
name: my_pipeline_slug          # used to name the river on creation
description: "Human description"
river_status: disabled          # disabled | active

source:
  type: mysql                   # connector type name
  connection_id: <cross-id>     # from your connection inventory

target:
  type: snowflake
  connection_id: <cross-id>
  database_name: MY_DB
  schema_name: MY_SCHEMA
  loading_method: merge
  merge_method: merge

run_type: multi_tables          # multi_tables | predefined_tables | cdc

schemas:
  - name: public
    tables: [orders, customers, products]

schedule:
  cron: "0 2 * * *"
  enabled: false

notifications:
  email: data-team@your-org.example.com
  warning_enabled: true
  failure_enabled: true

advanced:
  cross_id: ""   # populated by create_river.py; required for all subsequent ops
```

After running `create_river.py`, copy the printed `river_cross_id` into
`advanced.cross_id` and commit the YAML. All other scripts read the `cross_id`
from the YAML — no CLI argument needed.

## Stamp CI metadata (optional)

`scripts/stamp_ci_metadata.py` writes run context (timestamp, actor, git SHA,
CI system) into `advanced.ci_metadata` in the pipeline YAML. It is called
automatically by the `river-update` pipeline step. Run it standalone:

```bash
PIPELINE_CONFIG=configs/pipelines/my-team/my_pipeline.yml \
PIPELINE_ACTION=update \
CHANGE_NOTE="add orders table" \
python scripts/stamp_ci_metadata.py
```

## Sensitive data in CI logs

All scripts apply a `_redact()` filter before printing API response JSON to
stdout. Keys matching common secret patterns (`password`, `token`,
`client_secret`, `credentials`, `key`, `private_key`, etc.) are stripped from
logged output. The `get_connections.py` script additionally supports a
`--sanitize` flag that applies the same filter to the exported JSON file.

## Operating model

This template assumes that Boomi environments and connections already exist.
YAML files reference connections by ID. Connection provisioning, credential
rotation, and environment access controls remain outside this repository.

## Standard operating procedure

**Create a new pipeline:**
1. Copy `configs/pipelines/TEMPLATE.yml` to `configs/pipelines/<team>/<name>.yml`.
2. Fill in `source`, `target`, `run_type`, and any schema selections.
3. Open a PR and get it reviewed.
4. Run `create_river.py` (locally or via CI pipeline).
5. Copy the returned `cross_id` into `advanced.cross_id` and commit.

**Update an existing pipeline:**
1. Edit the YAML (schemas, schedule, notifications, target settings, etc.).
2. Open a PR, review, and merge.
3. Run `update_river.py`. The YAML is the sole source of truth; the script
   reads `advanced.cross_id` and PUTs the full desired state to the API.

**Operate a pipeline:**
Run `activate_river.py`, `run_river.py`, or `disable_river.py` as needed.

## Governance notes

- All API calls are authenticated with a short-lived token scoped to one
  environment. Rotate tokens regularly.
- Require PR approvals on `configs/pipelines/` before merging.
- Use the git history of YAML files as your change audit log.
- The `connections/` and `exports/` output directories are gitignored by
  default; commit them explicitly only if your governance process requires it.

## Setup checklist

- [ ] Replace `@your-org/data-platform-team` in `.github/CODEOWNERS`.
- [ ] Set `ACCOUNT_ID`, `ENV_ID`, and `TOKEN` in your CI secrets manager.
- [ ] Verify the API base URL matches your Boomi region.
- [ ] Copy `TEMPLATE.yml` and fill in real connection IDs.
- [ ] Run `create_river.py` and stamp `cross_id` back into the YAML.
- [ ] Update `pipelines-bot@your-org.example.com` in `bitbucket-pipelines.yml`
  to a real committer email if your repo requires signed commits.

## References

- Boomi Data Integration API: <https://developer.boomi.com/docs/api/dataintegration/Rivers>
- MIT License: see [`LICENSE`](LICENSE)
- Security policy: see [`SECURITY.md`](SECURITY.md)
