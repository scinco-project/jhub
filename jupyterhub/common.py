import json
import logging
import os
import string
import sys
import time

import requests
from tapipy.tapis import Tapis
from tenacity import retry, retry_if_result, stop_after_attempt, wait_fixed, RetryCallState

logger = logging.getLogger("JupyterHub")

# Detect which target we are deploying to
# Requires us to set this in our deployment yaml
DEPLOYMENT_TARGET = os.environ.get("DEPLOYMENT_TARGET", "").lower()

DEPLOYMENTS = {
    "tacc": {
        "RESTRICTED_ID": "66657",
        "RESTRICTED_LABEL": "hetdex",
        "PORTALS_BASE_URL": "https://portals.tapis.io",
        "TAPIS_BASE_URL": "https://tacc.tapis.io",
        "JUPYTER_HOME": "/home/jovyan",
    },
    "designsafe": {
        "TAPIS_BASE_URL": "https://designsafe.tapis.io",
        "JUPYTER_HOME": "/home/jupyter",
    },
}
deployment_defaults = DEPLOYMENTS.get(DEPLOYMENT_TARGET, {})

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise Exception(f"Missing {name} configuration.")
    return value


INSTANCE = _require_env("INSTANCE")
TENANT = _require_env("TENANT")
tapis_service_token = _require_env("TAPIS_SERVICE_TOKEN")
RESTRICTED_ID = os.environ.get("RESTRICTED_ID", deployment_defaults.get("RESTRICTED_ID", ""))
RESTRICTED_LABEL = os.environ.get("RESTRICTED_LABEL", deployment_defaults.get("RESTRICTED_LABEL", ""))
portals_service_token = os.environ.get("PORTALS_SERVICE_TOKEN")
portals_base_url = os.environ.get(
    "PORTALS_BASE_URL", deployment_defaults.get("PORTALS_BASE_URL", "https://portals.tapis.io")
)
tapis_base_url = (
    os.environ.get("TAPIS_BASE_URL") or deployment_defaults.get("TAPIS_BASE_URL", "https://tacc.tapis.io")
).rstrip()
meta_base_url = os.environ.get("META_BASE_URL", "https://tacc.tapis.io")
jupyter_home = deployment_defaults.get("JUPYTER_HOME", "/home/jovyan")
database = os.environ.get("TAPIS_DATABASE")
collection = os.environ.get("TAPIS_COLLECTION")
retry_attempts = int(os.environ.get("RETRY_ATTEMPTS", 3))
retry_wait = int(os.environ.get("RETRY_WAIT", 1))

# Tenant specific environment cariables
projects_url = os.environ.get("PROJECTS_URL", "https://designsafe-ci.org")


# Calls to the meta service to get configs related to the JupyterHub instance
# We also look for user specific configs (ie: if the user is in a group)

def get_metadata(t: Tapis, q: dict) -> dict | None:
    try:
        # no static type info exists for tapipy, ignoring
        response = json.loads(t.meta.listDocuments(db=database, collection=collection, filter=json.dumps(q)))  # pyright: ignore[reportAttributeAccessIssue]
    except Exception as e:
        logger.error(f"Unable to get metadata, error: {e}")
        return None
    return response


def get_config_metadata_name(restricted: bool) -> str:
    """Return name of config metadata"""
    return (
        f"config.{TENANT}.{INSTANCE}.jhub"
        if not restricted
        else f"config.{TENANT}.{INSTANCE}.restricted.jhub"
    )


def _return_none(retry_state: RetryCallState) -> None:
    return None


def _log_retry(retry_state: RetryCallState) -> None:
    fn_name = retry_state.fn.__name__ if retry_state.fn else "some metadata call"
    logger.warning(
        f"Retrying {fn_name}, attempt {retry_state.attempt_number}"
    )


@retry(
    retry=retry_if_result(lambda metadata: not metadata),
    stop=stop_after_attempt(retry_attempts),
    wait=wait_fixed(retry_wait),
    retry_error_callback=_return_none,
    before_sleep=_log_retry,
)
def get_tenant_configs(restricted: bool = False) -> dict:
    """Retrive tenant config from metadata"""
    t = Tapis(base_url=meta_base_url, jwt=tapis_service_token)
    q = {"name": get_config_metadata_name(restricted)}
    metadata = get_metadata(t, q)
    if not metadata:
        return {}
    logger.debug(f"Loaded tenant config: {metadata}")
    return metadata[0]["value"]


