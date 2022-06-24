import os
import string
import sys
import json

from agavepy.agave import Agave
from tapipy.tapis import Tapis

INSTANCE = os.environ.get("INSTANCE")
TENANT = os.environ.get("TENANT")
tapis_service_token = os.environ.get("TAPIS_SERVICE_TOKEN")
base_url = os.environ.get("AGAVE_BASE_URL", "https://api.tacc.utexas.edu")
tapis_base_url = os.environ.get("TAPIS_BASE_URL", "https://tacc.tapis.io")
database = os.environ.get("TAPIS_DATABASE")
collection = os.environ.get("TAPIS_COLLECTION")

if not tapis_service_token:
    raise Exception("Missing TAPIS_SERVICE_TOKEN configuration.")


def get_config_metadata_name():
    return "config.{}.{}.jhub".format(TENANT, INSTANCE)


def get_tenant_configs():
    t = Tapis(base_url=tapis_base_url, jwt=tapis_service_token)
    q = {"name": get_config_metadata_name()}
    print("tenant query: {}".format(q))
    metadata = json.loads(
        t.meta.listDocuments(db=database, collection=collection, filter=json.dumps(q))
    )[0]["value"]
    return metadata


def get_user_configs(username):
    t = Tapis(base_url=tapis_base_url, jwt=tapis_service_token)
    q = {"value.user": username, "value.tenant": TENANT, "value.instance": INSTANCE}
    print("user query: {}".format(q))
    metadata = json.loads(
        t.meta.listDocuments(db=database, collection=collection, filter=json.dumps(q))
    )
    return metadata


def safe_string(
    to_escape, safe=set(string.ascii_lowercase + string.digits), escape_char="-"
):
    """Escape a string so that it only contains characters in a safe set.
    Characters outside the safe list will be escaped with _%x_,
    where %x is the hex value of the character.
    """

    chars = []
    for c in to_escape:
        if c in safe:
            chars.append(c)
        else:
            chars.append(_escape_char(c, escape_char))
    return u"".join(chars)


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
        buf.append("%X" % _ord(byte))
    return "".join(buf)
