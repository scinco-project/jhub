import ast
import json
import os
import re
import time
from typing import Any

import certifi
import humanfriendly
import jwt
import requests
import urllib3
from requests.auth import HTTPBasicAuth

from .common import (
    DEPLOYMENT_TARGET,
    INSTANCE,
    IS_DESIGNSAFE,
    IS_TACC,
    IS_TRAINING,
    RESTRICTED_ID,
    RESTRICTED_LABEL,
    TENANT,
    get_tenant_configs,
    get_user_configs,
    jupyter_home,
    refresh_access_token,
    safe_string,
    save_token,
    tapis_base_url,
    projects_url,
    tapis_service_token
)

from ldap3 import SAFE_SYNC, Connection, Server
from tornado import web

# TAS configuration:
# base URL for TAS API.
TAS_URL_BASE = os.environ.get("TAS_URL_BASE", "https://tas.tacc.utexas.edu/api/v1")
TAS_ROLE_ACCT = os.environ.get("TAS_ROLE_ACCT", "tas-jetstream")
TAS_ROLE_PASS = os.environ.get("TAS_ROLE_PASS")

LDAP_PASS = os.environ.get("LDAP_PASS")

# Extra setup steps to run (in order) for a given deployment, after the
# shared spawner setup below. Names are resolved at call time via globals()
# so tests can still patch these functions by name.
DEPLOYMENT_HOOKS = {
    "designsafe": ["is_user_allowed", "apply_restricted_allocation", "get_tapis_access_data", "get_tas_data", "get_all_configs", "set_selected_image", "set_cpu_mem_limits", "set_spawner_env", "update_ds_env", "get_mounts", "get_licenses", "get_ds_projects"],
    "tacc": ["is_user_allowed", "apply_restricted_allocation", "get_tapis_access_data", "get_tas_data", "get_all_configs", "set_selected_image", "set_cpu_mem_limits", "set_spawner_env", "get_mounts"],
    "training": ["apply_training_uid_gid", "get_mounts"],
}


# Main configuration hook for the KubeSpawner

def hook(spawner: Any) -> None:
    """Sets up the user's notebook server."""
    spawner.log.info("In main hook function")
    spawner.start_timeout = 60 * 5
    spawner.log.info(f"👻 tenant configs 👻 {spawner.configs}")
    spawner.log.info(f"👽 user configs 👽 {spawner.user_configs}")
    spawner.log.info(f"😱 user options (from form) 😱 {spawner.user_options}")

    for hook_name in DEPLOYMENT_HOOKS.get(DEPLOYMENT_TARGET, []):
        globals()[hook_name](spawner)


def merge_configs(x: dict, y: dict) -> dict:
    """Deep-merge dict x into dict y, combining lists and dicts."""
    merged = {**y}
    for key, value in x.items():
        if key in merged:
            if isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = merged[key] + value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        else:
            merged[key] = value
    return merged


def get_tas_user_projects(spawner: Any) -> dict:
    """
    Retrieve user projects from TAS
    """
    try:
        user = spawner.user.name
        http_headers = urllib3.make_headers(basic_auth=f"{TAS_ROLE_ACCT}:{TAS_ROLE_PASS}")
        pool_manager = urllib3.PoolManager(
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(),
            retries=False,
            headers=http_headers,
        )
        response = pool_manager.request("GET", f"{TAS_URL_BASE}/projects/username/{user}")
        spawner.log.info(f"{TAS_URL_BASE}/projects/username/{user}")
        json_response = json.loads(response.data.decode("utf-8"))
        spawner.log.info(f"TAS Projects for {user}: {json_response}")
        return json_response
    except Exception:
        return {}


def is_user_allowed(spawner: Any) -> None:
    """
    A user is allowed if they have any allocation.
    
    Check response from TAS to check for any allocation
    Should already have been caught, but double checking doesn't hurt
    """
    user = spawner.user.name
    spawner.log.info(f"Check if user has any allocation: {user}")
    allowed = bool(spawner.tas_data.get("result"))
    if not allowed:
        spawner.log.error(f"UNAUTHORIZED USER: {spawner.user.name} ATTEMPTING TO ACCESS JUPYTERHUB")
        raise web.HTTPError(403)


