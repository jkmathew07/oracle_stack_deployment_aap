# acme.oracle_rdbms

Oracle 19c/26ai Grid Restart and DB software-only homes, plus offline RU and
best-effort interim/one-off patching. No database is created, started,
stopped, or patched with datapatch. DB RU maintenance requires all Oracle
instances stopped and subsequent DBA-led SQL patching. A failed or partial
installer is never automatically cleaned up. RU patch conflicts require
manual review; no automatic rollback or GPG bypass occurs. Interim/one-off
patch conflicts are logged as warnings and do not fail the deployment — the
RU alone already brings the home to a valid, supported state (see
`patch_grid_oneoffs` / `patch_db_oneoffs` role headers).

Release-specific OS compatibility, RU-required-on-major-version rules, and
response-file schema versions are data owned by each
`config/releases/{19c,26ai}.yml`, not hardcoded per-release logic in this
collection's roles.
