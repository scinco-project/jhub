from unittest.mock import Mock, patch

import pytest
from tornado import web

BASE_CONFIGS = {
    "images": [{"name": "image-1", "display_name": "Image 1"}],
    "mem_limit": "2G",
    "cpu_limit": "1",
    "extra_pod_config": {},
    "extra_container_config": {},
}

NEW_CONFIGS = {
    "images": [{"name": "image-1", "display_name": "Image 1"}],
    "mem_limit": "3G",
    "cpu_limit": "2",
    "extra_pod_config": {},
    "extra_container_config": {},
}

RESTRICTED_ID = "G-827652"

LDAP_USER = [
    {
        "dn": "uid=testuser,ou=People,dc=tacc,dc=utexas,dc=edu",
        "attributes": {
            "uidNumber": [1234],
            "gidNumber": [5678],
            "destinationIndicator": ["/home1/01234"],
        },
    }
]

LDAP_GROUPS = [
    "cn=G-800001,ou=Groups,dc=tacc,dc=utexas,dc=edu",
    "cn=G-800002,ou=Groups,dc=tacc,dc=utexas,dc=edu",
]

def _hook_spawner(fake_spawner, configs=None, ldap_groups=None):
    spawner = fake_spawner(configs=dict(configs or BASE_CONFIGS))
    spawner.ldap_groups = LDAP_GROUPS if ldap_groups is None else ldap_groups
    return spawner


def _hook_steps_called(spawner_hooks, spawner):
    all_steps = sorted({name for names in spawner_hooks.DEPLOYMENT_HOOKS.values() for name in names})
    calls = Mock()
    patchers = [patch.object(spawner_hooks, name) for name in all_steps]
    for name, patcher in zip(all_steps, patchers):
        calls.attach_mock(patcher.start(), name)
    try:
        spawner_hooks.hook(spawner)
    finally:
        for patcher in patchers:
            patcher.stop()
    return [c[0] for c in calls.mock_calls]


def test_hook_runs_tacc_steps(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("tacc")
    spawner = _hook_spawner(fake_spawner)

    assert _hook_steps_called(spawner_hooks, spawner) == [
        "retrieve_full_ldap_account", "is_user_allowed", "apply_restricted_allocation",
        "get_tapis_access_data", "get_ldap_data", "set_supplemental_gids", "get_all_configs",
        "set_selected_image", "set_cpu_mem_limits", "set_spawner_env", "get_mounts",
    ]


def test_hook_runs_designsafe_steps(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("designsafe")
    spawner = _hook_spawner(fake_spawner)

    assert _hook_steps_called(spawner_hooks, spawner) == [
        "retrieve_full_ldap_account", "check_user_restricted", "is_user_allowed",
        "get_tapis_access_data", "get_ldap_data", "set_supplemental_gids", "get_all_configs",
        "set_selected_image", "set_cpu_mem_limits", "set_spawner_env", "update_ds_env",
        "get_mounts", "get_licenses", "get_ds_projects",
    ]


def test_hook_runs_training_steps(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("training")
    spawner = _hook_spawner(fake_spawner)

    assert _hook_steps_called(spawner_hooks, spawner) == ["apply_training_uid_gid", "get_mounts"]


def test_hook_runs_no_steps_without_deployment_target(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("")
    spawner = _hook_spawner(fake_spawner)

    assert _hook_steps_called(spawner_hooks, spawner) == []


def test_tacc_deployment_target(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("tacc")
    spawner = _hook_spawner(fake_spawner)

    assert spawner_hooks.DEPLOYMENT_TARGET == 'tacc'


def test_designsafe_deployment_target(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("designsafe")
    spawner = _hook_spawner(fake_spawner)

    assert spawner_hooks.DEPLOYMENT_TARGET == 'designsafe'


def test_no_deployment_target(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("")
    spawner = _hook_spawner(fake_spawner)

    assert spawner_hooks.DEPLOYMENT_TARGET == ''


def test_user_has_no_configs(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("")
    spawner = _hook_spawner(fake_spawner)

    del spawner.configs
    with patch.object(spawner_hooks, "get_tenant_configs", return_value=NEW_CONFIGS) as get_configs:
        spawner_hooks.hook(spawner)

    get_configs.assert_called_once_with(restricted=False)
    assert spawner.configs == NEW_CONFIGS


def test_restricted_user_has_no_configs(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("")
    spawner = _hook_spawner(fake_spawner, ldap_groups=[f"cn={RESTRICTED_ID},ou=Groups,dc=tacc,dc=utexas,dc=edu"])

    del spawner.configs
    with patch.object(spawner_hooks, "get_tenant_configs", return_value=NEW_CONFIGS) as get_configs:
        spawner_hooks.hook(spawner)

    get_configs.assert_called_once_with(restricted=True)
    assert spawner.configs == NEW_CONFIGS


def test_user_with_configs_does_not_refetch(load_modules, fake_spawner):
    _, spawner_hooks = load_modules("")
    spawner = _hook_spawner(fake_spawner)

    with patch.object(spawner_hooks, "get_tenant_configs", return_value=NEW_CONFIGS) as get_configs:
        spawner_hooks.hook(spawner)

    get_configs.assert_not_called()
    assert spawner.configs == BASE_CONFIGS


@pytest.mark.parametrize("test_cpu_threads, expected_cpu_threads", [("1.5", "1"), ("0", "1"), ("2.5", "2"), ("5", "5")])
def test_num_threads(load_modules, fake_spawner, test_cpu_threads, expected_cpu_threads):
    _, spawner_hooks = load_modules("designsafe")
    spawner = _hook_spawner(fake_spawner)
    spawner.cpu_limit = test_cpu_threads
    assert(spawner_hooks.get_num_threads(spawner) == expected_cpu_threads)

