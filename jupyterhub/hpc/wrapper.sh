#!/bin/bash

SESSION_FILE="$STOCKYARD/delete_me_to_end_session"

# parse the agave environment parameter and export to the current environment:
eval `python3 set_env.py ${environment}`

# run notebook in background
LOCAL_IPY_PORT=8888

export SINGULARITYENV_XDG_RUNTIME_DIR="$STOCKYARD/jupyter"

nohup singularity run '${containerImage}' &

# use ssh for port forwarding
# echo Using ssh for port forwarding
IPY_PORT_PREFIX=2
NODE_HOSTNAME_PREFIX=`hostname -s`
NODE_HOSTNAME_DOMAIN=`hostname -d`
NODE_HOSTNAME_LONG=`hostname -f`
LOGIN_IPY_PORT="$((49+$IPY_PORT_PREFIX))`echo $NODE_HOSTNAME_PREFIX | perl -ne 'print $1.$2.$3 if /c\d\d(\d)-(\d)\d(\d)/;'`"

echo Port is $LOGIN_IPY_PORT

for i in `seq 5`; do
    ssh -f -g -N -R $LOGIN_IPY_PORT:$NODE_HOSTNAME_LONG:$LOCAL_IPY_PORT login$i
done

# send email notification
echo Your notebook is now running at http://$NODE_HOSTNAME_DOMAIN:$LOGIN_IPY_PORT

# send IP and PORT to actor via nonce URL
curl -H "Content-type: application/json" \
-d '{"tenant": ${tenant}, "instance": ${instance}, "username": ${username}. "ip": "$NODE_HOSTNAME_DOMAIN", "port": "$LOGIN_IPY_PORT" }' ${nonce_url}

# use file to kill job
echo $NODE_HOSTNAME_LONG $IPYTHON_PID > $SESSION_FILE
while [ -f $SESSION_FILE ] ; do
    sleep 10
done