import os
import string
import sys

from agavepy.agave import Agave

INSTANCE = os.environ.get('INSTANCE')
TENANT = os.environ.get('TENANT')
service_token = os.environ.get('AGAVE_SERVICE_TOKEN')
base_url = os.environ.get('AGAVE_BASE_URL', "https://api.tacc.utexas.edu")

if not service_token:
    raise Exception("Missing SERVICE_TOKEN configuration.")


def get_config_metadata_name():
    return 'config.{}.{}.jhub'.format(TENANT, INSTANCE)


def get_tenant_configs():
    ag = Agave(api_server=base_url, token=service_token)
    q = {'name': get_config_metadata_name()}
    print('tenant query: {}'.format(q))
    return ag.meta.listMetadata(q=str(q))[0]['value']

def get_user_configs(username):
    ag = Agave(api_server=base_url, token=service_token)
    q = {'value.user': username, 'value.tenant': TENANT, 'value.instance': INSTANCE}
    print('user query: {}'.format(q))
    return ag.meta.listMetadata(q=str(q))

def safe_string(to_escape, safe = set(string.ascii_lowercase + string.digits), escape_char='-'):
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
    return u''.join(chars)


if sys.version_info >= (3,):
    _ord = lambda byte: byte
else:
    _ord = ord


def _escape_char(c, escape_char):
    """Escape a single character"""
    buf = []
    for byte in c.encode('utf8'):
        buf.append(escape_char)
        buf.append('%X' % _ord(byte))
    return ''.join(buf)
