import ast
import humanfriendly
import json
import os
import re
import requests

from tornado import web
from ldap3 import Server, Connection, SAFE_SYNC
from agavepy.agave import Agave
from jupyterhub.common import (
    TENANT,
    INSTANCE,
    base_url,
    v2_token_url,
    get_tenant_configs,
    safe_string,
    get_user_configs,
)

# TAS configuration:
# base URL for TAS API.
TAS_URL_BASE = os.environ.get("TAS_URL_BASE", "https://tas.tacc.utexas.edu/api/v1")
TAS_ROLE_ACCT = os.environ.get("TAS_ROLE_ACCT", "tas-jetstream")
TAS_ROLE_PASS = os.environ.get("TAS_ROLE_PASS")
LDAP_PASS = os.environ.get("LDAP_PASS")


def hook(spawner):
    spawner.start_timeout = 60 * 5
    spawner.log.info("👻 tenant configs 👻 {}".format(spawner.configs))
    spawner.log.info("👽 user configs 👽 {}".format(spawner.user_configs))
    spawner.log.info("😱 user options (from form) 😱 {}".format(spawner.user_options))

    get_agave_access_data(spawner)
    spawner.log.info(
        "access token: {}, refresh token: {}, url: {}".format(
            spawner.access_token, spawner.refresh_token, spawner.url
        )
    )
    # check if access token is valid
    
    get_tas_data(spawner)

    spawner.uid = int(spawner.configs.get("uid", spawner.tas_uid))
    spawner.gid = int(spawner.configs.get("gid", spawner.tas_gid))

    spawner.extra_pod_config = spawner.configs.get("extra_pod_config", {})
    spawner.extra_container_config = spawner.configs.get("extra_container_config", {})
    
    if (
        len(spawner.configs.get("images")) == 1 and not spawner.hpc_available
    ):  # only 1 image option, so we skipped the form
        spawner.image = spawner.configs.get("images")[0]["name"]
    else:
        # verify form data
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
            spawner.log.info(
                "Checking user options: image-{} hpc-{} against metadata: {}".format(
                    image, spawner.user_options.get("hpc"), image_options
                )
            )
            allowed_options = next(
                option for option in image_options if option["name"] == image["name"] and option["display_name"] == image["display_name"]
            )
            if spawner.user_options.get("hpc"):
                if not eval(allowed_options.get("hpc_available", "False")):
                    spawner.log.error(
                        "hpc is not available for this image. {} -- {}".format(
                            spawner.user.name, allowed_options
                        )
                    )
                    raise web.HTTPError(403)
        except Exception as e:
            spawner.log.error(
                "{} user options not allowed. selected options {}. allowed options {}. got an error:{}".format(
                    spawner.user.name, spawner.user_options, image_options, e
                )
            )
            raise web.HTTPError(403)

        spawner.image = image["name"]
        if image.get("extra_pod_config"):
            merge_configs(image["extra_pod_config"], spawner.extra_pod_config)
        if image.get("extra_container_config"):
            merge_configs(image["extra_container_config"], spawner.extra_pod_config)
        spawner.notebook_dir = image.get("notebook_dir", "")

    if not spawner.user_options.get("hpc"):
        # find highest available limit between tenant/user/group configs
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
        spawner.log.info(
            "available limits -- mem: {} cpu:{}".format(mem_limits, cpu_limits)
        )
        spawner.mem_limit = max(mem_limits, key=mem_limits.get)
        spawner.cpu_limit = float(max(cpu_limits))
        # Set the guarantees really low because when None or 0,it sets a resource request for an amount equal to the limit
        spawner.mem_guarantee = ".001K"
        spawner.cpu_guarantee = float(0.001)
        spawner.environment = {
            "MKL_NUM_THREADS": max(cpu_limits),
            "NUMEXPR_NUM_THREADS": max(cpu_limits),
            "OMP_NUM_THREADS": max(cpu_limits),
            "OPENBLAS_NUM_THREADS": max(cpu_limits),
            "SCINCO_JUPYTERHUB_IMAGE": spawner.image,
        }
    get_mounts(spawner)
    get_projects(spawner)


def merge_configs(x, y):
    merged_pod_config = {**x, **y}
    for key, value in merged_pod_config.items():
        if key in x and key in y:
            merged_pod_config[key].update(x[key])

