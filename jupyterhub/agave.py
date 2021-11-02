"""
Custom Authenticator to use Agave OAuth with JupyterHub
"""

import json
import os
import re
import time
import urllib

from jupyterhub.auth import LocalAuthenticator
from kubernetes import client
from tornado import gen, web
from tornado.auth import OAuth2Mixin
from tornado.httpclient import HTTPRequest, AsyncHTTPClient
from tornado.httputil import url_concat
from traitlets import Set

from jupyterhub.common import TENANT, INSTANCE, get_tenant_configs, safe_string
from .oauth2 import OAuthLoginHandler, OAuthenticator

CONFIGS = get_tenant_configs()

class AgaveMixin(OAuth2Mixin):
    _OAUTH_AUTHORIZE_URL = "{}/oauth2/authorize".format(CONFIGS.get('agave_base_url').rstrip('/'))
    _OAUTH_ACCESS_TOKEN_URL = "{}/token".format(CONFIGS.get('agave_base_url').rstrip('/'))


class AgaveLoginHandler(OAuthLoginHandler, AgaveMixin):
    pass


class AgaveOAuthenticator(OAuthenticator):
    login_service = CONFIGS.get('agave_login_button_text')
    login_handler = AgaveLoginHandler

    team_whitelist = Set(
        config=True,
        help="Automatically whitelist members of selected teams",
    )

    @gen.coroutine
    def authenticate(self, handler, data):
        self.log.info('data', data)
        code = handler.get_argument("code", False)
        if not code:
            raise web.HTTPError(400, "oauth callback made without a token")

        http_client = AsyncHTTPClient()

        params = dict(
            grant_type="authorization_code",
            code=code,
            redirect_uri=CONFIGS.get('oauth_callback_url'),
            client_id=CONFIGS.get('agave_client_id'),
            client_secret=CONFIGS.get('agave_client_secret')
        )

        url = url_concat(
            "{}/oauth2/token".format(CONFIGS.get('agave_base_url').rstrip('/')), params)
        self.log.info(url)
        self.log.info(params)
        bb_header = {"Content-Type":
                     "application/x-www-form-urlencoded;charset=utf-8"}
        req = HTTPRequest(url,
                          method="POST",
                          validate_cert=eval(CONFIGS.get('oauth_validate_cert')),
                          body=urllib.parse.urlencode(params).encode('utf-8'),
                          headers=bb_header
                          )
        resp = yield http_client.fetch(req)
        resp_json = json.loads(resp.body.decode('utf8', 'replace'))

        access_token = resp_json['access_token']
        refresh_token = resp_json['refresh_token']
        expires_in = resp_json['expires_in']
        try:
            expires_in = int(expires_in)
        except ValueError:
            expires_in = 3600
        created_at = time.time()
        expires_at = time.ctime(created_at + expires_in)
        self.log.info(str(resp_json))
        # Determine who the logged in user is
        headers = {"Accept": "application/json",
                   "User-Agent": "JupyterHub",
                   "Authorization": "Bearer {}".format(access_token)
                   }
        req = HTTPRequest("{}/profiles/v2/me".format(CONFIGS.get('agave_base_url').rstrip('/')),
                          validate_cert=eval(CONFIGS.get('oauth_validate_cert')),
                          method="GET",
                          headers=headers
                          )
        resp = yield http_client.fetch(req)
        resp_json = json.loads(resp.body.decode('utf8', 'replace'))
        self.log.info('resp_json after /profiles/v2/me:', str(resp_json))
        username = resp_json["result"]["username"]

        self.ensure_token_dir(username)
        self.save_token(access_token, refresh_token, username, created_at, expires_in, expires_at)
        return username

    def ensure_token_dir(self, username):
        try:
            os.makedirs(self.get_user_token_dir(username))
        except OSError as e:
            self.log.info("Got error trying to make token dir: "
                          "{} exception: {}".format(self.get_user_token_dir(username), e))

    def get_user_token_dir(self, username):
        return os.path.join(
            '/agave/jupyter/tokens',
            INSTANCE,
            TENANT,
            username)

    def save_token(self, access_token, refresh_token, username, created_at, expires_in, expires_at):
        tenant_id = CONFIGS.get('agave_tenant_id')
        # agavepy file
        d = [{'token': access_token,
              'refresh_token': refresh_token,
              'tenant_id': tenant_id,
              'api_key': CONFIGS.get('agave_client_id'),
              'api_secret': CONFIGS.get('agave_client_secret'),
              'api_server': '{}'.format(CONFIGS.get('agave_base_url').rstrip('/')),
              'verify': eval(CONFIGS.get('oauth_validate_cert')),
              }]
        with open(os.path.join(self.get_user_token_dir(username), '.agpy'), 'w') as f:
            json.dump(d, f)
        self.log.info("Saved agavepy cache file to {}".format(os.path.join(self.get_user_token_dir(username), '.agpy')))
        self.log.info("agavepy cache file data: {}".format(d))
        self.create_configmap(username, '.agpy', json.dumps(d))

        # cli file
        d = {'tenantid': tenant_id,
             'baseurl': '{}'.format(CONFIGS.get('agave_base_url').rstrip('/')),
             'devurl': '',
             'apikey': CONFIGS.get('agave_client_id'),
             'username': username,
             'access_token': access_token,
             'refresh_token': refresh_token,
             'created_at': str(int(created_at)),
             'apisecret': CONFIGS.get('agave_client_secret'),
             'expires_in': str(expires_in),
             'expires_at': str(expires_at)
             }
        with open(os.path.join(self.get_user_token_dir(username), 'current'), 'w') as f:
            json.dump(d, f)
        self.log.info("Saved CLI cache file to {}".format(os.path.join(self.get_user_token_dir(username), 'current')))
        self.log.info("CLI cache file data: {}".format(d))
        self.create_configmap(username, 'current', json.dumps(d))

    def create_configmap(self, username, name, d):
        with open('/run/secrets/kubernetes.io/serviceaccount/token') as f:
            token = f.read()
        with open('/run/secrets/kubernetes.io/serviceaccount/namespace') as f:
            namespace = f.read()

        configuration = client.Configuration()
        configuration.api_key['authorization'] = 'Bearer {}'.format(token)
        configuration.host = 'https://kubernetes.default'
        configuration.ssl_ca_cert = '/run/secrets/kubernetes.io/serviceaccount/ca.crt'

        api_instance = client.CoreV1Api(client.ApiClient(configuration))

        safe_username = safe_string(username).lower()
        safe_tenant = safe_string(TENANT).lower()
        safe_instance = safe_string(INSTANCE).lower()
        configmap_name_prefix = '{}-{}-{}-jhub'.format(safe_username, safe_tenant, safe_instance)
        configmap_name = '{}-{}'.format(configmap_name_prefix, re.sub('[^A-Za-z0-9]+', '', name))  # remove the . from .agpy to accomodate k8 naming rules

        body = client.V1ConfigMap(
            data={name: str(d)},
            metadata={
                'name': configmap_name,
                'labels': {'app': configmap_name_prefix, 'tenant': TENANT, 'instance': INSTANCE, 'username': username}
            }
        )

        self.log.info('{}:{}'.format('configmap body', body))

        try: # delete any current configmaps to ensure no stale tokens
            api_response = api_instance.delete_namespaced_config_map(configmap_name, namespace)
            self.log.info('{} configmap deleted'.format(configmap_name))
            print(str(api_response))
        except Exception as e:
            print("Exception when calling CoreV1Api->delete_namespaced_config_map: %s\n" % e)

        try:
            api_response = api_instance.create_namespaced_config_map(namespace, body)
            self.log.info('{} configmap created'.format(name))
            print(str(api_response))
        except Exception as e:
            print("Exception when calling CoreV1Api->create_namespaced_config_map: %s\n" % e)


class LocalAgaveOAuthenticator(LocalAuthenticator, AgaveOAuthenticator):
    """A version that mixes in local system user creation"""
    pass
