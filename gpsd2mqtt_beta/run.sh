#!/usr/bin/with-contenv bashio

# Get the device config
CONFIG_PATH="/data/options.json"
INPUT_TYPE=$(bashio::config 'input_type')
DEVICE=$(bashio::config 'device')
TCP_HOST=$(bashio::config 'tcp_host')
TCP_PORT=$(bashio::config 'tcp_port')
BAUDRATE=$(bashio::config 'baudrate' 9600)
GPSD_OPTIONS=$(bashio::config 'gpsd_options') 
GPSD_OPTIONS="${GPSD_OPTIONS} --nowait --readonly --listenany"
GPSD_SOCKET="-F /var/run/gpsd.sock"
CHARSIZE=$(bashio::config 'charsize' 8)
PARITY=$(bashio::config 'parity' false)
STOPBIT=$(bashio::config 'stopbit' 1)
CONTROL="clocal"
MQTT_USER=$(bashio::config 'mqtt_username')
MQTT_PASSWORD=$(bashio::config 'mqtt_pw')
HA_AUTH=false

# stty expects -parenb to disable parity
if [ "$PARITY" = false ]; then
  PARITY_CL="-parenb"
elif [ "$PARITY" = true ]; then
  PARITY_CL="parenb"
fi

# stty expects -cstopb to set 1 stop bit per character, cstopb for 2
if [ "$STOPBIT" -eq 1 ]; then
  STOPBIT_CL="-cstopb"
elif [ "$STOPBIT" -eq 2 ]; then
  STOPBIT_CL="cstopb"
fi


MQTT_SERVICE_ATTEMPTS=24
MQTT_SERVICE_RETRY_DELAY=5

# True when the Supervisor offers an MQTT service. Queried directly rather than
# through bashio, which logs an error line per failed lookup.
mqtt_service_ready() {
    curl -sf -o /dev/null \
        -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
        "http://supervisor/services/mqtt"
}

# The Supervisor reports no MQTT service for a while when the add-on starts
# before the broker, so one failed lookup is not conclusive.
wait_for_mqtt_service() {
    local attempt
    for attempt in $(seq 1 ${MQTT_SERVICE_ATTEMPTS}); do
        if mqtt_service_ready; then
            return 0
        fi
        echo "Waiting for the MQTT service from the Supervisor (${attempt}/${MQTT_SERVICE_ATTEMPTS}) ..."
        sleep ${MQTT_SERVICE_RETRY_DELAY}
    done
    return 1
}

# Check if mqtt username is set, if not get it from Home Assistant via bashio::services
if bashio::config.is_empty 'mqtt_username'; then
    if wait_for_mqtt_service; then
        MQTT_USER="$(bashio::services 'mqtt' 'username')"
        MQTT_PASSWORD="$(bashio::services 'mqtt' 'password')"
        HA_AUTH=true
    else
        echo "ERROR: The Supervisor offered no MQTT service after $((MQTT_SERVICE_ATTEMPTS * MQTT_SERVICE_RETRY_DELAY)) seconds."
        echo "ERROR: Install the Mosquitto broker add-on, or set MQTT Username and MQTT Password in the configuration to use your own broker."
        exit 1 # Exit the script as we will not be able to authenticate to MQTT
    fi
fi

if [ "$INPUT_TYPE" = "serial" ]; then
    echo "Setting up serial device with the following: ${DEVICE} ${BAUDRATE} cs${CHARSIZE} ${STOPBIT_CL} ${PARITY_CL} ${CONTROL}"
    /bin/stty -F ${DEVICE} raw ${BAUDRATE} cs${CHARSIZE} ${PARITY_CL} ${CONTROL} ${STOPBIT_CL}
    echo "Starting GPSD with serial device \"${DEVICE}\"..."
    /usr/sbin/gpsd --version
    /usr/sbin/gpsd ${GPSD_OPTIONS} -s ${BAUDRATE} ${DEVICE}
elif [ "$INPUT_TYPE" = "tcp" ]; then
    if [ -z "$TCP_HOST" ] || [ -z "$TCP_PORT" ]; then
        echo "ERROR: tcp_host and tcp_port must both be set when input_type is tcp."
        exit 1
    fi
    echo "Starting GPSD with TCP source ${TCP_HOST}:${TCP_PORT} ..."
    /usr/sbin/gpsd --version
    /usr/sbin/gpsd ${GPSD_OPTIONS} tcp://${TCP_HOST}:${TCP_PORT}
else
    echo "Unknown input_type: $INPUT_TYPE"
    exit 1
fi

#echo "Checking device settings"
#/usr/bin/gpsctl

# Start python script to publish results from GPSD to MQTT
if [ "$HA_AUTH" = true ]; then
    echo "Starting MQTT Publisher with integrated credentials ... "
else
    echo "Starting MQTT Publisher with username ${MQTT_USER} ... "
fi

# Python is unpinned and follows the Alpine base; log which one is running.
echo "Using $(python3 --version 2>&1)"

# Credentials go through the environment rather than the command line: argv
# would expose the password in `ps`, and an unquoted password containing spaces
# would be split into separate arguments.
export MQTT_USER
export MQTT_PASSWORD

# exec so python replaces this shell as the process the supervisor signals --
# otherwise bash sits in wait() and never forwards SIGTERM, and the add-on only
# stops when it gets SIGKILLed.
exec python /gpsd2mqtt.py


# Config file for gpsd server
#usage: gpsd [OPTIONS] device...
#
#  Options include:
#  -?, -h, --help            = help message
#  -b, --readonly            = bluetooth-safe: open data sources read-only
#  -D, --debug integer       = set debug level, default 0
#  -F, --sockfile sockfile   = specify control socket location, default none
#  -f, --framing FRAMING     = fix device framing to FRAMING (8N1, 8O1, etc.)
#  -G, --listenany           = make gpsd listen on INADDR_ANY
#  -l, --drivers             = list compiled in drivers, and exit.
#  -n, --nowait              = don't wait for client connects to poll GPS
#  -N, --foreground          = don't go into background
#  -P, --pidfile pidfile     = set file to record process ID
#  -p, --passive             = do not reconfigure the receiver automatically
#  -r, --badtime             = use GPS time even if no fix
#  -S, --port PORT           = set port for daemon, default 2947
#  -s, --speed SPEED         = fix device speed to SPEED, default none
#  -V, --version             = emit version and exit.