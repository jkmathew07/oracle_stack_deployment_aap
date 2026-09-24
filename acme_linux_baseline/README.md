# acme.linux_baseline

Runs scoped package, user, group, sysctl, login limit and HugePages changes.
Requires an approved OS image with THP, SELinux, swap and firewall policy
already set. No RPM downloads, GPG bypass or generic service disabling are
performed.

`vm.nr_hugepages` is always calculated from actual server RAM
(`oracle_hugepages.target_pct`, default 56%) unless an explicit override in
`oracle_hugepages.nr` already meets `hugepages_validation.min_pct` — never a
hardcoded page count — and the applied value is read back and asserted
correct before the role reports success.