@retry(
    retry=retry_if_result(lambda metadata: not metadata),
    stop=stop_after_attempt(retry_attempts),
    wait=wait_fixed(retry_wait),
    retry_error_callback=_return_none,
    before_sleep=_log_retry,
)
def get_user_configs(username: str) -> dict | None:
    """Retrieve any groups user belongs to"""
    t = Tapis(base_url=meta_base_url, jwt=tapis_service_token)
    q = {"value.user": username, "value.tenant": TENANT, "value.instance": INSTANCE}
    metadata = get_metadata(t, q)
    logger.debug(f"Loaded user configs: {metadata}")
    return metadata


# Functions that manage the users access token

def refresh_access_token(refresh_token: str, username: str) -> dict | None:
    logger.info(f"Refreshing access token for user {username}")

    try:
        data = {
            "refresh_token": refresh_token,
        }
        res = requests.put(f"{tapis_base_url}/v3/tokens", json=data)
        logger.debug(f"Token refresh response: {res}")
        resp_data = res.json()
        logger.debug(f"Token refresh data: {resp_data}")
        new_access_token = resp_data["result"]["access_token"]["access_token"]
        refresh_token = resp_data["result"]["refresh_token"]["refresh_token"]

        expires_in = resp_data["result"]["access_token"]["expires_in"]
        expires_at = resp_data["result"]["access_token"]["expires_at"]
        return {
            "access_token": new_access_token,
            "refresh_token": refresh_token,
            "created_at": time.time(),
            "expires_in": expires_in,
            "expires_at": expires_at,
        }
    except Exception as e:
        logger.error(f"Unable to refresh access token for {username}, error: {e}")
        return None


def get_user_token_dir(username: str) -> str:
    return os.path.join("/tapis/jupyter/tokens", INSTANCE, TENANT, username)


def save_token(
    access_token: str,
    refresh_token: str,
    username: str,
    created_at: str,
    expires_in: str,
    expires_at: str
) -> None:
    try:
        configs = get_tenant_configs()

        if not configs:
            raise ValueError("Missing tenant configs")

        tenant_id = configs.get("tapis_tenant_id")
        configs_base_url = configs.get("tapis_base_url")
        oauth_validate_cert = configs.get("oauth_validate_cert")
        if not configs_base_url or oauth_validate_cert is None:
            raise ValueError("Missing tapis_base_url or oauth_validate_cert in tenant configs")
        configs_base_url = configs_base_url.rstrip("/")

        # tapipy file
        d = [
            {
                "token": access_token,
                "refresh_token": refresh_token,
                "tenant_id": tenant_id,
                "api_key": configs.get("tapis_client_id"),
                "api_secret": configs.get("tapis_client_secret"),
                "api_server": configs_base_url,
                "verify": oauth_validate_cert,
            }
        ]
        with open(os.path.join(get_user_token_dir(username), ".tapipy"), "w") as f:
            json.dump(d, f)

        # CLI file
        cli_data = {
            "tenantid": tenant_id,
            "baseurl": configs_base_url,
            "devurl": "",
            "apikey": configs.get("tapis_client_id"),
            "username": username,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "created_at": str(int(created_at)),
            "apisecret": configs.get("tapis_client_secret"),
            "expires_in": str(expires_in),
            "expires_at": str(expires_at),
        }
        with open(os.path.join(get_user_token_dir(username), "current"), "w") as f:
            json.dump(cli_data, f)
    except Exception as e:
        logger.error(f"Unable to save CLI cache file for {username}, error: {e}")


# String utilities

def safe_string(to_escape: str, safe: set[str] = set(), escape_char: str = "-") -> str:
    """Escape a string so that it only contains characters in a safe set.
    Characters outside the safe list will be escaped with _%x_,
    where %x is the hex value of the character.
    """
    if not safe:
        safe = set(string.ascii_lowercase + string.digits)
    chars = []
    for c in to_escape:
        if c in safe:
            chars.append(c)
        else:
            chars.append(_escape_char(c, escape_char))
    return "".join(chars)


if sys.version_info >= (3,):

    def _ord(byte):
        return byte

else:
    _ord = ord


def _escape_char(c, escape_char):
    """Escape a single character"""
    buf = []
    for byte in c.encode("utf8"):
        buf.append(escape_char)
        buf.append(f"{_ord(byte)}")
    return "".join(buf)
