# Oracle 19c / 26ai deployment control

Deploys Oracle Restart (Grid) and/or a standalone Database software home on
one approved host per run, from **AAP 2.7** or the **command line**, using
the same playbooks and four collections:

| Collection | Purpose |
|---|---|
| `acme.linux_baseline` | OS packages, users/groups, kernel, limits, HugePages |
| `acme.oracle_common` | Request/plan, AAP workflow guard, host preflight (shared by both releases) |
| `acme.oracle_19c` | 19c install with `-applyRU`, RU verification, interim patches |
| `acme.oracle_26ai` | 26ai install from Oracle-patched gold images (no patching) |

Homes are **RU-versioned** from `RU_VERSION` in `config/releases/<release>.yml`:
`/u01/app/<RU_VERSION>/grid` and `/u01/app/oracle/product/<RU_VERSION>/oracle`.
A new RU (19c) or gold image (26ai) is always a new home; existing homes are
never RU-patched in place. No database is created, moved or datapatched.

## Stages

| Node | 19c playbook | 26ai playbook |
|---|---|---|
| preflight | `19c_00_preflight.yml` | `26ai_00_preflight.yml` |
| approval | prod workflows only | prod workflows only |
| baseline | `common_01_baseline.yml` | `common_01_baseline.yml` |
| reboot | `common_02_reboot.yml` | `common_02_reboot.yml` |
| grid install | `19c_03_install_grid.yml` | `26ai_03_install_grid.yml` |
| grid patch | `19c_04_patch_grid.yml` | — |
| db install | `19c_05_install_db.yml` | `26ai_04_install_db.yml` |
| db patch | `19c_06_patch_db.yml` | — |
| verify | `19c_07_verify.yml` | `26ai_05_verify.yml` |

Node 00 validates the request on localhost (no host contact), resolves the
homes, lists the media, shows the plan for approval, then runs read-only
checks on the target. Every later node first runs `stage_guard`.

## Media integrity (SHA-256 optional)

Media comes from Oracle Support. For each artifact, `sha256: ''` means "not
pinned": preflight checks the file exists and tests the archive with
`unzip -tq`. Paste the SHA-256 from the Oracle Support download page to pin
the exact file. A malformed value fails closed. Staged Oracle RPMs (RHEL)
always get `rpm -K --nosignature`; repo packages rely on the repos' GPG signing.

## Command line (ansible-playbook)

```bash
cd acme_oracle_control
# Collections from this checkout (ansible.posix comes from Galaxy/Hub):
ansible-galaxy collection install -r requirements-local.yml -p collections --force
# ...or the published versions from Private Automation Hub:
# ansible-galaxy collection install -r requirements.yml -p collections

ansible-playbook playbooks/19c_site.yml  -e @params/examples/19c_grid_and_db.yml
ansible-playbook playbooks/26ai_site.yml -e @params/examples/26ai_grid_and_db.yml
```

Run from `acme_oracle_control` so `ansible.cfg` is used (Ansible ignores it
in a world-writable directory — keep the checkout `chmod -R go-w`). The
`*_site.yml` playbooks run every stage in one process, so the plan stays in
memory. Production is refused outside AAP; dev and staging are allowed.

## AAP 2.7

1. Publish the four collections to Private Automation Hub and build the EE
   from `execution-environment.yml` (it also needs `ansible.controller`).
2. Create the organization, inventory, Machine credential, project SCM
   credential, a read-only **Red Hat Ansible Automation Platform** credential
   (`aap_controller_credential`), and the teams named in
   `playbooks/group_vars/all/aap_policy.yml` and `aap_change_approver_team`.
3. Edit `aap_bootstrap/bootstrap_vars.yml`, then run
   `ansible-playbook aap_bootstrap/bootstrap_aap.yml` with `ansible.controller`.

This creates 12 job templates and four workflows —
`Oracle 19c Deploy - Dev/Staging`, `Oracle 19c Deploy - Prod`,
`Oracle 26ai Deploy - Dev/Staging`, `Oracle 26ai Deploy - Prod` — each with
its own survey (26ai has no patch scope). Operators get Execute on
workflows only; approvers get Approve on the prod workflows. Child job
templates never prompt for variables, and `workflow_guard` proves through
the controller API that each job belongs to a running workflow owning that
release and tier, that this run's approval succeeded, and that the plan is
the one this run's preflight published.

`allow_simultaneous: false` serialises each template; coordinate changes to
the same host across workflows or CLI runs through change scheduling.