def is_user_restricted(spawner: Any) -> bool:
    """
    If the user is only in the restricted HETDEX project,
    they are given the restricted user configs.
    """
    user = spawner.user.name
    spawner.log.info(f"Check tas for restricted project for user: {user}")
    results = spawner.tas_data.get("result", [])
    if results and len(results) == 1:
        item_id = results[0].get("id")
        if item_id is not None and str(item_id) == RESTRICTED_ID and IS_TACC:
            spawner.log.info(f"Found restricted project for user: {user}")
            spawner.extra_labels = {"restrictedProject": RESTRICTED_LABEL}
            return True
    return False


def apply_restricted_allocation(spawner: Any) -> None:
    """TACC-only: if the user's only allocation is the restricted project,
    switch spawner.configs/user_configs to the restricted metadata group.
    
    Will also check for DS and raise 403, because we don't support a restricted
    DesignSafe JupyterHub, so restricted accounts should be booted.
    """
    restricted = is_user_restricted(spawner)
    spawner.log.info(f"Restricted? {restricted}")

    if not IS_TACC and restricted:
        raise web.HTTPError(403)
    if not IS_TACC:
        return

    if restricted:
        spawner.configs = get_tenant_configs(restricted)
        spawner.log.info(f"spawner configs: {spawner.configs}")
        spawner.user_configs = get_user_configs(spawner.user.name)
        spawner.log.info(f"spawner user configs: {spawner.user_configs}")


def apply_training_uid_gid(spawner: Any) -> None:
    """Training instances run every user under uid/gid 100."""
    spawner.uid = 100
    spawner.gid = 100


def get_tenant_configs_for_user(spawner: Any) -> dict:
    """TACC-only: fetch tenant configs, respecting the restricted-allocation
    override. Other deployments always get the unrestricted configs."""
    return get_tenant_configs(restricted=is_user_restricted(spawner))


async def get_notebook_options(spawner: Any) -> str | None:
    """Determine which images should be shown to the user to select."""
    spawner.tas_data = get_tas_user_projects(spawner)
    is_user_allowed(spawner)

    spawner.configs = get_tenant_configs_for_user(spawner)

    spawner.log.info(f"spawner configs: {spawner.configs}")
    spawner.user_configs = get_user_configs(spawner.user.name)
    spawner.log.info(f"spawner user configs: {spawner.user_configs}")

    image_options = spawner.configs.get("images", [])

    if spawner.user_configs:
        for item in spawner.user_configs:
            if isinstance(item, dict) and "value" in item:
                images = item["value"].get("images")
                if isinstance(images, list):
                    for image in images:
                        if image not in image_options:
                            image_options += [image]

    image_options = sorted(image_options, key=lambda d: d["display_name"])

    if len(image_options) > 1:
        options = ""
        for image in image_options:
            options += f" <option value='{json.dumps(image)}'> {image.get('display_name', image['name'])} </option>"

        js = """(function(){
            var select_element = document.getElementById('image');
            var value = select_element.value || select_element.options[select_element.selectedIndex].value;
            var value = JSON.parse(value);
            document.getElementById('image_description').innerText = ''
            if ('description' in value) {
                document.getElementById('image_description').innerText = value['description'];
            }
        })()"""

        image_description = '<p id="image_description" style="display: inline-block"> </p>'
        select_images = f'<select id="image" name="image" size="10" onchange="{js}"> {options} </select>'
        return f"{select_images}{image_description}"
    else:
        return None


async def parse_form_data(formdata: dict, spawner: Any) -> dict:
    spawner.log.info(f"FORM DATA: {formdata}")
    return formdata


