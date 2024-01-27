#!/usr/bin/with-contenv bashio

export IS_IN_DOCKER=true
export DEFAULTENABLEDPLUGINS=signalk-mqtt-client
#export ADMINUSER=admin:test123
# export PORT=3001


# Start reverse proxy
/usr/sbin/nginx

# Start Signal K Server
/usr/local/bin/signalk-server --sample-nmea0183-data

