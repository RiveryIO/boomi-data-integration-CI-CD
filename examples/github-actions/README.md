# GitHub Actions — Optional Examples

These workflow files are **optional reference implementations** for teams that use
GitHub Actions as their CI platform.

The Python scripts in `scripts/` are fully CI-agnostic and can be called from any
CI system (Bitbucket Pipelines, GitLab CI, Jenkins, etc.) or run locally.
See the [root README](../../README.md) for the canonical script reference and
environment-variable documentation.

## Using these workflows

1. Copy the workflow files you need into `.github/workflows/` in your repository.
2. Configure the three required repository secrets (Settings → Secrets and variables → Actions):

   | Secret | Description |
   |--------|-------------|
   | `ACCOUNT_ID` | Your Boomi Data Integration account ID |
   | `ENV_ID` | Target environment ID (use per-environment secrets for multi-env repos) |
   | `TOKEN` | Boomi Data Integration API token |

3. All workflows are `workflow_dispatch` (manual trigger). Run them from the
   **Actions** tab → select workflow → **Run workflow**.

## Workflow catalogue

| File | Purpose |
|------|---------|
| `river-create.yml` | Create a new river from a pipeline YAML; prints the `river_cross_id` you must stamp back into the YAML |
| `river-update.yml` | Push YAML changes to the live river; stamps `advanced.ci_metadata`; auto-commits the updated YAML |
| `river-activate.yml` | Activate a river (start scheduling / CDC) |
| `river-run.yml` | Trigger an on-demand river run |
| `river-disable.yml` | Disable a river (pause scheduling / CDC) |
| `export-river.yml` | Export a live river to JSON + regenerate its pipeline YAML |
| `export-connections.yml` | Export the connection inventory as sanitised JSON |
| `export-schemas-tables.yml` | Discover schemas and tables for a given connection |

## Default pipeline path

Workflows default to `configs/pipelines/team-a/mysql_to_snowflake_demo.yml`.
Override via the `pipeline_config` input when running the workflow.

## Notes

- `river-update.yml` has `contents: write` permission so the bot can commit the
  updated YAML back to the branch.  Grant this permission deliberately and limit
  which branches can trigger the workflow in production.
- The `export-*` workflows also commit output files; review the commit author
  (`github-actions[bot]`) and adjust branch-protection rules as needed.
