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
    release_names = {f.stem for f in release_files}
    assert {'19c', '26ai'} <= release_names, 'Both 19c and 26ai release configs must exist'

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
