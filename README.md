# JupyterHub Implementation

## Authentication

Authentication is handled via the tapis.py file using the Tapis OAuthenticator, allowing any user with a TACC account to be able to login. 

The class TapisOAuthenticator handles the workflow and different steps. After the user successfully logs in, we have to authenticate the user with an authoirzation code that they submit. 

We send the code to the Tapis /oauth2/tokens endpoint, along with the redirect uri and grant type (authorization code in this case). We also pass the Tapis client credentials in the header.

We parse the response from the tokens API and grab a bunch of different fields and we save that information in a file for JupyterHub.

## JupyterHub Config

The jupyterhub_config.py file controls several different aspects of the JupyterHub environment. 

### KubeSpawner

We use the KubeSpawner to launch our notebook servers on a Kubernetes cluster. We configure the pre_spawn_hook, options_form, and options_from_form attributes. 

## Notebook Spawner

Most of the logic goes into the configuration and building of the notebook server, handled in the spawner_hooks.py file. Going back to the jupyterhub_config.py file, at the end we set
``c.KubeSpawner.pre_spawn_hook = hook``

Where `hook` is the main function in the spawner_hooks.py file. The hook file is where we can alter the environment and the spawner itself in all sorts of ways.
For example, we set the timeout to 5min:

``spawner.start_timeout = 60 * 5``

So, after a user's server starts being created, if it isn't running after 5 minutes, it will automatically shutdown. Let's go into a little more detail on what happens in the hook function.

## Spawner Hook

We will then go on to set different data needed for authenitcation and authorization within the `get_agave_access_data` and `get_tas_data` functions -- defined below.

If a user has more than one notebook server image available to them (options form generated by `get_notebook_options` function), they will be presented with a screen that allows them to choose whichever image they want --

``spawner.image = image['name']``

where image is the object they select. If only one image is allowed, we can just

``spawner.image = spawner.configs.get("images")[0]["name"]``

where we grab the image directly from the configuration metadata for the JupyterHub.

We then grab the different memory and cput limits from the metadata and set those for the spawner

```
mem_limits = {tenant_mem_limit: humanfriendly.parse_size(tenant_mem_limit)}
cpu_limits = [spawner.configs.get("cpu_limit")]
...
spawner.mem_limit = max(mem_limits, key=mem_limits.get)
spawner.cpu_limit = float(max(cpu_limits))
```

We also set some different environment variables needed for numpy and one for tracking which image is used for the notebook

```
spawner.environment = {
    "MKL_NUM_THREADS": max(cpu_limits),
    "NUMEXPR_NUM_THREADS": max(cpu_limits),
    "OMP_NUM_THREADS": max(cpu_limits),
    "OPENBLAS_NUM_THREADS": max(cpu_limits),
    "SCINCO_JUPYTERHUB_IMAGE": spawner.image,
}
```

Next we grab the different mounts and projects available to the user withing the `get_mounts` and `get_projects` functions.

One thing to note about each of the functions that alter the spawner in some way require you pass the spawner object in so you have access to it

``get_mounts(spawner)``

### get_agave_access_data

When a user goes through the authentication process, the response from the tokens API is saved in an agavepy file. In this function, we find the file and set the different spawner attributes that allow Jupyter to verify it's you -- access token, refresh token, and a base url. For example, to set the access token after we loaded the data

``spawner.access_token = data[0]["token"]``

### get_tas_data

This function is responsible for getting the TACC uid, gid, and home directory for a user from the TAS API. This allows us to make sure the user has the correct uid and gid for different directories. The home directory allows us to mount their work directory from Stockyard so they can access their data from JupyterHub.

### get_mounts

This function is responsible for getting the different mounts available to the user. The first thing we do is create some initial containers for the spawner, namely where we hold the agave data for verification purposes. Next, we can grab the list of volume mounts from the meta for the tenant, and any extra volume mounts specific to the user (ie: from a group). 

We then go through each volume mount and create a volume / volume_mount for each one and append them to the spawner. 

### get_projects

This function allows us to retrieve any projects that the user is a part of and create volume mounts to those different projects. Since this endpoint is currently only available in v2, we have to convert the v3 token from the auth workflow to a v2 token. We can then request the projects URL on behalf of the user and get the mounts from the response. For where these projects are located in the network, we have a 'network_storage' variable in the meta. 

We go through each project and run some simple string replace to fit the format of how they appear (ie: work -> work2, corral-repl -> corral/main). And then, depending on what the source of the mount is, we either label it an nfs mount (corral) or a hostPath (work).

## Metadata

Tapis has a service called metadata, which allows user to store information in database entries called documents. These documents serve as the backbone of JupyterHub, allowing us to save the configuration of individual JupyterHub instances. The common.py file handles the different metadata calls that we make.

### get_config_metadata_name

This one-line function is responsible for returning the name of the document associated with the current JupyterHub instance by using the TENANT (ie: TACC) and INSTANCE (ie: dev, prod).

### get_tenant_configs

Using the name of the config metadata, this returns the document associated with the JupyterHub instance.

### get_user_configs

Argument: username

This function allows us to scan the database and return any extra documents associated with the user (ie: a sub group).