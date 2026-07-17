# jupyterhub

Spawner config (`common.py`, `spawner_hooks.py`, `tapis.py`, ...) deployed into
the JupyterHub image for TACC and DesignSafe (see `Dockerfile`). It runs against
live Tapis, TAS, and LDAP services inside a Kubernetes cluster, so it can't be
exercised end-to-end locally.

- Changed logic in `common.py` / `spawner_hooks.py` is covered by a local unit
  test suite that mocks those services -- see `tests/README.md`.
- The Hub UI / login / spawn flow itself (proxy, auth, single-user server
  lifecycle) can be exercised locally with a minimal, Tapis/TAS/LDAP/Kubernetes-free
  config.

## Local dev Hub (`local-dev/`)

`local-dev/jupyterhub_config.local.py` runs a real JupyterHub locally with:

- `DummyAuthenticator` instead of `TapisOAuthenticator` -- log in with any
  username and the password set in the config..
- `LocalProcessSpawner` instead of `KubeSpawner` -- spawns a real
  `jupyterhub-singleuser` process on your machine instead of a pod, so no
  Kubernetes cluster is needed. This requires the JupyterHub username to match
  a real local OS user (it does a `getpwnam` lookup), so log in with your
  actual machine username.
- None of `common.py` / `spawner_hooks.py` / `tapis.py` are loaded.

Everything for this is self-contained under `local-dev/` and gitignored except
for the `jupyterhub_config_local.py`, `pyproject.toml`, and `uv.lock`.

### Prerequisites

- [`uv`](https://docs.astral.sh/uv/)
- Node/npm (for `configurable-http-proxy`, JupyterHub's default proxy)
- A local Postgres server running, with a `jupyterhub` database created and
  reachable without a password as your local user, e.g.:

  ```sh
  brew services start postgresql@16
  createdb jupyterhub
  ```

  (Adjust `c.JupyterHub.db_url` in `jupyterhub_config.local.py` if your setup
  differs -- e.g. swap back to the commented-out `sqlite:///...` line to avoid
  Postgres entirely.)

### Setup

```sh
cd local-dev
npm install
uv sync
```

### Run

```sh
cd local-dev
uv run jupyterhub -f jupyterhub_config.local.py
```

Then open http://127.0.0.1:8000 and log in with your local OS username and
the password from `jupyterhub_config.local.py` (`local` by default).

### Stop / reset

```sh
pkill -f "jupyterhub -f jupyterhub_config.local.py"

# reset Hub state (cookie secret, sqlite db if used)
rm -rf local-dev/jupyterhub_local_data/
```

To reset the Postgres-backed state instead, drop and recreate the `jupyterhub`
database.
