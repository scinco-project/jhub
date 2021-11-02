import docker

# Starts up jupyter notebook docker image

# This script uses python to run a docker command similar to the following:
# docker run --rm -p 8888:8888 -v $(pwd)/jupyter-notebook-localconf.py:/home/jupyter/.jupyter/jupyter_notebook_config.py taccsciapps/jupyteruser-ds start-notebook.sh

client = docker.from_env()
image = client.images.pull('taccsciapps/jupyteruser-ds:1.2.4')

client.containers.run(
    image,
    ports={'8888/tcp': 8888},
    volumes={'/jupyter-notebook-localconf.py':
                {'bind': '/home/jupyter/.jupyter/jupyter_notebook_config.py',
                 'mode': 'rw'}
             }
)

docker service create --name jhub --user 458981:816877 --replicas 1 --mount source=/corral-repl/tacc/NHERI/shared/mlm55,target=/home/jupyter/MyData,type=bind --mount source=/corral-repl/tacc/NHERI/published,target=/home/jupyter/NHERI-Published,type=bind --mount source=/corral-repl/tacc/NHERI/public/projects,target=/home/jupyter/Published,type=bind --mount source=/corral-repl/tacc/NHERI/community,target=/home/jupyter/CommunityData,type=bind --publish 3000 taccsciapps/jupyteruser-ds:1.2.6

"/corral-repl/tacc/NHERI/shared/mlm55:/home/jupyter/MyData:rw",
  "/corral-repl/tacc/NHERI/published:/home/jupyter/NHERI-Published:ro",
  "/corral-repl/tacc/NHERI/shared/dan/Meta_Published:/home/jupyter/Published:ro",
  "/corral-repl/tacc/NHERI/public/projects:/home/jupyter/NEES:ro",
  "/corral-repl/tacc/NHERI/community:/home/jupyter/CommunityData:ro"