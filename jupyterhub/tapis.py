"""
Custom Authenticator to use Tapis OAuth with JupyterHub
"""

import json
import os
import re
import time
import urllib
import base64
import jwt

from jupyterhub.auth import LocalAuthenticator
from kubernetes import client
from tornado import gen, web
from tornado.auth import OAuth2Mixin
from tornado.httpclient import HTTPRequest, AsyncHTTPClient
from tornado.httputil import url_concat
from traitlets import Set

from jupyterhub.common import TENANT, INSTANCE, get_tenant_configs, safe_string, get_user_token_dir
from .oauth2 import OAuthLoginHandler, OAuthenticator

CONFIGS = get_tenant_configs()


class TapisMixin(OAuth2Mixin):
    _OAUTH_AUTHORIZE_URL = f"{CONFIGS.get('tapis_base_url').rstrip('/')}/oauth2/authorize"
    _OAUTH_ACCESS_TOKEN_URL = f"{CONFIGS.get('tapis_base_url').rstrip('/')}/oauth2/tokens"


class TapisLoginHandler(OAuthLoginHandler, TapisMixin):
    pass


class TapisOAuthenticator(OAuthenticator):
    login_service = CONFIGS.get("tapis_login_button_text")
    login_handler = TapisLoginHandler

    team_whitelist = Set(
        config=True,
        help="Automatically allow members of selected teams",
    )

    @gen.coroutine
    def authenticate(self, handler, data):
        code = handler.get_argument("code", False)

        if not code:
            raise web.HTTPError(400, "oauth callback made without a token")

        http_client = AsyncHTTPClient()

        params = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CONFIGS.get("oauth_callback_url"),
        }

        url = url_concat(
            f"{CONFIGS.get('tapis_base_url').rstrip('/')}/oauth2/tokens", params
        )

        credentials = (
            str(CONFIGS.get("tapis_client_id"))
            + str(":")
            + str(CONFIGS.get("tapis_client_key"))
        )
        cred_bytes = credentials.encode("ascii")
        cred_encoded = base64.b64encode(cred_bytes)
        cred_encoded_string = cred_encoded.decode("ascii")

        headers = {
            "Authorization": f"Basic {cred_encoded_string}",
            "Content-Type": "application/json",
        }

        req = HTTPRequest(
            url,
            method="POST",
            validate_cert=eval(CONFIGS.get("oauth_validate_cert")),
            body=json.dumps(params),
            headers=headers,
        )
        resp = yield http_client.fetch(req)

        resp_json = json.loads(resp.body)
        access_token = resp_json["result"]["access_token"]["access_token"]
        refresh_token = resp_json["result"]["refresh_token"]["refresh_token"]
        expires_in = resp_json["result"]["access_token"]["expires_in"]
        expires_at = resp_json["result"]["access_token"]["expires_at"]
        data = jwt.decode(access_token, options={"verify_signature": False})
        username = data["tapis/username"].lower()
        created_at = time.time()

        self.ensure_token_dir(username)
        self.save_token(
            access_token, refresh_token, username, created_at, expires_in, expires_at
        )
        return username

    def ensure_token_dir(self, username):
        try:
            os.makedirs(get_user_token_dir(username))
        except OSError as e:
            self.log.info(
                f"Got error trying to make token dir: {get_user_token_dir(username)} exception: {e}"
            )

    def save_token(
        self, access_token, refresh_token, username, created_at, expires_in, expires_at
    ):
        tenant_id = CONFIGS.get("tapis_tenant_id")
        # tapipy file
        d = [
            {
                "token": access_token,
                "refresh_token": refresh_token,
                "tenant_id": tenant_id,
                "api_key": CONFIGS.get("tapis_client_id"),
                "api_secret": CONFIGS.get("tapis_client_secret"),
                "api_server": CONFIGS.get("tapis_base_url").rstrip("/"),
                "verify": eval(CONFIGS.get("oauth_validate_cert")),
            }
        ]
        with open(os.path.join(get_user_token_dir(username), ".tapipy"), "w") as f:
            json.dump(d, f)
        self.create_configmap(username, ".tapipy", json.dumps(d))

        # cli file
        d = {
            "tenantid": tenant_id,
            "baseurl": CONFIGS.get("tapis_base_url").rstrip("/"),
            "devurl": "",
            "apikey": CONFIGS.get("tapis_client_id"),
            "username": username,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "created_at": str(int(created_at)),
            "apisecret": CONFIGS.get("tapis_client_secret"),
            "expires_in": str(expires_in),
            "expires_at": str(expires_at),
        }
        with open(os.path.join(get_user_token_dir(username), "current"), "w") as f:
            json.dump(d, f)
        self.create_configmap(username, "current", json.dumps(d))

    def create_configmap(self, username, name, d):
        with open("/run/secrets/kubernetes.io/serviceaccount/token") as f:
            token = f.read()
        with open("/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
            namespace = f.read()

        configuration = client.Configuration()
        configuration.api_key["authorization"] = f"Bearer {token}"
        configuration.host = "https://kubernetes.default"
        configuration.ssl_ca_cert = "/run/secrets/kubernetes.io/serviceaccount/ca.crt"

        api_instance = client.CoreV1Api(client.ApiClient(configuration))

        safe_username = safe_string(username).lower()
        safe_tenant = safe_string(TENANT).lower()
        safe_instance = safe_string(INSTANCE).lower()
        configmap_name_prefix = f"{safe_username}-{safe_tenant}-{safe_instance}-jhub"
        # remove the . from .agpy to accomodate k8 naming rules
        configmap_name = f"{configmap_name_prefix}-{re.sub('[^A-Za-z0-9]+', '', name)}"

        body = client.V1ConfigMap(
            data={name: str(d)},
            metadata={
                "name": configmap_name,
                "labels": {
                    "app": configmap_name_prefix,
                    "tenant": TENANT,
                    "instance": INSTANCE,
                    "username": username,
                },
            },
        )

        try:  # delete any current configmaps to ensure no stale tokens
            api_response = api_instance.delete_namespaced_config_map(
                configmap_name, namespace
            )
            print(str(api_response))
        except Exception as e:
            print(f"Exception when calling CoreV1Api->delete_namespaced_config_map: {e}\n")

        try:
            api_response = api_instance.create_namespaced_config_map(namespace, body)
            self.log.info(str(api_response))
        except Exception as e:
            self.log.info(f"Exception when calling CoreV1Api->create_namespaced_config_map: {e}\n")


class LocalTapisOAuthenticator(LocalAuthenticator, TapisOAuthenticator):
    """A version that mixes in local system user creation"""

    pass
