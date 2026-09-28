# acme.oracle_19c

Oracle 19c Restart (Grid) and Database software-only homes. Behaviour is
unchanged from `acme.oracle_rdbms` 2.3.0; only the namespace moved and the
release-agnostic controls moved to `acme.oracle_common`.

- Homes are RU-versioned (`/u01/app/<RU_VERSION>/grid`,
  `/u01/app/oracle/product/<RU_VERSION>/oracle`) and installed with
  `-applyRU`. A new RU is a new home; RUs are never applied in place.
- `patch_grid`/`patch_db` verify the RU of an existing home and prepare
  OPatch; `patch_*_oneoffs` apply approved interim patches (conflicts found
  by analysis are skipped with a warning, apply failures fail the job).
- No database is created, moved or datapatched.

Roles: `plan`, `preflight`, `install_grid`, `patch_grid`,
`patch_grid_oneoffs`, `install_db`, `patch_db`, `patch_db_oneoffs`,
`update_opatch`, `stage_patch`, `verify`.
