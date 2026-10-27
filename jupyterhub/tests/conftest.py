import importlib
import logging
import sys
import types
from pathlib import Path

import ldap3
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ENV = {
    "TAPIS_SERVICE_TOKEN": "test-service-token",
    "INSTANCE": "test-instance",
    "TENANT": "test-tenant",
    "TAPIS_DATABASE": "test-database",
    "TAPIS_COLLECTION": "test-collection",
}


@pytest.fixture(autouse=True)
def block_real_ldap(monkeypatch):
    def _connection(*args, **kwargs):
        pytest.fail("search_ldap tried to open a real LDAP connection; patch spawner_hooks.search_ldap in this test")

    monkeypatch.setattr(ldap3, "Connection", _connection)


@pytest.fixture
def load_modules(monkeypatch):
    """Return a function that (re)loads common/spawner_hooks for a deployment target.

    Usage: common, spawner_hooks = load_modules("tacc", EXTRA_VAR="value")
    """

    def _load(deployment_target="", **extra_env):
        env = {**DEFAULT_ENV, "DEPLOYMENT_TARGET": deployment_target, **extra_env}
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        for name in ("jupyterhub", "jupyterhub.common", "jupyterhub.spawner_hooks"):
            sys.modules.pop(name, None)

        package = types.ModuleType("jupyterhub")
        package.__path__ = [str(REPO_ROOT)]
        sys.modules["jupyterhub"] = package

        common = importlib.import_module("jupyterhub.common")
        spawner_hooks = importlib.import_module("jupyterhub.spawner_hooks")
        return common, spawner_hooks

    yield _load

    for name in ("jupyterhub", "jupyterhub.common", "jupyterhub.spawner_hooks"):
        sys.modules.pop(name, None)


class FakeUser:
    def __init__(self, name):
        self.name = name


class FakeSpawner:
    """Minimal stand-in for KubeSpawner exposing only what hook() touches."""

    def __init__(self, username="testuser", configs=None, user_configs=None, user_options=None):
        self.user = FakeUser(username)
        self.log = logging.getLogger("test_spawner")
        self.configs = configs if configs is not None else {}
        self.user_configs = user_configs if user_configs is not None else []
        self.user_options = user_options if user_options is not None else {}


@pytest.fixture
def fake_spawner():
    return FakeSpawner
