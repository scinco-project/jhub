"""
Minimal local JupyterHub config for exercising the Hub UI / login / spawn flow
without Tapis, TAS, LDAP, or Kubernetes. Not used by the real deployment
(see jupyterhub_config.py / Dockerfile for that) -- run with:

    cd local-dev
    uv run jupyterhub -f jupyterhub_config.local.py

Log in with any username and the password set below.
"""
import os

here = os.path.dirname(__file__)
data_dir = os.path.join(here, "jupyterhub_local_data")
os.makedirs(data_dir, exist_ok=True)

c.JupyterHub.ip = "127.0.0.1"
c.JupyterHub.port = 8000

c.JupyterHub.authenticator_class = "dummy"
c.DummyAuthenticator.password = "local"
c.Authenticator.allow_all = True

c.JupyterHub.spawner_class = "jupyterhub.spawner.LocalProcessSpawner"
c.Spawner.cmd = [os.path.join(here, ".venv", "bin", "jupyterhub-singleuser")]

# c.JupyterHub.db_url = f"sqlite:///{os.path.join(data_dir, 'jupyterhub.sqlite')}"
c.JupyterHub.db_url = "postgresql://gcurbelo@localhost:5432/jupyterhub"
c.JupyterHub.cookie_secret_file = os.path.join(data_dir, "jupyterhub_cookie_secret")

c.ConfigurableHTTPProxy.command = [os.path.join(here, "node_modules", ".bin", "configurable-http-proxy")]
