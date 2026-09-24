# Release qualification and go-live gates

## Implemented controls

- AAP 2.7-compatible EE base selection with Ansible Core 2.20; exact EE image
  digest and Hub collection versions must be recorded at promotion time.
- No `shell` or `raw` actions. All direct executables use command `argv`.
- Target must be an exact member of `oracle_targets`; the inventory-assigned
  environment must match the request. Production requires
  `workflow_allowed_tiers == ['prod']`, which only the AAP production
  Workflow Job Template sets — not a guessed AAP-internal variable name —
  and its approval node before any change.
- Artifact SHA-256 checks run on the managed host before mutations, for
  media, RUs, OPatch, *and* any approved interim/one-off patches. No
  `-ignorePrereqFailure`, GPG bypass, automatic patch conflict rollback,
  wildcard package install, or blind recursive stage deletion.
- A missing registered patch target fails. Repeat runs check Oracle patch
  inventory rather than relying only on an earlier workflow flag.
- One process CLI run uses the same playbooks and skips no requested stage.
- HugePages (`vm.nr_hugepages`) is calculated from actual RAM and its
  applied value is read back and asserted correct — never left unconfigured.
- 19c and 26ai are both supported, from a shared data-driven compatibility
  matrix (`SUPPORTED_OS`, `REQUIRE_RU_ON_MAJOR_VERSIONS`) owned by each
  release's `config/releases/*.yml`, not hardcoded per-release logic.
- Interim/one-off patches (`GRID_INTERIM_PATCHES` / `DB_INTERIM_PATCHES`)
  apply after the RU and are deliberately best-effort: a conflict is a
  logged warning, never a deployment failure, since the RU alone already
  brings the home to a valid, supported state.

## Site-dependent mandatory gates

1. Provide real target inventory, managed Machine/Privilege Escalation
   credentials, signed package repositories, approved SELinux and firewall
   policy, capacity planning and change scheduling.
2. Replace all artifact placeholders with approved file paths and SHA-256
   digests for **both** `19c.yml` and `26ai.yml` (26ai has not been
   qualified at all — every value is a placeholder); identify the correct
   DB RU and stage layout for each release. Validate OS certification and
   required OS packages per target release/OS combination, and confirm
   `SUPPORTED_OS` / `REQUIRE_RU_ON_MAJOR_VERSIONS` / `RESPONSE_FILE_SCHEMA_VERSION`
   in each release file against Oracle's actual published certification —
   the shipped 26ai values are reasonable assumptions, not verified facts.
3. Build EE and collections; pin and sign the promoted EE digest. Dry-run AAP
   bootstrap against the installed certified `ansible.controller` version.
4. Run dev and staging installation, patch-only, combined, interim-patch,
   repeat, partial failure, rollback-runbook and production-approval tests
   on disposable Oracle targets, for both 19c and 26ai. Confirm Grid
   Restart, OPatch inventory and `vm.nr_hugepages` independently.
5. Arrange a DBA-owned DB start/stop and `datapatch` procedure for any existing
   database using a patched DB Home. SQL patch state is outside this software
   Home automation.
6. Apply AAP RBAC so only the workflow can execute child templates, restrict
   SCM/inventory modifications, and ensure approvers differ from requesters.
   Use a central lock to prevent same-target overlap across workflows/CLI.

These site gates must pass before operating on production hosts. The archive
contains no SSH secrets, license media or invented artifact checksums.
