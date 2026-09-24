# Migration history

This bundle went through two passes. The notes from both are kept here so
the reasoning behind the current state is traceable.

## Pass 1 — hardening (produced `oracle-aap27-hardened.zip`)

- Replaced the original gate/phase-engine collections with a narrow,
  fail-closed Oracle 19c software Home implementation.
- Moved shared OS variables beside `playbooks/` so Ansible loads them from
  both AAP and CLI. Oracle release data is loaded explicitly from `config/`.
- Replaced assert-based decision-node branches with a linear workflow and
  scoped no-op stages: every node always runs, and no-ops internally via
  `when: deployment_plan.*` — so a red node in the AAP UI only ever means a
  genuine failure, never "not selected." Production has one approval after
  the complete preflight plan and before any mutation.
- Replaced ad hoc boolean vars with a single normalized `deployment_plan`
  object, validated once at preflight and re-checked (target identity +
  inventory tier) at the top of every subsequent node.
- Every remote command uses `ansible.builtin.command` with `argv:` — no
  `shell`, no `raw`, anywhere.
- Added SHA-256 verification for every requested media/patch artifact on
  the target before any mutation, pinned collection versions, an AAP 2.7 EE
  baseline, `ansible-lint` + an offline contract-test script, and a release
  checklist. Fixed the previous build's `DB_RU_PATCH_FILE == GRID_RU_PATCH_FILE`
  bug by requiring a distinct, explicitly-approved placeholder — no patch is
  applied until a real ID, archive and expected-inventory manifest are supplied.
- Traded scope for that rigor: 26ai support and interim/one-off patching
  were dropped entirely in this pass.

## Pass 2 — merge (this bundle)

Took Pass 1 as the base (independently verified — see below — to be the
stronger foundation) and restored what it had traded away, without
reintroducing the problems Pass 1 fixed:

- **HugePages restored.** `configure_baseline` now calculates
  `vm.nr_hugepages` from actual RAM (`oracle_hugepages.target_pct`, default
  56%, floor `hugepages_validation.min_pct`) exactly as the pre-hardening
  design did — Pass 1 had dropped this entirely, a real functional gap for
  a production Oracle deployment. The applied value is read back and
  asserted correct before the role reports success, matching Pass 1's own
  "verify, don't just trust" pattern.
- **26ai support restored, and made data-driven rather than hardcoded.**
  `preflight` no longer hardcodes `release == '19c'`; the OS/version
  compatibility matrix (`SUPPORTED_OS`), the "RU required on this major
  version" rule (`REQUIRE_RU_ON_MAJOR_VERSIONS`), and the response-file
  schema suffix (`RESPONSE_FILE_SCHEMA_VERSION`) are now owned by each
  release's own `config/releases/*.yml`. Added `26ai.yml` in the same
  fail-closed-placeholder style Pass 1 established for 19c — nothing in it
  has been qualified; every `CHANGE_ME`/`REPLACE_WITH_*` value must be
  replaced with an approved, verified value before a 26ai run can proceed
  past preflight.
- **Interim/one-off patching restored**, as new `patch_grid_oneoffs` /
  `patch_db_oneoffs` roles reusing Pass 1's own `stage_patch`/`update_opatch`
  roles, preserving the original design's deliberate warn-not-fail behavior
  (a one-off conflict is a logged warning, not a deployment failure, since
  the RU alone already brings the home to a valid, supported state). Wired
  into the existing `04_patch_grid.yml` / `06_patch_db.yml` nodes as
  additional steps — no new workflow nodes, so Pass 1's clean linear graph
  and `aap_bootstrap` wiring are unchanged.
- **Fixed a latent fragility in Pass 1's production-approval gate.** It
  asserted `awx_workflow_job_name == 'Oracle Deploy - Prod'` — a variable
  name that isn't a confirmed, documented AAP-injected value (there's
  community uncertainty about even the more established
  `tower_workflow_job_id` existing across AAP versions). The gate now
  relies solely on `workflow_allowed_tiers`, an extra_var set explicitly
  per-workflow in `bootstrap_aap.yml` — deterministic, not a guess. Even
  under the old check, the failure mode was safe (blocks all prod runs
  rather than silently bypassing the gate) — this closes the gap without
  having weakened anything.
- **A real bug was introduced and caught during this pass, not shipped**:
  the first draft of `patch_grid_oneoffs`/`patch_db_oneoffs` put `loop:` on
  a `block:`, which Ansible does not support. `ansible-lint` (run for real,
  not just documented) caught it immediately; fixed by moving the per-item
  block/rescue into an included task file (`apply_one_interim_patch.yml`)
  and looping over the `include_tasks` call instead, which is the
  supported pattern.
- Extended `tests/verify_contract.py` with regression guards for
  everything above: every release config must have distinct GRID_RU/DB_RU
  paths *and* ids, must define `SUPPORTED_OS` and
  `RESPONSE_FILE_SCHEMA_VERSION`, both interim-patch lists must exist; the
  one-off roles must exist, be wired into the patch nodes, and must never
  call `ansible.builtin.fail`; `configure_baseline` must configure
  `vm.nr_hugepages` via RAM-derived sizing, not a hardcoded value; and
  `00_preflight.yml` must never reference `awx_workflow_job_name` again.
  All of it was actually run — `ansible-core 2.21.4` syntax-check across
  all four `params/examples/*.yml` scenarios (19c, 26ai, patch-only,
  patch-with-interim), `ansible-lint --offline` at the `production`
  profile for the two new roles, and the full `verify_contract.py` suite —
  not just asserted in prose.

## What's still true from Pass 1, unchanged

- Still fully fail-closed: `19c.yml`'s real values remain
  `REPLACE_WITH_VERIFIED_SHA256` / `REPLACE_WITH_APPROVED_DB_RU_ZIP`
  placeholders, exactly as Pass 1 left them, and `26ai.yml` follows the
  same pattern. No artifact checksum, DB RU, or 26ai media path has been
  invented or filled in during this merge.
- Still zero `shell`/`raw` usage anywhere, including in the new roles.
- Still one production approval, after the complete preflight plan and
  before any mutation — the graph shape from Pass 1 is unchanged.
- SELinux/firewalld/swap posture: unchanged from Pass 1 (see
  `RELEASE_CHECKLIST.md` — these remain site-dependent gates, not
  something this automation configures).

The production workflow, Oracle media (19c and 26ai), interim patch
approvals, support certification, controller collection version, and
actual target hosts still require site qualification. See
`RELEASE_CHECKLIST.md` before any production run.
