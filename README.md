# Boomi Data Integration CI/CD Template

## Executive summary

This repository provides a GitHub Actions–driven CI/CD framework for Boomi Data Integration pipelines, using YAML as the source of truth. The template is designed to help teams standardize pipeline deployment, keep changes auditable, and operate safely across environments (Dev/Staging/Prod). It supports exporting, creating, updating, activating, running, and disabling rivers, plus exporting schema/table inventories for data discovery.

## Intended audience

- Data platform and analytics engineers
- CI/CD and DevOps teams
- Data operations teams responsible for pipeline governance

## Business value

- **Auditability:** YAML definitions in Git produce a traceable history.
- **Repeatability:** Consistent workflows for creating and updating rivers.
- **Operational safety:** Explicit activation, run, and disable steps.
- **Environment parity:** Multi-environment support through secrets.

## Solution overview

### What this template does

- Treats pipeline YAML as the **single source of truth**.
- Automates common river lifecycle actions via GitHub Actions.
- Provides helper scripts for local operations.

### What this template does not do

- Create or manage Boomi environments.
- Create or rotate connection credentials.

## Repository structure

```
.
├─ .github/
│  └─ workflows/
│     ├─ export-connections.yml    # Export Connection
│     ├─ export-river.yml          # Export River
│     ├─ river-create.yml          # Create River
│     ├─ river-activate.yml        # Activate River
│     ├─ river-run.yml             # Run River
│     ├─ river-disable.yml         # Disable River
│     ├─ river-update.yml          # Update River
│     └─ export-schemas-tables.yml # Export Schemas and Tables
├─ configs/
│  ├─ pipelines/
│  │  └─ TEMPLATE.yml              # Pre-create template
│  ├─ sources/                     # Sample source templates
│  └─ targets/                     # Sample target templates
├─ connections/                    # Generated connection inventories (gitignored)
├─ exports/                        # Generated exports (gitignored)
├─ scripts/
│  ├─ create_river.py              # Create a river from YAML
│  ├─ update_river.py              # Update a river from YAML
│  ├─ activate_river.py            # Activate a river (uses cross_id)
│  ├─ run_river.py                 # Run a river (uses cross_id)
│  ├─ disable_river.py             # Disable a river (uses cross_id)
│  ├─ export_pipeline_details.py   # Export river JSON + YAML
│  ├─ get_connections.py           # Export connections inventory
│  └─ get_schemas_tables.py        # Export schemas + tables for a connection
└─ README.md
```

## Prerequisites

### Required secrets

Create these GitHub Secrets in your repo (Settings ▸ Secrets and variables ▸ Actions):

- `ACCOUNT_ID`
- `ENV_ID`
- `TOKEN` (API token)

> **Note:** Each environment requires its own API token. Use environment-specific secrets or a separate repository per environment.

### API endpoints by region

- **US:** https://api.rivery.io
- **EU:** https://api.eu-west-1.rivery.io
- **IL:** https://api.il-central-1.rivery.io
- **AU:** https://api.ap-southeast-2.rivery.io

## Operating model

This template assumes environments and connections already exist in Boomi Data Integration. YAML files reference those connections by ID, and the workflows read metadata and deploy rivers accordingly. Connection provisioning, credential rotation, and access controls remain outside this repository.

## Pipeline YAML: single source of truth

- Start from `configs/pipelines/TEMPLATE.yml` when defining a new pipeline.
- Minimal required fields:
  - `name`
  - `source.connection_id`
  - `target.connection_id`
  - target database/schema settings

**After creation:** the Create workflow outputs a `cross_id`. Copy it into `advanced.cross_id` in your YAML to enable updates and runtime actions.

## Workflow catalog

1. **Export Connection**
   - Writes connection inventory to `connections/connections.dev.json` (default; gitignored).
2. **Export River**
   - Fetches a live river and generates JSON + YAML.
3. **Create River**
   - Creates a river from YAML and returns `cross_id`.
4. **Activate River**
   - Activates a river using the `advanced.cross_id`.
5. **Run River**
   - Executes a river on demand.
6. **Disable River**
   - Disables a river in the environment.
7. **Update River**
   - Pushes the full YAML state to the API.
8. **Export Schemas and Tables**
   - Creates schema/table inventory for a connection.

## Standard operating procedure

### Create a new pipeline

1. Copy the template:
   ```bash
   cp configs/pipelines/TEMPLATE.yml configs/pipelines/<team>/<your_pipeline>.yml
   ```
2. Populate required fields (name, source/target connection IDs, schema).
3. Commit and open a pull request.
4. Run **Create River** with `pipeline_config` pointing to the YAML.
5. Copy the output `cross_id` into `advanced.cross_id` in the YAML.

### Update an existing pipeline

1. Edit the YAML (schemas, schedules, notifications, etc.).
2. Commit and open a pull request.
3. Run **Update River** with the updated YAML.

### Operate a pipeline

- **Activate:** run **Activate River**.
- **Run:** run **Run River**.
- **Disable:** run **Disable River**.

## Local usage (optional)

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install requests pyyaml

# Required envs
export ACCOUNT_ID=...
export ENV_ID=...
export TOKEN=...

# Generated outputs land in gitignored folders (connections/, exports/).

# Export connections
python scripts/get_connections.py --out connections/connections.dev.json --rps 0.8

# Export schemas/tables
python scripts/get_schemas_tables.py \
  --connection-id <connection_id> \
  --out exports/schemas_tables.json \
  --rps 0.8

# Export a river
python scripts/export_pipeline_details.py \
  --river-id <cross_id> \
  --json-out exports/river.json \
  --yaml-out exports/river.yml

# Create / Update / Activate / Run / Disable
python scripts/create_river.py --pipeline-config configs/pipelines/<team>/<your_pipeline>.yml
python scripts/update_river.py --pipeline-config configs/pipelines/<team>/<your_pipeline>.yml
python scripts/activate_river.py --pipeline-config configs/pipelines/<team>/<your_pipeline>.yml
python scripts/run_river.py --pipeline-config configs/pipelines/<team>/<your_pipeline>.yml
python scripts/disable_river.py --pipeline-config configs/pipelines/<team>/<your_pipeline>.yml
```

## Governance and security considerations

- **Secrets management:** Store API tokens in GitHub Secrets only.
- **Environment isolation:** Use distinct tokens per environment.
- **Change control:** Require PR approvals for pipeline updates.
- **Auditability:** Use the repo history as the change log.

## Template checklist

- [ ] Replace placeholder team and pipeline names.
- [ ] Validate connection IDs exist in the target environment.
- [ ] Confirm region base URL.
- [ ] Ensure `advanced.cross_id` is set after creation.
- [ ] Validate workflows are enabled in GitHub Actions.

## References

- Boomi Data Integration API docs: https://developer.boomi.com/docs/api/dataintegration/Rivers
