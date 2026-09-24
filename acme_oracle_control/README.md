# Oracle 19c/26ai home deployment for Ansible Automation Platform 2.7

## Supported scope

Single host Oracle Restart Grid installation, Database Home software-only
installation, offline Grid/DB Home RU application, and best-effort
Grid/DB interim (one-off) patching for both **19c and 26ai**. RAC, ASM,
DBCA, database lifecycle and `datapatch` are **not supported** by this
release. Patch-only requests are supported for registered existing homes.
All non-requested stages succeed without changes. A failed RU/install stage
stops the workflow; a failed interim/one-off patch is logged as a warning
and does not (see `acme.oracle_rdbms` README). Partial Oracle installer runs
require a DBA recovery plan.

26ai support is present but **unqualified**: every media path, RU, OPatch
and SHA-256 value in `config/releases/26ai.yml` is a placeholder, and its
`SUPPORTED_OS` / `RESPONSE_FILE_SCHEMA_VERSION` values are reasonable
assumptions, not verified against Oracle's actual 26ai certification and
installer documentation. Treat 19c as the qualified path and 26ai as
scaffolding to qualify before relying on it.

## Mandatory site configuration

1. Publish both `acme.*` collections at version 2.1.0 to your private hub.
   Build the EE from `execution-environment.yml`, qualify the exact
   `ansible.posix` version and base image, then deploy the tested EE by digest.
2. Replace the example inventory with an approved inventory source. Every
   target must belong to `oracle_targets` and have a controlled
   `deployment_tier` host variable matching the survey environment. Limit
   source changes and inventory write access to automation administrators.
3. Review `playbooks/group_vars/all/` kernel parameters, HugePages sizing,
   users, package names and limits against your certified OS images. Install
   packages only from signed enterprise repositories. Ensure the image
   already has THP disabled, SELinux enabled, approved firewall rules, swap
   and required mounts — this automation verifies that baseline at preflight,
   it does not configure it.
4. Fill `config/releases/19c.yml` **and** `config/releases/26ai.yml` with the
   correct, independently verified Oracle media, OPatch and RU SHA-256
   values for each release you intend to use. GRID_RU and DB_RU are
   intentionally distinct, separately-tracked artifacts in both files — do
   not point them at the same file. Populate `GRID_INTERIM_PATCHES` /
   `DB_INTERIM_PATCHES` only with approved, checksummed one-off patches; both
   default to an empty list. Verify patch IDs, home paths, `SUPPORTED_OS`,
   `REQUIRE_RU_ON_MAJOR_VERSIONS`, `RESPONSE_FILE_SCHEMA_VERSION` and Oracle
   support certification before approving a release — especially for 26ai,
   where none of this has been qualified yet.
5. Put this release bundle at the root of the Git repository referenced by the
   AAP Project. If publishing only `acme_oracle_control/` as the project root,
   set `aap_project_playbook_prefix` to an empty string in bootstrap
   variables. Create AAP organization, inventory source, Machine Credential,
   Project SCM credential and the built EE. Edit
   `aap_bootstrap/bootstrap_vars.yml` to the names and immutable release ref.
   Run bootstrap using the `ansible.controller` collection provided for your
   AAP 2.7 installation. Keep child template Execute rights restricted and
   assign separate approvers to the production workflow. The single
   production approval covers the entire validated change plan before OS
   and Oracle modifications begin, and is enforced via
   `workflow_allowed_tiers` (an extra_var set explicitly per-workflow in
   bootstrap — not a guessed AAP-internal variable name).
6. Prevent overlapping changes to the same target through a change scheduler
   or target lock service. `allow_simultaneous: false` serializes each workflow
   template, but cannot coordinate another workflow or a CLI invocation.

Credentials and SSH keys belong in AAP credentials or a managed local SSH
agent. Do not store them in inventory, Git or params. Production operations
must use the AAP approval workflow. The CLI path is limited to dev/staging —
`workflow_allowed_tiers` and `awx_workflow_job_id` are never set outside a
real AAP workflow run, so a CLI attempt against `deploy_environment: prod`
always fails closed at preflight.

## AAP flow

`preflight → approval (prod only) → baseline → reboot → Grid install →
Grid RU + Grid interim patches → DB install → DB RU + DB interim patches →
verify`. Preflight publishes one validated plan with `set_stats` (global
artifacts); other jobs receive it as an extra variable. The target is
checked against that plan before any changes on every job. No decision node
signals an intended skip by failing. `verify` re-checks live target state
(HAS status, OPatch inventory on both homes, `vm.nr_hugepages`) and fails
if the RU-level state is wrong — interim/one-off patch state is reported
for visibility only and never fails this final check.

## Command-line flow

From `acme_oracle_control/` with the same qualified Ansible Core 2.20 and
collections available (or the same EE through `ansible-navigator`):

```text
ansible-galaxy collection install ansible.posix:2.1.0 -p collections
ansible-galaxy collection install ../dist/acme-linux_baseline-2.1.0.tar.gz \
  ../dist/acme-oracle_rdbms-2.1.0.tar.gz -p collections
ansible-playbook -i inventory/oracle_targets.yml \
  playbooks/local_run.yml -e @params/examples/grid_and_db.yml
```

`local_run.yml` imports the same stage playbooks. Set `change_ticket`, exact
inventory `hostname`, tier, release (`19c` or `26ai`), two install booleans
and patch scope in an approved params file — see `params/examples/` for one
example per scenario (19c, 26ai, patch-only, patch-with-interim). The
samples use fake targets and intentionally unconfigured SHA-256 values; they
cannot modify a real host until these are replaced. Use `--syntax-check` and
the offline contract check (`python tests/verify_contract.py`) before running.

No shell or raw Ansible actions are used. Vendor installers are invoked using
`ansible.builtin.command` with explicit `argv`. RU patch conflicts fail
rather than rolling back other patches; interim/one-off patch conflicts are
logged as warnings by design (see `acme.oracle_rdbms` README). Software Home
verification does not imply DB SQL patching; run and verify `datapatch`
under a separate approved DBA procedure before returning databases to service.