def get_tapis_access_data(spawner: Any) -> None:
    """
    Returns the access token and base URL cached in the tapipy file
    """
    token_file = os.path.join(get_user_token_dir(spawner.user.name), ".tapipy")
    spawner.log.info(
        f"spawner looking for token file: {token_file} for user: {spawner.user.name}"
    )
    if not os.path.exists(token_file):
        spawner.log.warning(f"spawner did not find a token file at {token_file}")
        return None
    try:
        data = json.load(open(token_file))
    except ValueError:
        spawner.log.warning("could not ready json from token file")
        return None

    try:
        spawner.access_token = data[0]["token"]
        decoded_data = {}
        try:
            decoded_data = jwt.decode(
                data[0]["token"], options={"verify_signature": False}
            )
        except Exception as e:
            spawner.log.error(f"Error decoding access token: {e}")

        refresh_data = None
        if "exp" in decoded_data and decoded_data["exp"] < time.time():
            spawner.log.info(
                f"{spawner.user.name} has expired access token, attempting to refresh"
            )
            refresh_data = refresh_access_token(
                data[0]["refresh_token"], spawner.user.name
            )
            spawner.log.info(f"Data retrieved from refreshing: {refresh_data}")

        if refresh_data:
            spawner.log.info(
                f"Refreshed access token for: {spawner.user.name}, attempting to save and update tapipy files"
            )
            save_token(
                refresh_data["access_token"],
                refresh_data["refresh_token"],
                spawner.user.name,
                refresh_data["created_at"],
                refresh_data["expires_in"],
                refresh_data["expires_at"],
            )
            spawner.access_token = refresh_data["access_token"]
            spawner.refresh_token = refresh_data["refresh_token"]
        else:
            spawner.refresh_token = data[0]["refresh_token"]

        spawner.url = data[0]["api_server"]

        spawner.log.info(
            f"access token: {spawner.access_token}, refresh token: {spawner.refresh_token}, url: {spawner.url}"
        )

    except (TypeError, KeyError):
        spawner.log.warning(
            f"token file did not have an access token and/or an api_server. data: {data}"
        )
        return None


def get_tas_data(spawner: Any) -> None:
    """Get the TACC uid, gid and homedir for this user from the TAS API."""
    if not TAS_ROLE_ACCT:
        spawner.log.error("No TAS_ROLE_ACCT configured. Aborting.")
        return
    if not TAS_ROLE_PASS:
        spawner.log.error("No TAS_ROLE_PASS configured. Aborting.")
        return
    url = f"{TAS_URL_BASE}/users/username/{spawner.user.name}"
    headers = {"Content-type": "application/json", "Accept": "application/json"}
    try:
        rsp = requests.get(
            url,
            headers=headers,
            auth=HTTPBasicAuth(TAS_ROLE_ACCT, TAS_ROLE_PASS),
        )
    except Exception as e:
        spawner.log.error(
            f"Got an exception from TAS API. Exception: {e}. url: {url}. TAS_ROLE_ACCT: {TAS_ROLE_ACCT}"
        )
        return
    try:
        data = rsp.json()
        spawner.log.info("TAS DATA: %s", data)
    except Exception as e:
        spawner.log.error(
            f"Did not get JSON from TAS API. rsp: {rsp} Exception: {e}. url: {url}. TAS_ROLE_ACCT: {TAS_ROLE_ACCT}"
        )
        return
    spawner.tas_gid = None
    try:
        spawner.tas_uid = data["result"]["uid"]
        spawner.tas_gid = data["result"]["gid"]
        spawner.init_gid = data["result"]["gid"]
        spawner.tas_homedir = data["result"]["homeDirectory"]
    except Exception as e:
        spawner.log.error(
            f"Did not get attributes from TAS API. rsp: {rsp} Exception: {e}. url: {url}. TAS_ROLE_ACCT: {TAS_ROLE_ACCT}"
        )
        return

    gids = []

    try:
        server = Server("ldaps://ldap.tacc.utexas.edu:636")
        conn = Connection(
            server,
            "uid=ldapbind,ou=People,dc=tacc,dc=utexas,dc=edu",
            LDAP_PASS,
            client_strategy=SAFE_SYNC,
            auto_bind=True,
        )
        status, result, response, _ = conn.search(
            "ou=Groups,dc=tacc,dc=utexas,dc=edu",
            f"(uniqueMember=uid={spawner.user.name},ou=People,dc=tacc,dc=utexas,dc=edu)",
        )
        for entry in response:
            data = entry["dn"].split(",")
            cn = data[0].split("=")
            group = cn[1]
            temp_gid = group.split("-")[1]
            try:
                gid = int(temp_gid)
                gids.append(gid)
            except Exception:
                continue
    except Exception as e:
        spawner.log.error(f"Did not get gid's from ldap. rsp: {e}")

    if gids:
        spawner.supplemental_gids = gids

    # if the instance has a configured TAS_GID to use we will use that; otherwise,
    # we fall back on using the user's uid as the gid, which is (almost) always safe)
    if not spawner.tas_gid:
        spawner.tas_gid = spawner.configs.get("gid", spawner.tas_uid)
    spawner.log.info(f"Setting the following TAS data: uid:{spawner.tas_uid} gid:{spawner.tas_gid}")

    if not spawner.tas_uid or not spawner.tas_gid:
        raise web.HTTPError(403)
    spawner.uid = int(spawner.tas_uid)
    spawner.gid = int(spawner.tas_gid)


