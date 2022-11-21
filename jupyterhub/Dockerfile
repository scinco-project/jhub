# Image: taccsciapps/jupyterhub:2.0

FROM jupyterhub/jupyterhub:3.0.0

RUN apt-get update
RUN apt-get install -y build-essential curl chromium-browser unzip vim git

RUN pip install oauthenticator agavepy jupyterhub-kubespawner==4.3.0 notebook ipdb humanfriendly git+https://github.com/kubernetes-client/python.git selenium webdriver-manager
RUN pip install pyjwt[crypto]
RUN pip install --upgrade pip
RUN pip install tapipy --ignore-installed certifi 
RUN pip install ldap3

# COPY requirements.txt /home/requirements.txt
# RUN pip install -r /home/requirements.txt

ADD tapis.py /usr/local/lib/python3.10/dist-packages/oauthenticator/tapis.py
ADD common.py /usr/local/lib/python3.10/dist-packages/jupyterhub/common.py
ADD selenium/ /srv/jupyterhub/selenium
ADD spawner_hooks.py /usr/local/lib/python3.10/dist-packages/jupyterhub/spawner_hooks.py
ADD jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
ADD custom_templates /usr/local/share/jupyterhub/templates/custom_templates


# FROM taccsciapps/jupyterhub:2.0.5

# ADD spawner_hooks.py /opt/conda/lib/python3.6/site-packages/jupyterhub/spawner_hooks.py
