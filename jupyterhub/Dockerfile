# Image: taccsciapps/jupyterhub:1.0

#from jupyterhub/jupyterhub:2.0.0
from taccsciapps/jupyterhub:2.0.2

#RUN apt-get update && apt-get install -y build-essential chromium-browser curl unzip vim
#RUN apt-get -y install git
#RUN pip install oauthenticator agavepy jupyterhub-kubespawner notebook ipdb humanfriendly git+https://github.com/kubernetes-client/python.git selenium webdriver-manager
#RUN pip install pyjwt[crypto]==1.7.1
#RUN pip install --upgrade pip
#RUN pip install tapipy --ignore-installed certifi 
#RUN pip install ldap3

#ADD agave.py /opt/conda/lib/python3.6/site-packages/oauthenticator/agave.py
#ADD common.py /opt/conda/lib/python3.6/site-packages/jupyterhub/common.py
#ADD selenium/ /srv/jupyterhub/selenium
ADD spawner_hooks.py /opt/conda/lib/python3.6/site-packages/jupyterhub/spawner_hooks.py
#ADD jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
#ADD custom_templates /opt/conda/share/jupyterhub/templates/custom_templates
