# jupyterhub

Spawner config (`common.py`, `spawner_hooks.py`, `tapis.py`, ...) deployed into
the JupyterHub image for TACC and DesignSafe (see `Dockerfile`). It runs against
live Tapis, TAS, and LDAP services inside a Kubernetes cluster, so it can't be
exercised end-to-end locally — instead the changed logic is covered by a local
unit test suite that mocks those services.

## Running the tests

```sh
uv sync
uv run pytest
```

`tests/conftest.py` registers `common.py`/`spawner_hooks.py` as `jupyterhub.common`
/ `jupyterhub.spawner_hooks` (mirroring how the Dockerfile drops them into the
installed `jupyterhub` package) and reloads them with the env vars needed for
either `DEPLOYMENT_TARGET=tacc` or `DEPLOYMENT_TARGET=designsafe`, so both
branches of the deployment-target logic can be tested in isolation.