async def get_notebook_options(spawner):
    spawner.configs = get_tenant_configs()
    spawner.log.info(f"spawner configs: {spawner.configs}")
    spawner.user_configs = get_user_configs(spawner.user.name)
    spawner.log.info(f"spawner user configs: {spawner.configs}")

    image_options = spawner.configs.get("images")

    for item in spawner.user_configs:
        for image in item["value"].get("images"):
            if image not in image_options:
                image_options += [image]
            if eval(image.get("hpc_available", "False")):
                spawner.hpc_available = True

    if not hasattr(
        spawner, "hpc_available"
    ):  # only looped through user options -- check the tenant options for hpc
        for image in spawner.configs.get("images"):
            if eval(image.get("hpc_available", "False")):
                spawner.hpc_available = True
                break
            spawner.hpc_available = False

    image_options = sorted(image_options, key=lambda d: d["name"])
    if len(image_options) > 1 or spawner.hpc_available:
        options = ""
        for image in image_options:
            options = options + " <option value='{}'> {} </option>".format(
                json.dumps(image), image.get("display_name", image["name"])
            )

        if spawner.hpc_available:
            hpc = """<input type="checkbox" id="hpc" name="hpc" style="display: none">
                <label for="hpc" id="hpc_label" style="display: none">Run on HPC</label>
                """
            js = """(function hpc(){
                var select_element = document.getElementById('image');
                var value = select_element.value || select_element.options[select_element.selectedIndex].value;
                var value = JSON.parse(value);
                document.getElementById('image_description').innerText = ''
                if ('description' in value) {
                    document.getElementById('image_description').innerText = value['description'];
                }
                if (value['hpc_available']) {
                    document.getElementById('hpc').checked = false;
                    document.getElementById('hpc').style.display = 'inline-block';
                    document.getElementById('hpc_label').style.display = 'inline-block';
                } else {
                    document.getElementById('hpc').checked = false;
                    document.getElementById('hpc').style.display = 'none';
                    document.getElementById('hpc_label').style.display = 'none';
                }
            })()"""
        else:
            js = """(function hpc(){
                            var select_element = document.getElementById('image');
                            var value = select_element.value || select_element.options[select_element.selectedIndex].value;
                            var value = JSON.parse(value);
                            document.getElementById('image_description').innerText = ''
                            if ('description' in value) {
                                document.getElementById('image_description').innerText = value['description'];
                            }
                        })()"""

            hpc = ""

        image_description = (
            '<p id="image_description" style="display: inline-block"> </p>'
        )
        select_images = '<select id="image" name="image" size="10" onchange="{}"> {} </select>'.format(
            js, options
        )
        spawner.log.info(select_images)
        return "{}{}{}".format(select_images, image_description, hpc)

async def parse_form_data(formdata, spawner):
    spawner.log.info(f"FORM DATA: {formdata}")
    return formdata


def get_agave_access_data(spawner):
    """
    Returns the access token and base URL cached in the agavepy file
    :return:
    """
    # TODO figure out naming conventions that can follow k8 rules
    # k8 names must consist of lower case alphanumeric characters, '-' or '.',
    # and must start and end with an alphanumeric character
    # do all tenant names follow that? usernames?
    token_file = os.path.join(get_user_token_dir(spawner.user.name), ".agpy")
    spawner.log.info(
        "spawner looking for token file: {} for user: {}".format(
            token_file, spawner.user.name
        )
    )
    if not os.path.exists(token_file):
        spawner.log.warning(
            "spawner did not find a token file at {}".format(token_file)
        )
        return None
    try:
        data = json.load(open(token_file))
    except ValueError:
        spawner.log.warning("could not ready json from token file")
        return None

    try:
        spawner.access_token = data[0]["token"]
        spawner.log.info("Setting token: {}".format(spawner.access_token))
        spawner.refresh_token = data[0]["refresh_token"]
        spawner.log.info("Setting refresh token: {}".format(spawner.refresh_token))
        spawner.url = data[0]["api_server"]
        spawner.log.info("Setting url: {}".format(spawner.url))

    except (TypeError, KeyError):
        spawner.log.warning(
            "token file did not have an access token and/or an api_server. data: {}".format(
                data
            )
        )
        return None


