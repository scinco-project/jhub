import os
import string
import sys
import json
import requests
import time

from tapipy.tapis import Tapis

INSTANCE = os.environ.get("INSTANCE")
TENANT = os.environ.get("TENANT")
RESTRICTED_ID = os.environ.get("RESTRICTED_ID", "66657")
RESTRICTED_LABEL = os.environ.get("RESTRICTED_LABEL", "hetdex")
tapis_service_token = os.environ.get("TAPIS_SERVICE_TOKEN")
tapis_base_url = os.environ.get("TAPIS_BASE_URL", "https://tacc.tapis.io")
database = os.environ.get("TAPIS_DATABASE")
collection = os.environ.get("TAPIS_COLLECTION")


if not tapis_service_token:
    raise Exception("Missing TAPIS_SERVICE_TOKEN configuration.")


def get_config_metadata_name(restricted):
    """Return name of config metadata"""
    return (
        f"config.{TENANT}.{INSTANCE}.jhub"
        if not restricted
        else f"config.{TENANT}.{INSTANCE}.restricted.jhub"
    )


def get_tenant_configs(restricted=False):
    """Retrive tenant config from metadata"""
    t = Tapis(base_url=tapis_base_url, jwt=tapis_service_token)
    q = {"name": get_config_metadata_name(restricted)}
    print(f"tenant query: {q}")
    metadata = json.loads(
        t.meta.listDocuments(db=database, collection=collection, filter=json.dumps(q))
    )[0]["value"]
    return metadata


def get_user_configs(username):
    """Retrieve any groups user belongs to"""
    t = Tapis(base_url=tapis_base_url, jwt=tapis_service_token)
    q = {"value.user": username, "value.tenant": TENANT, "value.instance": INSTANCE}
    print(f"user query: {q}")
    metadata = json.loads(
        t.meta.listDocuments(db=database, collection=collection, filter=json.dumps(q))
    )
    return metadata


def refresh_access_token(refresh_token, username):
    print("In refresh function")
    try:
        data = {
            "refresh_token": refresh_token,
        }
        res = requests.put("https://tacc.tapis.io/v3/tokens", json=data)
        print(res)
        resp_data = res.json()
        print(resp_data)
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
        print(f"Unable to refresh access token for {username}, error: {e}")


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
        print(
            "Saved tapipy cache file to {}".format(
                os.path.join(get_user_token_dir(username), ".tapipy")
            )
        )
        print(f"tapipy cache file data: {d}")

        # cli file
        d = {
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
            json.dump(d, f)
        print(
            f"Saved CLI cache file to {os.path.join(get_user_token_dir(username), 'current')}"
        )
    except Exception as e:
        print(f"Unable to save CLI cache file for {username}, error: {e}")


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
