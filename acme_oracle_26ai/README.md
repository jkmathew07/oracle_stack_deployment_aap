# acme.oracle_26ai

Oracle AI Database 26ai Restart (Grid) and Database software-only homes from
the **patched gold images** Oracle ships. There is no OPatch, RU or interim
patching: a newer image is a new home.

- Homes are RU-versioned from the image version, e.g. `RU_VERSION: 23.26.1`
  -> `/u01/app/23.26.1/grid`, `/u01/app/oracle/product/23.26.1/oracle`.
- After install (and on every run) `verify_home` checks
  `oraversion -compositeVersion` starts with `RU_VERSION`, so a home can never
  hold a different image than its path claims.
- Response files use the 21c+ key format; confirm them against
  `<home>/install/response/*.rsp` in your image during qualification.

Roles: `plan`, `install_grid`, `install_db`, `verify_home`, `verify`.