def get_tas_data(spawner):
    """Get the TACC uid, gid and homedir for this user from the TAS API."""
    if not TAS_ROLE_ACCT:
        spawner.log.error("No TAS_ROLE_ACCT configured. Aborting.")
        return
    if not TAS_ROLE_PASS:
        spawner.log.error("No TAS_ROLE_PASS configured. Aborting.")
        return
    url = "{}/users/username/{}".format(TAS_URL_BASE, spawner.user.name)
    headers = {"Content-type": "application/json", "Accept": "application/json"}
    try:
        rsp = requests.get(
            url,
            headers=headers,
            auth=requests.auth.HTTPBasicAuth(TAS_ROLE_ACCT, TAS_ROLE_PASS),
        )
    except Exception as e:
        spawner.log.error(
            "Got an exception from TAS API. "
            "Exception: {}. url: {}. TAS_ROLE_ACCT: {}".format(e, url, TAS_ROLE_ACCT)
        )
        return
    try:
        data = rsp.json()
        spawner.log.info("TAS DATA: %s", data)
    except Exception as e:
        spawner.log.error(
            "Did not get JSON from TAS API. rsp: {}"
            "Exception: {}. url: {}. TAS_ROLE_ACCT: {}".format(
                rsp, e, url, TAS_ROLE_ACCT
            )
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
            "Did not get attributes from TAS API. rsp: {}"
            "Exception: {}. url: {}. TAS_ROLE_ACCT: {}".format(
                rsp, e, url, TAS_ROLE_ACCT
            )
        )
        return
    
    gids = []

    try:
        server = Server('ldaps://ldap.tacc.utexas.edu:636')
        conn = Connection(server, 'uid=ldapbind,ou=People,dc=tacc,dc=utexas,dc=edu', LDAP_PASS, client_strategy=SAFE_SYNC, auto_bind=True)
        status, result, response, _ = conn.search('ou=Groups,dc=tacc,dc=utexas,dc=edu', f'(uniqueMember=uid={spawner.user.name},ou=People,dc=tacc,dc=utexas,dc=edu)')
        for entry in response:
            data = entry['dn'].split(',')
            cn = data[0].split('=')
            group = cn[1]
            temp_gid = group.split('-')[1]
            try:
                gid = int(temp_gid)
                gids.append(gid)
            except Exception as e:
                continue
    except Exception as e:
        spawner.log.error(
            "Did not get gid's from ldap. rsp: {}"
            .format(e)
        )
    
    if gids:
        spawner.supplemental_gids = gids

    # if the instance has a configured TAS_GID to use we will use that; otherwise,
    # we fall back on using the user's uid as the gid, which is (almost) always safe)
    if not spawner.tas_gid:
        spawner.tas_gid = spawner.configs.get("gid", spawner.tas_uid)
    spawner.log.info(
        # "Setting the following TAS data: uid:{} gid:{} homedir:{}".format(
        #     spawner.tas_uid, spawner.tas_gid, spawner.tas_homedir
        # )
        "Setting the following TAS data: uid:{} gid:{}".format(
            spawner.tas_uid, spawner.tas_gid
        )
    )


def get_user_token_dir(username):
    return os.path.join("/agave/jupyter/tokens", INSTANCE, TENANT, username)


def get_mounts(spawner):
    safe_username = safe_string(spawner.user.name).lower()
    safe_tenant = safe_string(TENANT).lower()
    safe_instance = safe_string(INSTANCE).lower()
    agpy_safe_name = "{}-{}-{}-jhub-agpy".format(
        safe_username, safe_tenant, safe_instance
    )
    current_safe_name = "{}-{}-{}-jhub-current".format(
        safe_username, safe_tenant, safe_instance
    )

    spawner.init_containers = [
        {
            "name": "rw-configmap-workaround",
            "image": "busybox",
            "command": [
                "/bin/sh",
                "-c",
                "cp -r /agave_data/.agpy /agave_data_rw/.agpy && cp -r /agave_data/current /agave_data_rw/current && ls -lah /agave_data_rw && cat /agave_data_rw/current/current && chmod -R 777 /agave_data_rw && ls -lah /agave_data_rw",
            ],
            "volumeMounts": [
                {
                    "mountPath": "/agave_data/.agpy",
                    "name": "{}-configmap".format(agpy_safe_name),
                    "subPath": ".agpy",
                },
                {
                    "mountPath": "/agave_data/current",
                    "name": "{}-configmap".format(current_safe_name),
                    "subPath": "current",
                },
                {
                    "mountPath": "/agave_data_rw/.agpy",
                    "name": agpy_safe_name,
                    "subPath": ".agpy",
                },
                {
                    "mountPath": "/agave_data_rw/current",
                    "name": current_safe_name,
                    "subPath": "current",
                }
            ],
        }
    ]

    spawner.volumes = [
        {
            "name": "{}-configmap".format(agpy_safe_name),
            "configMap": {"name": agpy_safe_name, "defaultMode": 0o0777},
        },
        {
            "name": "{}-configmap".format(current_safe_name),
            "configMap": {"name": current_safe_name, "defaultMode": 0o0777},
        },
        {
            "name": agpy_safe_name,
            "emptyDir": {},
        },
        {
            "name": current_safe_name,
            "emptyDir": {},
        }
    ]
    spawner.volume_mounts = [
        {
            "mountPath": "/etc/.agpy",
            "name": agpy_safe_name,
            "subPath": ".agpy/.agpy",
        },
        {
            "mountPath": "/home/jupyter/.agave",
            "name": current_safe_name,
            "subPath": "current",
        }
    ]
    volume_mounts = spawner.configs.get("volume_mounts")

    for item in spawner.user_configs:
        if item["value"].get("volume_mounts"):
            volume_mounts += [
                x for x in item["value"]["volume_mounts"] if x not in volume_mounts
            ]

    template_vars = {
        "username": spawner.user.name,
        "tenant_id": TENANT,  # TODO do we need this?
    }

    if hasattr(spawner, "tas_homedir"):
        template_vars["tas_homedir"] = spawner.tas_homedir

    if len(volume_mounts):
        for item in volume_mounts:
            path = item["path"].format(**template_vars)

            # volume names must consist of lower case alphanumeric characters or '-',
            # and must start and end with an alphanumeric character (e.g. 'my-name',  or '123-abc',
            # regex used for validation is '[a-z0-9]([-a-z0-9]*[a-z0-9])?')
            if item["mountPath"][-1] == '/':
                item["mountPath"] = item["mountPath"][:-1]
            vol_name = re.sub(
                r"([^a-z0-9-\s]+?)", "", item["mountPath"].split("/")[-1].lower()
            )

            vol = {"path": path, "readOnly": eval(item["readOnly"])}
            if item["type"] == "nfs":
                vol["server"] = item["server"]

            if item["path"] == "/work2/{tas_homedir}":
                spawner.log.info(spawner.init_gid)
                if spawner.init_gid == 0:
                    continue
            
            spawner.volumes.append({"name": vol_name, item["type"]: vol})

            spawner.volume_mounts.append(
                {"mountPath": item["mountPath"], "name": vol_name}
            )
        spawner.log.info("volumes: {}".format(spawner.volumes))
        spawner.log.info("volume_mounts: {}".format(spawner.volume_mounts))


