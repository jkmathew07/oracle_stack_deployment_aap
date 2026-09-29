# acme.oracle_common

Release-agnostic controls shared by `acme.oracle_19c` and `acme.oracle_26ai`.

| Role | Runs | Purpose |
|---|---|---|
| `request_plan` | node 00, localhost | Validate request, prove workflow provenance, load `config/releases/<release>.yml`, resolve RU-versioned homes (`request_plan_base`) |
| `publish_plan` | node 00, localhost | Publish `deployment_plan` (set_stats for AAP, host fact for CLI) and display it for approval |
| `workflow_guard` | every node | AAP: prove via the controller API that the job belongs to a running workflow owning the tier and release, that this run's approval succeeded and that the plan is the one this run's preflight published. CLI: dev/staging only |
| `stage_guard` | nodes 01+ | Plan/target/tier/release binding + `workflow_guard` |
| `configure_thp` | baseline node, target | Transparent HugePages = `madvise` (or release `THP_MODE`) now and at every boot via `oracle-thp.service`; no grub change, no reboot |
| `host_preflight` | node 00, target | OS/sizing/SELinux/THP, path checks, media (optional SHA-256, else `unzip -tq`), local RPMs, inventory, Oracle Restart (`olr.loc`) and Grid ≥ DB RU checks |

A release collection supplies its own `plan` role (between `request_plan` and
`publish_plan`) and its own release preflight, install and verify roles.
