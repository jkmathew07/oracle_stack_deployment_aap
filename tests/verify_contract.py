#!/usr/bin/env python3
"""Offline invariants for the 4-collection layout (AAP + CLI); no target mutations."""
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / 'acme_oracle_control'
COLL = {name: ROOT / f'acme_{name}' for name in ('linux_baseline', 'oracle_common', 'oracle_19c', 'oracle_26ai')}
HEX64 = re.compile(r'^[0-9a-f]{64}$')


def load(path):
    return yaml.safe_load(Path(path).read_text())


def text(path):
    return Path(path).read_text()


def role_src(coll, role):
    return '\n'.join(f.read_text() for f in sorted((COLL[coll] / 'roles' / role).rglob('*.yml')))


def no_shell(value):
    if isinstance(value, dict):
        if any(k in value for k in ('ansible.builtin.shell', 'ansible.builtin.raw', 'raw')) or (
            'shell' in value and value['shell'] not in ('/bin/bash', '{{ item.shell }}')
        ):
            raise AssertionError('Shell or raw action found')
        if 'ansible.builtin.command' in value:
            command = value['ansible.builtin.command']
            assert isinstance(command, dict) and isinstance(command.get('argv'), list), 'Command must use argv'
        for item in value.values():
            no_shell(item)
    elif isinstance(value, list):
        for item in value:
            no_shell(item)