def get_projects(spawner):
    if not spawner.access_token:
        spawner.log.info("no access_token")
        return None
    #url = "{}/projects/v2/".format(spawner.url)
    projects_url = f"{base_url}/projects/v2"
    
    # use spawner.access_token to generate v2 token
    # call v3 to v2 token endpoint
    # tacc.develop.tapis.io/v3/oauth2/v2/token
    spawner.log.error("getting projects")
    try:
        token_url = v2_token_url
        headers = {
            'x-tapis-token': spawner.access_token
        }
        rsp = requests.post(token_url, headers=headers)
        rsp.raise_for_status()
        access_token = rsp.json()['access_token']
    except Exception as e:
        spawner.log.error(f"Unable to generate v2 token; error: {e}; response: {rsp}")
        return None

    # with v2 token, send request to projects url
    try:
        ag = Agave(api_server=base_url, token=access_token)
        rsp = ag.geturl(projects_url)
        rsp.raise_for_status()
        data = rsp.json()
    except Exception as e:
        spawner.log.warn(f"Did not get data from /projects. Exception: {e}")
        spawner.log.warn(f"Full response from service: {rsp}")
        spawner.log.warn(f"url used: {projects_url}")
        return None

    projects = data.get("mounts")
    spawner.network_storage = spawner.configs.get('network_storage')

    try:
        spawner.log.info("Found {} projects".format(len(projects)))
    except TypeError:
        spawner.log.error("Projects data has no length.")
        spawner.log.info(f"response: {rsp}, data: {data}")
        return None

    for p in projects:
        mountPath = p.get('mountPath')
        path = p.get('path')
        pems = p.get('pems')
        readOnly = False if pems == 'rw' else True
        source = ""
        if path.split('/')[1] == 'work':
            source = "work"
            path = path.replace('work', 'work2', 1)
        if path.split('/')[1] == 'corral-repl':
            source = "corral"
            path = path.replace('corral-repl', 'corral/main', 1)
        # check if corral -- then use nfs, else, use hostPath
        if source == "corral":
            name = 'project-{}'.format(safe_string(mountPath).lower())
            if len(name) > 63:
                name = name[:62] + 'e'
            spawner.volumes.append(
                {
                    'name': name,
                    "nfs": {
                        "server": spawner.network_storage,
                        "path": path,
                        "readOnly": readOnly,
                    },
                }
            )

            spawner.volume_mounts.append(
                {
                    "mountPath": f"/home/jovyan/projects{mountPath}",
                    'name': name,
                }
            )
        if source == "work":
            name = 'project-{}'.format(safe_string(mountPath).lower())
            if len(name) > 63:
                name = name[:62] + 'e'
            spawner.volumes.append(
                {
                    'name': name,
                    "hostPath": {
                        "path": path,
                        "readOnly": readOnly,
                    },
                }
            )

            spawner.volume_mounts.append(
                {
                    "mountPath": f"/home/jovyan/projects{mountPath}",
                    'name': name,
                }
            )
    spawner.log.info(spawner.volumes)
    spawner.log.info(spawner.volume_mounts)
