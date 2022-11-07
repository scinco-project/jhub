# Image: taccsciapps/jupyterhub:1.0

FROM jupyterhub/jupyterhub:3.0.0
#FROM taccsciapps/jupyterhub:2.0.2
#FROM python:3.9-slim-bullseye

# RUN apt update -y && apt upgrade -y
# RUN apt install software-properties-common -y
# RUN add-apt-repository ppa:deadsnakes/ppa -y
# RUN apt update
# RUN apt install python3.8 -y
RUN apt-get update
#RUN apt-get install wget
#RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
#RUN dpkg -i google-chrome-stable_current_amd64.deb; apt-get -fy install
RUN apt-get install -y build-essential curl chromium-browser unzip vim git
#RUN apt-get install -y python3-dev

# RUN apt-get update && \
#     apt-get upgrade -y && \ 
#     apt-get install -y \
#         build-essential \
#         chromium \
#         curl \
#         unzip \
#         vim \
#         git

RUN pip install oauthenticator agavepy jupyterhub-kubespawner==4.3.0 notebook ipdb humanfriendly git+https://github.com/kubernetes-client/python.git selenium webdriver-manager
RUN pip install pyjwt[crypto]
RUN pip install --upgrade pip
RUN pip install tapipy --ignore-installed certifi 
RUN pip install ldap3

# COPY requirements.txt /home/requirements.txt
# RUN pip install -r /home/requirements.txt

ADD agave.py /usr/local/lib/python3.10/dist-packages/oauthenticator/agave.py
ADD common.py /usr/local/lib/python3.10/dist-packages/jupyterhub/common.py
ADD selenium/ /srv/jupyterhub/selenium
ADD spawner_hooks.py /usr/local/lib/python3.10/dist-packages/jupyterhub/spawner_hooks.py
ADD jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
ADD custom_templates /usr/local/share/jupyterhub/templates/custom_templates

#/opt/conda/lib/python3.6/site-packages

# CMD ["jupyterhub", "--config", "/srv/jupyterhub/jupyterhub_config.py"]