def get_user_token_dir(username: str) -> str:
    return os.path.join("/tapis/jupyter/tokens", INSTANCE, TENANT, username)


def get_mounts(spawner: Any) -> None:
    safe_username = safe_string(spawner.user.name).lower()
    safe_tenant = safe_string(TENANT).lower()
    safe_instance = safe_string(INSTANCE).lower()
    tapipy_safe_name = f"{safe_username}-{safe_tenant}-{safe_instance}-jhub-tapipy"
    current_safe_name = f"{safe_username}-{safe_tenant}-{safe_instance}-jhub-current"

    spawner.init_containers = [
        {
            "name": "rw-configmap-workaround",
            "image": "busybox",
            "command": [
                "/bin/sh",
                "-c",
                "cp -r /tapis_data/.tapipy /tapis_data_rw/.tapipy && cp -r /tapis_data/current /tapis_data_rw/current && ls -lah /tapis_data_rw && cat /tapis_data_rw/current/current && chmod -R 777 /tapis_data_rw && ls -lah /tapis_data_rw",
            ],
            "volumeMounts": [
                {
                    "mountPath": "/tapis_data/.tapipy",
                    "name": f"{tapipy_safe_name}-configmap",
                    "subPath": ".tapipy",
                },
                {
                    "mountPath": "/tapis_data/current",
                    "name": f"{current_safe_name}-configmap",
                    "subPath": "current",
                },
                {
                    "mountPath": "/tapis_data_rw/.tapipy",
                    "name": tapipy_safe_name,
                    "subPath": ".tapipy",
                },
                {
                    "mountPath": "/tapis_data_rw/current",
                    "name": current_safe_name,
                    "subPath": "current",
                },
            ],
        }
    ]

    spawner.volumes = [
        {
            "name": f"{tapipy_safe_name}-configmap",
            "configMap": {"name": tapipy_safe_name, "defaultMode": 0o0777},
        },
        {
            "name": f"{current_safe_name}-configmap",
            "configMap": {"name": current_safe_name, "defaultMode": 0o0777},
        },
        {
            "name": tapipy_safe_name,
            "emptyDir": {},
        },
        {
            "name": current_safe_name,
            "emptyDir": {},
        },
    ]
    spawner.volume_mounts = [
        {
            "mountPath": "/etc/.tapipy",
            "name": tapipy_safe_name,
            "subPath": ".tapipy/.tapipy",
        },
        {
            "mountPath": f"{jupyter_home}/.tapis-token",
            "name": current_safe_name,
            "subPath": "current",
        },
    ]

    volume_mounts = spawner.configs.get("volume_mounts")
    for item in spawner.user_configs:
        if item["value"].get("volume_mounts"):
            volume_mounts += [
                x for x in item["value"]["volume_mounts"] if x not in volume_mounts
            ]

    template_vars = {
        "username": spawner.user.name,
        "tenant_id": TENANT,
    }

    if hasattr(spawner, "tas_homedir"):
        template_vars["tas_homedir"] = spawner.tas_homedir

    if len(volume_mounts):
        for item in volume_mounts:
            path = item["path"].format(**template_vars)

            # volume names must consist of lower case alphanumeric characters or '-',
            # and must start and end with an alphanumeric character (e.g. 'my-name',  or '123-abc',
            # regex used for validation is '[a-z0-9]([-a-z0-9]*[a-z0-9])?')
            if item["mountPath"][-1] == "/":
                item["mountPath"] = item["mountPath"][:-1]
            vol_name = re.sub(
                r"([^a-z0-9-\s]+?)", "", item["mountPath"].split("/")[-1].lower()
            )

            vol = {"path": path, "readOnly": eval(item["readOnly"])}
            if item["type"] == "nfs":
                vol["server"] = item["server"]

            spawner.volumes.append({"name": vol_name, item["type"]: vol})

            spawner.volume_mounts.append(
                {"mountPath": item["mountPath"], "name": vol_name}
            )
        spawner.log.info(f"volumes: {spawner.volumes}")
        spawner.log.info(f"volume_mounts: {spawner.volume_mounts}")


