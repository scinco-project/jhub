import os
import string
import sys
import json

from tapipy.tapis import Tapis

INSTANCE = os.environ.get("INSTANCE")
TENANT = os.environ.get("TENANT")
tapis_service_token = os.environ.get("TAPIS_SERVICE_TOKEN")
base_url = os.environ.get("AGAVE_BASE_URL", "https://api.tacc.utexas.edu")
tapis_base_url = os.environ.get("TAPIS_BASE_URL", "https://tacc.tapis.io")
v2_token_url = os.environ.get("V2_TOKEN_URL", "https://tacc.develop.tapis.io/v3/oauth2/v2/token")
database = os.environ.get("TAPIS_DATABASE")
collection = os.environ.get("TAPIS_COLLECTION")

if not tapis_service_token:
    raise Exception("Missing TAPIS_SERVICE_TOKEN configuration.")


def get_config_metadata_name():
    """Return name of config metadata"""
    return f"config.{TENANT}.{INSTANCE}.jhub"


def get_tenant_configs():
    """Retrive tenant config from metadata"""
    t = Tapis(base_url=tapis_base_url, jwt=tapis_service_token)
    q = {"name": get_config_metadata_name()}
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


def safe_string(
    to_escape, safe=None, escape_char="-"
):
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
