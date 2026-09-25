#!/usr/bin/env python3
"""Offline invariants for the AAP and CLI distribution; no target mutations."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / 'acme_oracle_control'


def tasks(value):
    if isinstance(value, dict):
        if any(k in value for k in ('ansible.builtin.shell', 'ansible.builtin.raw', 'raw')) or (
            'shell' in value and value['shell'] not in ('/bin/bash', '{{ item.shell }}')
        ):
            raise AssertionError('Shell or raw action found')
        if 'ansible.builtin.command' in value:
            command = value['ansible.builtin.command']
            assert isinstance(command, dict) and isinstance(command.get('argv'), list), 'Command must use argv'
        for item in value.values():
            tasks(item)
    elif isinstance(value, list):
        for item in value:
            tasks(item)


def verify():
    for file in ROOT.rglob('*.yml'):
        for document in yaml.safe_load_all(file.read_text()):
            tasks(document)
    bootstrap = yaml.safe_load((CONTROL / 'aap_bootstrap/bootstrap_vars.yml').read_text())
    ids = {item['identifier'] for item in bootstrap['aap_nodes']}
    assert len(ids) == 8
    links = bootstrap['aap_links']
    assert [link['from'] for link in links] == [
        'baseline', 'reboot', 'grid_install', 'grid_patch', 'db_install', 'db_patch'
    ]
    assert [link['to'] for link in links] == [
        'reboot', 'grid_install', 'grid_patch', 'db_install', 'db_patch', 'verify'
    ]
    assert len(bootstrap['aap_workflows']) == 2
    for node in bootstrap['aap_nodes']:
        assert (CONTROL / node['playbook']).exists(), node
        assert (ROOT / (bootstrap['aap_project_playbook_prefix'] + node['playbook'])).exists(), node
    run = yaml.safe_load((CONTROL / 'playbooks/local_run.yml').read_text())
    assert [Path(entry['import_playbook']).stem for entry in run] == [
        Path(node['playbook']).stem for node in bootstrap['aap_nodes']
    ]

    # ── Every release config: distinct GRID_RU/DB_RU, compatibility data present ──
    releases_dir = CONTROL / 'config/releases'
    release_files = sorted(releases_dir.glob('*.yml'))
    assert len(release_files) >= 2, 'Expected at least 19c.yml and 26ai.yml'
    for rfile in release_files:
        release = yaml.safe_load(rfile.read_text())
        assert release['GRID_RU']['path'] != release['DB_RU']['path'], \
            f'{rfile.name}: GRID_RU and DB_RU must not share a path (regression guard)'
        assert release['GRID_RU']['id'] != release['DB_RU']['id'], \
            f'{rfile.name}: GRID_RU and DB_RU must not share a patch id'
        assert release.get('SUPPORTED_OS'), f'{rfile.name}: SUPPORTED_OS must be defined and non-empty'
        assert 'RESPONSE_FILE_SCHEMA_VERSION' in release, f'{rfile.name}: RESPONSE_FILE_SCHEMA_VERSION must be defined'
        assert 'GRID_INTERIM_PATCHES' in release and 'DB_INTERIM_PATCHES' in release, \
            f'{rfile.name}: interim patch lists must be defined (even if empty)'
        assert 'ru_version' in release['GRID_RU'] and 'ru_version' in release['DB_RU'], \
            f'{rfile.name}: GRID_RU/DB_RU must declare ru_version for the minimum-RU check'
        assert 'MIN_RU_VERSION_ON_MAJOR_VERSION' in release, \
            f'{rfile.name}: MIN_RU_VERSION_ON_MAJOR_VERSION must be defined (even if empty)'
        assert 'REQUIRE_RU_ON_MAJOR_VERSIONS' not in release, \
            f'{rfile.name}: regression guard — REQUIRE_RU_ON_MAJOR_VERSIONS was replaced by MIN_RU_VERSION_ON_MAJOR_VERSION'
        assert 'PREINSTALL_PACKAGE' in release and 'name' in release['PREINSTALL_PACKAGE'], \
            f'{rfile.name}: PREINSTALL_PACKAGE.name must be defined'
        assert 'rhel' in release['PREINSTALL_PACKAGE'], \
            f'{rfile.name}: PREINSTALL_PACKAGE.rhel must be defined (even if only placeholder entries)'
    release_names = {f.stem for f in release_files}
    assert {'19c', '26ai'} <= release_names, 'Both 19c and 26ai release configs must exist'

    # ── 19c specifically: RHEL/OEL 10 supported, with the stated minimum RUs ──
    release_19c = yaml.safe_load((releases_dir / '19c.yml').read_text())
    supported_majors = {(o['distribution'], o['major_version']) for o in release_19c['SUPPORTED_OS']}
    assert ('OracleLinux', '10') in supported_majors and ('RedHat', '10') in supported_majors, \
        '19c.yml: SUPPORTED_OS must include major_version 10 for both distributions'
    assert release_19c['MIN_RU_VERSION_ON_MAJOR_VERSION'].get('9') == 23, \
        '19c.yml: MIN_RU_VERSION_ON_MAJOR_VERSION["9"] must be 23'
    assert release_19c['MIN_RU_VERSION_ON_MAJOR_VERSION'].get('10') == 32, \
        '19c.yml: MIN_RU_VERSION_ON_MAJOR_VERSION["10"] must be 32'

    # ── Preflight must enforce the minimum-RU rule, and never GPG-bypass the preinstall RPM ──
    preflight_src = (ROOT / 'acme_oracle_rdbms/roles/preflight/tasks/main.yml').read_text()
    assert 'MIN_RU_VERSION_ON_MAJOR_VERSION' in preflight_src, \
        'preflight must reference MIN_RU_VERSION_ON_MAJOR_VERSION'
    assert 'REQUIRE_RU_ON_MAJOR_VERSIONS' not in preflight_src, \
        'regression guard: preflight must not reference the retired REQUIRE_RU_ON_MAJOR_VERSIONS'
    baseline_src_full = (ROOT / 'acme_linux_baseline/roles/configure_baseline/tasks/main.yml').read_text()
    assert 'deployment_plan.release_cfg.PREINSTALL_PACKAGE.name' in baseline_src_full, \
        'PREINSTALL_PACKAGE.name must be read from config, not hardcoded in the role'
    assert 'disable_gpg_check: true' not in baseline_src_full, \
        'regression guard: the RHEL preinstall RPM must never disable GPG checking'
    assert 'get_url' not in baseline_src_full and 'rpm_key' not in baseline_src_full, \
        'regression guard: the RHEL preinstall RPM must be pre-staged + checksummed by preflight, ' \
        'not live-downloaded (see MIGRATION_NOTES.md) — no get_url/rpm_key in configure_baseline'
    preflight_full = (ROOT / 'acme_oracle_rdbms/roles/preflight/tasks/main.yml').read_text()
    assert "combine({'label': 'Oracle preinstall package'})" in preflight_full, \
        'preflight must compute the RHEL preinstall RPM as an artifact for the ' \
        'existing generic checksum loop to cover'
    assert 'deployment_plan.artifacts + preflight_rhel_preinstall_artifact' in preflight_full, \
        'the generic checksum loop must include the RHEL preinstall artifact'
    for rfile in release_files:
        release = yaml.safe_load(rfile.read_text())
        for major, entry in release['PREINSTALL_PACKAGE'].get('rhel', {}).items():
            assert 'path' in entry and 'sha256' in entry and 'url' not in entry, \
                f'{rfile.name}: PREINSTALL_PACKAGE.rhel["{major}"] must be a local {{path, sha256}} artifact, not a URL'

    # ── Survey must offer both releases ──────────────────────────────────
    release_question = next(q for q in bootstrap['aap_survey_spec']['spec'] if q['variable'] == 'oracle_release')
    assert '19c' in release_question['choices'] and '26ai' in release_question['choices']

    # ── Interim-patch (one-off) roles exist and are wired into the patch nodes ──
    for role in ('patch_grid_oneoffs', 'patch_db_oneoffs'):
        assert (ROOT / 'acme_oracle_rdbms/roles' / role / 'tasks/main.yml').exists(), \
            f'Missing role: {role}'
    grid_patch_pb = (CONTROL / 'playbooks/04_patch_grid.yml').read_text()
    assert 'acme.oracle_rdbms.patch_grid_oneoffs' in grid_patch_pb, \
        '04_patch_grid.yml must include patch_grid_oneoffs'
    db_patch_pb = (CONTROL / 'playbooks/06_patch_db.yml').read_text()
    assert 'acme.oracle_rdbms.patch_db_oneoffs' in db_patch_pb, \
        '06_patch_db.yml must include patch_db_oneoffs'

    # ── One-off roles must never call ansible.builtin.fail (warn-not-fail contract) ──
    for role in ('patch_grid_oneoffs', 'patch_db_oneoffs'):
        role_dir = ROOT / 'acme_oracle_rdbms/roles' / role / 'tasks'
        role_src = '\n'.join(f.read_text() for f in role_dir.glob('*.yml'))
        assert 'ansible.builtin.fail' not in role_src, \
            f'{role}: must stay warn-not-fail on interim patch conflicts, per its own header comment'

    # ── HugePages must be configured, not just referenced ────────────────
    baseline_src = (ROOT / 'acme_linux_baseline/roles/configure_baseline/tasks/main.yml').read_text()
    assert 'vm.nr_hugepages' in baseline_src, 'HugePages configuration is missing from configure_baseline'
    assert 'oracle_hugepages' in baseline_src, 'HugePages sizing must be RAM-derived via oracle_hugepages, not a hardcoded value'

    # ── Production approval gate must not depend on a guessed AAP variable name ──
    preflight_pb = (CONTROL / 'playbooks/00_preflight.yml').read_text()
    assert 'awx_workflow_job_name' not in preflight_pb, \
        'Regression guard: do not reintroduce the unverified awx_workflow_job_name check'
    assert 'workflow_allowed_tiers' in preflight_pb, \
        'Production gate must rely on workflow_allowed_tiers (set explicitly in bootstrap_aap.yml)'

    print('Offline security and graph checks passed')


if __name__ == '__main__':
    verify()