def get_ds_projects(spawner: Any) -> None:
    """Mount DesignSafe projects from Corral."""
    if not IS_DESIGNSAFE:
        return

    spawner.host_projects_root_dir = spawner.configs.get("host_projects_root_dir")
    spawner.container_projects_root_dir = spawner.configs.get("container_projects_root_dir")
    spawner.network_storage = spawner.configs.get("network_storage")

    if not spawner.host_projects_root_dir or not spawner.container_projects_root_dir:
        spawner.log.info(f"No host/container projects root dir configured: {spawner.configs}")
        return
    if not spawner.access_token or not spawner.url:
        spawner.log.info("No access_token or url — skipping get_projects")
        return

    try:
        headers = {"x-tapis-token": spawner.access_token}
        rsp = requests.get(f"{projects_url}/api/projects/v2", headers=headers)
        data = rsp.json()
        projects = data.get("result")
        spawner.log.info(f"service returned projects: {projects}")
    except Exception as e:
        spawner.log.warning(f"Exception calling /projects for {spawner.user.name}: {e}")
        return

    try:
        spawner.log.info(f"Found {len(projects)} projects")
    except TypeError:
        spawner.log.error(f"Projects data has no length. response: {rsp}, data: {data}")
        return

    for project in projects:
        uuid = project.get("uuid")
        if not uuid:
            spawner.log.warning(f"No uuid for project: {project}")
            continue
        project_id = project.get("value", {}).get("projectId")
        if not project_id:
            spawner.log.warning(f"No projectId for project: {project}")
            continue

        server = spawner.network_storage
        mount_path = f"{spawner.container_projects_root_dir}/{project_id}"
        path = f"{spawner.host_projects_root_dir}/{uuid}"

        if uuid == "7997906542076432871-242ac11c-0001-012":
            path = "/corral/main/projects/NHERI/community"
            server = "129.114.52.166"

        spawner.volumes.append({
            "name": f"project-{safe_string(uuid).lower()}",
            "nfs": {"server": server, "path": path, "readOnly": False},
        })
        spawner.volume_mounts.append({
            "mountPath": mount_path,
            "name": f"project-{safe_string(uuid).lower()}",
        })

    spawner.log.info(spawner.volumes)
    spawner.log.info(spawner.volume_mounts)


def get_licenses(spawner: Any) -> None:
    """Fetch MATLAB and LSDYNA licenses."""
    if not spawner.access_token:
        spawner.log.info("No access_token — skipping get_licenses")
        return

    headers = {"x-tapis-token": tapis_service_token}

    for license_type, env_key in [("MATLAB", "MATLAB_LICENSE"), ("LSDYNA", "LSDYNA_LICENSE")]:
        url = f"{projects_url}/api/licenses/{license_type}/?username={spawner.user.name}"
        spawner.log.info(f"Fetching {license_type} license from {url}")
        try:
            rsp = requests.get(url, headers=headers)
            data = rsp.json()
            spawner.log.info(f"{license_type} license data: {data}")
            spawner.environment[env_key] = data["license"]
        except Exception as e:
            spawner.log.warning(f"Exception fetching {license_type} license for {spawner.user.name}: {e}")


def update_ds_env(spawner: Any) -> None:
    """DesignSafe Only: Update env to include mlm license file"""
    spawner.environment["MLM_LICENSE_FILE"] = spawner.configs.get("mlm_license_file", "")