def verify():
    code = [f for f in ROOT.rglob('*.yml') if '.git' not in f.parts and 'collections' not in f.relative_to(ROOT).parts[1:2]]
    for file in code:
        for document in yaml.safe_load_all(file.read_text()):
            no_shell(document)
        src = file.read_text()
        assert 'oracle_rdbms' not in src, f'{file}: stale acme.oracle_rdbms reference'
        assert 'workflow_allowed_tiers' not in src, f'{file}: trust must not come from an extra_var'

    # ── Collections and dependencies ─────────────────────────────────────
    meta = {n: load(p / 'galaxy.yml') for n, p in COLL.items()}
    for n in ('oracle_19c', 'oracle_26ai'):
        assert 'acme.oracle_common' in meta[n]['dependencies'], f'{n} must depend on acme.oracle_common'
    assert 'ansible.controller' not in (meta['oracle_common']['dependencies'] or {}), \
        'ansible.controller must not be a hard dependency (CLI runs without it)'
    req = {c['name']: c.get('version') for c in load(CONTROL / 'requirements.yml')['collections']}
    for n, m in meta.items():
        assert req.get(f'acme.{n}') == str(m['version']), f'requirements.yml must pin acme.{n} {m["version"]}'
    local = [c['name'] for c in load(CONTROL / 'requirements-local.yml')['collections'] if c.get('type') == 'dir']
    assert sorted(local) == sorted(f'../acme_{n}' for n in COLL), 'requirements-local.yml must list all 4 source dirs'

    for n, p in COLL.items():
        assert load(p / 'meta/runtime.yml')['requires_ansible'] == '>=2.18.0', \
            f'{n}: requires_ansible must be >=2.18.0 (no upper pin; CI tests 2.20 and 2.21)'

    # ── AAP policy, graphs, job templates, site playbooks ────────────────
    policy = load(CONTROL / 'playbooks/group_vars/all/aap_policy.yml')
    boot = load(CONTROL / 'aap_bootstrap/bootstrap_vars.yml')
    assert 'aap_workflows' not in boot, 'aap_workflows must live only in aap_policy.yml'
    jts = {jt['name']: jt['playbook'] for jt in boot['aap_job_templates']}
    for pb in jts.values():
        assert (CONTROL / pb).exists(), pb
    for release in ('19c', '26ai'):
        wfs = [w for w in policy['aap_workflows'] if w['release'] == release]
        prod = [w for w in wfs if 'prod' in w['allowed']]
        assert len(prod) == 1 and prod[0]['allowed'] == ['prod'] and prod[0]['requires_approval'] is True, \
            f'{release}: exactly one workflow may own prod, alone, and it must require approval'
        graph = boot['aap_release_graphs'][release]
        ids = [n['identifier'] for n in graph['nodes']]
        assert ids[0] == policy['aap_preflight_node_identifier'] and 'baseline' in ids
        for n in graph['nodes']:
            assert n['job_template'] in jts, n
        for link in graph['links']:
            assert link['from'] in ids and link['to'] in ids, link
        # Linear chain preflight -> baseline -> ... must match the CLI site playbook order.
        order = ['preflight', 'baseline']
        nxt = {l['from']: l['to'] for l in graph['links']}
        while order[-1] in nxt:
            order.append(nxt[order[-1]])
        assert sorted(order) == sorted(ids), f'{release}: graph is not one linear chain'
        by_id = {n['identifier']: Path(jts[n['job_template']]).name for n in graph['nodes']}
        site = [e['import_playbook'] for e in load(CONTROL / f'playbooks/{release}_site.yml')]
        assert site == [by_id[i] for i in order], f'{release}_site.yml must import stages in workflow order'
        assert 'patch' in [q['variable'] for q in boot['aap_surveys'][release]] or release == '26ai'
    assert 'patch' not in [q['variable'] for q in boot['aap_surveys']['26ai']], '26ai has no patch scope'

    for pb in sorted((CONTROL / 'playbooks').glob('*.yml')):
        src = pb.read_text()
        if pb.name.endswith('_site.yml'):
            continue
        if '_00_preflight' in pb.name:
            release = pb.name.split('_')[0]
            assert 'acme.oracle_common.request_plan' in src and f"request_plan_release: '{release}'" in src
            assert f'acme.oracle_{release}.plan' in src and 'acme.oracle_common.publish_plan' in src
            assert 'acme.oracle_common.host_preflight' in src
        else:
            assert 'acme.oracle_common.stage_guard' in src, f'{pb.name} must run stage_guard'
            if not pb.name.startswith('common_'):
                assert f"stage_guard_release: '{pb.name.split('_')[0]}'" in src, f'{pb.name} must pin its release'

    bt = {t['name']: t for t in load(CONTROL / 'aap_bootstrap/bootstrap_aap.yml')[0]['tasks']}
    jt = bt['Create child job templates']['ansible.controller.job_template']
    assert jt['ask_variables_on_launch'] is False, 'Child job templates must not prompt for variables'
    assert '{{ aap_controller_credential }}' in jt['credentials'], 'workflow_guard needs the controller credential'
    assert any('ansible.controller.role' in t for t in bt.values()), 'RBAC must be managed by bootstrap'
    guard = role_src('oracle_common', 'workflow_guard')
    assert 'workflow_guard_policy.release' in guard and 'to_json(sort_keys=true)' in guard

    # ── Release files ────────────────────────────────────────────────────
    for release in ('19c', '26ai'):
        cfg = load(CONTROL / f'config/releases/{release}.yml')
        assert cfg['RELEASE'] == release
        assert 'GRID_HOME' not in cfg and 'DB_HOME' not in cfg, 'homes come from *_HOME_PATTERN + RU_VERSION'
        for key in ('GRID_HOME_PATTERN', 'DB_HOME_PATTERN'):
            assert cfg[key].startswith('/') and cfg[key].count('{RU_VERSION}') == 1 and '/{RU_VERSION}/' in cfg[key]
        for key in ('ORA_INVENTORY', 'GRID_BASE', 'DB_BASE'):
            assert cfg[key].startswith('/') and not any(c in cfg[key] for c in '{}%$')
        assert not cfg['GRID_HOME_PATTERN'].startswith(cfg['GRID_BASE'] + '/')
        assert cfg.get('SUPPORTED_OS') and cfg.get('PREINSTALL_PACKAGE', {}).get('name')
        # Option B: sha256 optional - empty or a real 64-hex value, never a placeholder.
        for art in [v for v in cfg.values() if isinstance(v, dict) and 'path' in v] + \
                cfg.get('GRID_INTERIM_PATCHES', []) + cfg.get('DB_INTERIM_PATCHES', []):
            assert art.get('sha256', '') == '' or HEX64.match(art['sha256']), f'{release}: bad sha256 {art}'
    for pkg in load(CONTROL / 'playbooks/group_vars/all/os_packages.yml')['oracle_os_packages_local']:
        assert pkg.get('sha256', '') == '' or HEX64.match(pkg['sha256']), pkg

    c19 = load(CONTROL / 'config/releases/19c.yml')
    assert int(c19['RU_VERSION'].split('.')[c19['RU_NUMBER_INDEX']]) == c19['GRID_RU']['ru_version']
    assert c19['MIN_RU_VERSION_ON_MAJOR_VERSION'] == {'9': 23, '10': 32}
    assert {('OracleLinux', '10'), ('RedHat', '10')} <= {(o['distribution'], o['major_version']) for o in c19['SUPPORTED_OS']}
    c26 = load(CONTROL / 'config/releases/26ai.yml')
    for key in ('GRID_RU', 'DB_RU', 'OPATCH_ZIP', 'GRID_INTERIM_PATCHES', 'DB_INTERIM_PATCHES', 'BASE_VERSION'):
        assert key not in c26, f'26ai.yml: {key} does not apply to gold images'
    assert 'GRID_IMAGE' in c26 and 'DB_IMAGE' in c26

    # ── Common preflight ─────────────────────────────────────────────────
    hp = role_src('oracle_common', 'host_preflight')
    for needle in ('unzip, -tq', '/etc/oracle/olr.loc', 'rpm, -K, --nosignature', 'get_checksum'):
        assert needle in hp, f'host_preflight must contain {needle}'
    assert "replace('{RU_VERSION}'" in role_src('oracle_common', 'request_plan'), 'homes resolved by plain substitution'

    # ── 19c behaviour kept ───────────────────────────────────────────────
    for role in ('patch_grid', 'patch_db'):
        src = role_src('oracle_19c', role)
        assert ' apply' not in src and '- apply' not in src, f'{role}: in-place RU apply is not allowed'
    for role in ('patch_grid_oneoffs', 'patch_db_oneoffs'):
        assert 'rescue:' not in role_src('oracle_19c', role), f'{role}: apply failures must not be swallowed'
    grid_oneoff = load(COLL['oracle_19c'] / 'roles/patch_grid_oneoffs/tasks/apply_one_interim_patch.yml')
    cmds = [t for t in grid_oneoff[0]['block'] if 'ansible.builtin.command' in t]
    assert cmds and all(t['ansible.builtin.command']['argv'][0].endswith('/OPatch/opatchauto') and 'become_user' not in t
                        for t in cmds), 'Grid interim patches: opatchauto as root'
    assert 'orainstRoot.sh' in role_src('oracle_19c', 'install_db')
    assert '-applyRU' in role_src('oracle_19c', 'install_grid') and '-applyRU' in role_src('oracle_19c', 'install_db')
    assert 'MIN_RU_VERSION_ON_MAJOR_VERSION' in role_src('oracle_19c', 'preflight')

    # ── 26ai is install-only ─────────────────────────────────────────────
    all26 = '\n'.join(line for f in COLL['oracle_26ai'].rglob('*.yml')
                      for line in f.read_text().splitlines() if not line.lstrip().startswith('#'))
    for needle in ('opatch', 'OPatch', 'applyRU', 'GRID_RU', 'DB_RU', 'INTERIM'):
        assert needle not in all26, f'acme.oracle_26ai must not contain {needle}'
    assert 'orainstRoot.sh' in role_src('oracle_26ai', 'install_db')
    assert 'oraversion' in role_src('oracle_26ai', 'verify_home')

    # ── Baseline unchanged contract ──────────────────────────────────────
    base = role_src('linux_baseline', 'configure_baseline')
    assert 'vm.nr_hugepages' in base and 'oracle_hugepages' in base
    assert 'deployment_plan.release_cfg.PREINSTALL_PACKAGE.name' in base
    assert 'disable_gpg_check: true' not in base and 'get_url' not in base

    print('Offline security and graph checks passed')


if __name__ == '__main__':
    verify()
