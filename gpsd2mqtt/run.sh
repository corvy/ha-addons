#!/usr/bin/with-contenv bashio

# Get the device config
CONFIG_PATH="/data/options.json"
DEVICE=$(bashio::config 'device')
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


# Check if mqtt username is set, if not get it from Home Assistant via bashio::services
if bashio::config.is_empty 'mqtt_username' && bashio::var.has_value "$(bashio::services 'mqtt')"; then
    MQTT_USER="$(bashio::services 'mqtt' 'username')"
    MQTT_PASSWORD="$(bashio::services 'mqtt' 'password')"
    HA_AUTH=true
elif bashio::config.is_empty 'mqtt_username'; then
    echo "ERROR: Not able to use HA integrated authentication, and no credentials manually configured. "
    echo "ERROR: Please update configuration with your own credentials to continue."
    exit 1 # Exit the script as we will not be able to authenticate to MQTT
fi

# Serial setup
#
# For serial interfaces, options such as low_latency are recommended
# Also, http://catb.org/gpsd/upstream-bugs.html#tiocmwait recommends
#   setting the baudrate with stty
# Uncomment the following lines if using a serial device:
#

echo "Setting up serial device with the following: ${DEVICE} ${BAUDRATE} cs${CHARSIZE} ${STOPBIT_CL} ${PARITY_CL} ${CONTROL}"
/bin/stty -F ${DEVICE} raw ${BAUDRATE} cs${CHARSIZE} ${PARITY_CL} ${CONTROL} ${STOPBIT_CL}
# /bin/setserial ${DEVICE} low_latency

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

echo "Starting GPSD with device \"${DEVICE}\"..."
/usr/sbin/gpsd --version
/bin/su /usr/sbin/gpsd ${GPSD_OPTIONS} -s ${BAUDRATE} ${DEVICE}

#echo "Checking device settings"
#/usr/bin/gpsctl

# Start python script to publish results from GPSD to MQTT
if [ $HA_AUTH = true ]; then
    echo "Starting MQTT Publisher with integrated credentials ... "
    else
    echo "Starting MQTT Publisher with username ${MQTT_USER} ... "
fi
    
python /gpsd2mqtt.py ${MQTT_USER} ${MQTT_PASSWORD}