def get_all_configs(spawner: Any) -> None:
    # Retrieve all of the configs and merge them together
    spawner.extra_pod_config = spawner.configs.get("extra_pod_config", {})
    spawner.extra_container_config = spawner.configs.get("extra_container_config", {})
    spawner.extra_resource_guarantees = spawner.configs.get("extra_resource_guarantees", {})
    spawner.extra_resource_limits = spawner.configs.get("extra_resource_limits", {})

    for user_conf in spawner.user_configs:
        conf_value = user_conf.get("value", user_conf)
        if "extra_pod_config" in conf_value:
            spawner.extra_pod_config = merge_configs(
                conf_value["extra_pod_config"], spawner.extra_pod_config
            )
        if "extra_resource_guarantees" in conf_value:
            spawner.extra_resource_guarantees = merge_configs(
                conf_value["extra_resource_guarantees"], spawner.extra_resource_guarantees
            )
        if "extra_resource_limits" in conf_value:
            spawner.extra_resource_limits = merge_configs(
                conf_value["extra_resource_limits"], spawner.extra_resource_limits
            )


def set_cpu_mem_limits(spawner: Any) -> None:
    # Find highest available limit between tenant/user/group configs and set env variables
    tenant_mem_limit = spawner.configs.get("mem_limit")
    mem_limits = {tenant_mem_limit: humanfriendly.parse_size(tenant_mem_limit)}
    cpu_limits = [spawner.configs.get("cpu_limit")]
    for item in spawner.user_configs:
        mem_limit = item["value"].get("mem_limit")
        cpu_limit = item["value"].get("cpu_limit")
        if mem_limit:
            mem_limits.update({mem_limit: humanfriendly.parse_size(mem_limit)})
        if cpu_limit:
            cpu_limits.append(cpu_limit)
    spawner.log.info(f"available limits -- mem: {mem_limits} cpu:{cpu_limits}")
    spawner.mem_limit = max(mem_limits, key=lambda k: mem_limits[k])
    spawner.cpu_limit = float(max(cpu_limits))
    # Set the guarantees really low because when None or 0,
    # it sets a resource request for an amount equal to the limit
    spawner.mem_guarantee = ".001K"
    spawner.cpu_guarantee = float(0.001)


def set_selected_image(spawner: Any) -> None:
    # only 1 image option, so we can skip the form
    if len(spawner.configs.get("images")) == 1:
        spawner.image = spawner.configs.get("images")[0]["name"]
    else:
        image_options = spawner.configs.get("images")
        spawner.log.info(f"Verifiying image: {image_options}")
        user_configs = spawner.user_configs
        spawner.log.info(f"User configs: {user_configs}")
        for item in spawner.user_configs:
            spawner.log.info(f"Item: {item}")
            for image in item["value"]["images"]:
                spawner.log.info(f"Image: {image}")
                image_options.append(image)
        user_options = spawner.user_options
        spawner.log.info(f"User options: {user_options}")
        image = ast.literal_eval(spawner.user_options["image"][0])
        spawner.log.info(f"Image: {image}")

        try:
            spawner.log.info(f"Checking user options: image-{image} against metadata: {image_options}")
            next(
                option
                for option in image_options
                if option["name"] == image["name"]
                and option["display_name"] == image["display_name"]
            )
        except Exception as e:
            spawner.log.error(
                f"{spawner.user.name} user options not allowed. selected options {spawner.user_options}. allowed options {image_options}. got an error:{e}"
            )
            raise web.HTTPError(403)

        spawner.image = image["name"]
        spawner.log.info(image)
        spawner.log.info(spawner.extra_pod_config)
        if image.get("extra_pod_config"):
            merge_configs(image["extra_pod_config"], spawner.extra_pod_config)
        if image.get("extra_container_config"):
            merge_configs(image["extra_container_config"], spawner.extra_pod_config)
        spawner.notebook_dir = image.get("notebook_dir", "")


def set_spawner_env(spawner: Any) -> None:
    user = spawner.user.name
    uid = str(spawner.uid)
    gid = str(spawner.gid)

    env = {
        "MKL_NUM_THREADS": max(spawner.cpu_limits),
        "NUMEXPR_NUM_THREADS": max(spawner.cpu_limits),
        "OMP_NUM_THREADS": max(spawner.cpu_limits),
        "OPENBLAS_NUM_THREADS": max(spawner.cpu_limits),
        "SCINCO_JUPYTERHUB_IMAGE": spawner.image,
        "HUB_USER": user,
        "HUB_UID": uid,
        "HUB_GID": gid,
    }

    spawner.environment = env
