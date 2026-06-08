import json
import logging
import os
import string
import sys
import time

import requests
from tapipy.tapis import Tapis

logger = logging.getLogger("JupyterHub")

# Detect which target we are deploying to
# Requires us to set this in our deployment yaml
DEPLOYMENT_TARGET = os.environ.get("DEPLOYMENT_TARGET", "").lower()

IS_TACC = DEPLOYMENT_TARGET == "tacc"
IS_DESIGNSAFE = DEPLOYMENT_TARGET == "designsafe"


INSTANCE = os.environ.get("INSTANCE")
TENANT = os.environ.get("TENANT")
RESTRICTED_ID = os.environ.get("RESTRICTED_ID", "66657")
RESTRICTED_LABEL = os.environ.get("RESTRICTED_LABEL", "hetdex")
tapis_service_token = os.environ.get("TAPIS_SERVICE_TOKEN")
portals_service_token = os.environ.get("PORTALS_SERVICE_TOKEN")
portals_base_url = os.environ.get("PORTALS_BASE_URL", "https://portals.tapis.io")
tapis_base_url = os.environ.get("TAPIS_BASE_URL", "https://tacc.tapis.io").rstrip()
meta_base_url = os.environ.get("META_BASE_URL", "https://tacc.tapis.io")
database = os.environ.get("TAPIS_DATABASE")
collection = os.environ.get("TAPIS_COLLECTION")

if not tapis_service_token:
    raise Exception("Missing TAPIS_SERVICE_TOKEN configuration.")

# Tenant specific environment cariables
projects_url = os.environ.get("PROJECTS_URL", "https://designsafe-ci.org")

if IS_TACC:
    RESTRICTED_ID = os.environ.get("RESTRICTED_ID", "66657")
    RESTRICTED_LABEL = os.environ.get("RESTRICTED_LABEL", "hetdex")
    portals_service_token = os.environ.get("PORTALS_SERVICE_TOKEN")
    portals_base_url = os.environ.get("PORTALS_BASE_URL", "https://portals.tapis.io")

if IS_DESIGNSAFE:
    tapis_base_url = tapis_base_url or "https://designsafe.tapis.io"


# Calls to the meta service to get configs related to the JupyterHub instance
# We also look for user specific configs (ie: if the user is in a group)

def get_metadata(t, q):
    try:
        response = json.loads(t.meta.listDocuments(db=database, collection=collection, filter=json.dumps(q)))
    except Exception as e:
        logger.error(f"Unable to get metadata, error: {e}")
        return None
    return response


def get_config_metadata_name(restricted):
    """Return name of config metadata"""
    return (
        f"config.{TENANT}.{INSTANCE}.jhub"
        if not restricted
        else f"config.{TENANT}.{INSTANCE}.restricted.jhub"
    )


def get_tenant_configs(restricted=False, retry=True):
    """Retrive tenant config from metadata"""
    t = Tapis(base_url=meta_base_url, jwt=tapis_service_token)
    q = {"name": get_config_metadata_name(restricted)}
    metadata = get_metadata(t, q)
    if not metadata:
        if retry:
            time.sleep(1)
            return get_tenant_configs(restricted, False)
        return None
    logger.error(f"Loaded tenant config: {metadata}")
    return metadata[0]["value"]


def get_user_configs(username, retry=True):
    """Retrieve any groups user belongs to"""
    t = Tapis(base_url=meta_base_url, jwt=tapis_service_token)
    q = {"value.user": username, "value.tenant": TENANT, "value.instance": INSTANCE}
    metadata = get_metadata(t, q)
    if not metadata:
        if retry:
            time.sleep(1)
            return get_user_configs(username, False)
    return metadata


# Functions that manage the users access token

def refresh_access_token(refresh_token, username):
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


def get_user_token_dir(username):
    return os.path.join("/tapis/jupyter/tokens", INSTANCE, TENANT, username)


def save_token(
    access_token, refresh_token, username, created_at, expires_in, expires_at
):
    try:
        configs = get_tenant_configs()
        tenant_id = configs.get("tapis_tenant_id")

        # tapipy file
        d = [
            {
                "token": access_token,
                "refresh_token": refresh_token,
                "tenant_id": tenant_id,
                "api_key": configs.get("tapis_client_id"),
                "api_secret": configs.get("tapis_client_secret"),
                "api_server": "{}".format(configs.get("tapis_base_url").rstrip("/")),
                "verify": eval(configs.get("oauth_validate_cert")),
            }
        ]
        with open(os.path.join(get_user_token_dir(username), ".tapipy"), "w") as f:
            json.dump(d, f)

        # CLI file
        cli_data = {
            "tenantid": tenant_id,
            "baseurl": "{}".format(configs.get("tapis_base_url").rstrip("/")),
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

def safe_string(to_escape, safe=None, escape_char="-"):
    """Escape a string so that it only contains characters in a safe set.
    Characters outside the safe list will be escaped with _%x_,
    where %x is the hex value of the character.
    """
    if safe is None:
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
