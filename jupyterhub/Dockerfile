# Image: taccsciapps/jupyterhub:1.0

from jupyterhub/jupyterhub:2.3.1
#from taccsciapps/jupyterhub:2.0.2

# RUN apt update -y && apt upgrade -y
# RUN apt install software-properties-common -y
# RUN add-apt-repository ppa:deadsnakes/ppa -y
# RUN apt update
# RUN apt install python3.8 -y
RUN apt-get update && apt-get install -y build-essential chromium-browser curl unzip vim
RUN apt-get -y install git
RUN pip install oauthenticator agavepy jupyterhub-kubespawner notebook ipdb humanfriendly git+https://github.com/kubernetes-client/python.git selenium webdriver-manager
RUN pip install pyjwt[crypto]
RUN pip install --upgrade pip
RUN pip install tapipy --ignore-installed certifi 
RUN pip install ldap3

ADD agave.py /usr/local/lib/python3.8/dist-packages/oauthenticator/agave.py
ADD common.py /usr/local/lib/python3.8/dist-packages/jupyterhub/common.py
ADD selenium/ /srv/jupyterhub/selenium
ADD spawner_hooks.py /usr/local/lib/python3.8/dist-packages/jupyterhub/spawner_hooks.py
ADD jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
ADD custom_templates /usr/local/share/jupyterhub/templates/custom_templates
