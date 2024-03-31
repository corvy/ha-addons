import json
import datetime
import logging
import time
import serial
import platform
import hashlib
import signal
import sys
import paho.mqtt.client as mqtt
from gpsdclient import GPSDClient

# To make sure Home Assistant gets a uniique identifier, we use this section to crate a simple 8 character UID
def get_unique_identifier():
    system_info = platform.uname()

    unique_identifier = "-".join([
        system_info.node,  # Hostname - increase the chance of uniqueness
        system_info.system,  # System - e.g. Windows or Linux
        system_info.machine,  # Machine - for instance x86
    ])

    # Hash the combined attributes using SHA-256
    hashed_identifier = hashlib.sha256(unique_identifier.encode()).hexdigest()

    # Truncate the hash to 8 characters
    truncated_identifier = hashed_identifier[:8]

    return truncated_identifier


# Get a unique identifier for the MQTT configuration topic
unique_identifier = get_unique_identifier()

# Read the config options from the JSON file
with open("/data/options.json", "r") as jsonfile:
    data = json.load(jsonfile)
    
# Replace the variables with the values from the config options
device = data.get("device")
baudrate = data.get("baudrate") or 9600
mqtt_broker = data.get("mqtt_broker") or "core-mosquitto"
mqtt_port = data.get("mqtt_port") or 1883
mqtt_username = data.get("mqtt_username") or "addons"
mqtt_pw = data.get("mqtt_pw") or ""
# Default confiuration options, should normally not be changed
mqtt_config = data.get("mqtt_config", "homeassistant/device_tracker/gpsd2mqtt/" + unique_identifier + "/config")
mqtt_state = data.get("mqtt_state", "gpsd2mqtt/" + unique_identifier + "/state")
mqtt_attr = data.get("mqtt_attr", "gpsd2mqtt/" + unique_identifier + "/attribute")
debug = data.get("debug", False)
# Variables used to publish updates to the
summary_interval = data.get("summary_interval") or 120 # Interval in seconds
publish_interval = data.get("publish_interval") or 10
published_updates = 0
last_summary_time = datetime.datetime.now()
last_published_time = datetime.datetime.now()
result = None

# Define parameters for exponential backoff
RECONNECT_DELAY_BASE = 5  # Initial delay in seconds
MAX_RECONNECT_ATTEMPTS = 10  # Maximum number of reconnection attempts

# Set up logging, adding timestamp to the logs
logging.basicConfig(
    level=logging.DEBUG if debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Adding %(asctime)s for timestamp
)
# Define parameters for exponential backoff
RECONNECT_DELAY_BASE = 5  # Initial delay in seconds
MAX_RECONNECT_ATTEMPTS = 10  # Maximum number of reconnection attempts


# Set up logging, adding timestamp to the logs
logging.basicConfig(
    level=logging.DEBUG if debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Adding %(asctime)s for timestamp
)
logger = logging.getLogger("MQTT Publisher")

# Print the variables in use
logger.debug('These are the options in use.')
logger.debug('Serial device: ' + device)
logger.debug('Device Baudrate: ' + str(baudrate))
logger.debug('MQTT Hostname: ' + mqtt_broker)
logger.debug('MQTT TCP Port: ' + str(mqtt_port))
logger.debug('MQTT Username: ' + mqtt_username)
logger.debug('MQTT Password: ' + mqtt_pw)
logger.debug('MQTT Config: ' + mqtt_config)
logger.debug('MQTT State: ' + mqtt_state)
logger.debug('MQTT Attribute: ' + mqtt_attr)
logger.debug('Publish interval: ' + str(publish_interval))
logger.debug('Summary interval: ' + str(summary_interval))
logger.debug('Debug enabled: ' + str(debug))
logger.debug('Unique ID: ' + unique_identifier)

# Now, create an instance of the MQTT client and set up the appropriate callbacks:
client = mqtt.Client()

# Set username and password, and connect to MQTT
client.username_pw_set(mqtt_username, mqtt_pw)
client.connect(mqtt_broker, mqtt_port)

def shutdown():
    # Publish blank config to delete entities configured but the addon
    logger.info("Shutdown detected, cleaning up.")
    client.publish(mqtt_config)

def signal_handler(sig, frame):
    # Handle shutdown signal
    shutdown()
    client.disconnect()
    sys.exit(0)

# Register signal handler for SIGTERM and SIGINT
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Create the device using the Home Assistant discovery protocol and set the state not_home
json_config = f'''
{{
    "state_topic": "{mqtt_state}",
    "unique_id": "{unique_identifier}",
    "name": "Device Tracker",
    "platform": "mqtt",
    "payload_home": "home",
    "payload_not_home": "not_home",
    "payload_reset": "check_zone",
    "json_attributes_topic": "{mqtt_attr}",
    "device": {{
        "name": "GPSD Service",
        "identifiers": "gpsd2mqtt_{unique_identifier}", 
        "configuration_url": "https://github.com/corvy/ha-addons/tree/main/gpsd2mqtt",
        "model": "gpsd2MQTT",
        "manufacturer": "GPSD and @sbarmen"
    }}
}}
'''

client.publish(mqtt_config, json_config)
#client.publish(mqtt_config, json_config, retain=True)

logger.info(f"Published MQTT discovery message to topic:" + mqtt_config)
logger.info(f"Published MQTT State to not_home to:" + mqtt_state)
logger.debug(f"Published {json_config} discovery message to topic: {mqtt_config}")

# Next, define the necessary callback functions for the MQTT client
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
    else:
        logger.error("Failed to connect, return code: " + str(rc))

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning("Disconnected from MQTT broker. Attempting reconnection...")
        reconnect_to_mqtt()

def reconnect_to_mqtt():
    attempt = 1
    while attempt <= MAX_RECONNECT_ATTEMPTS:
        try:
            logger.info("Trying to reconnect to MQTT broker (attempt {} of {})...".format(attempt, MAX_RECONNECT_ATTEMPTS))
            client.reconnect()
            break  # If reconnection successful, exit the loop
        except Exception as e:
            logger.error("Failed to reconnect to MQTT broker: " + str(e))
        
        # Calculate the delay using exponential backoff formula
        reconnect_delay = RECONNECT_DELAY_BASE * (2 ** (attempt - 1))
        logger.info("Waiting {} seconds before next reconnection attempt...".format(reconnect_delay))
        time.sleep(reconnect_delay)
        attempt += 1
    
    if attempt > MAX_RECONNECT_ATTEMPTS:
        logger.error("Exceeded maximum reconnection attempts. Giving up.")

def on_message(client, userdata, msg):
    logger.debug("Received message: " + msg.topic + " " + str(msg.payload))
    if msg.topic == "homeassistant/status" and msg.payload.decode() == "online":
        # Resend the MQTT discovery message
        client.publish(mqtt_config, json_config)
        logger.info("Re-sent MQTT discovery message due to Home Assistant reboot")

def on_log(client, userdata, level, buf):
    logger.debug(buf)

#def on_message(client, userdata, msg):
#    logger.debug("Received message: " + msg.topic + " " + str(msg.payload))

# Set the callback functions
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_log = on_log
# client.on_message = on_message

# Main program loop
while True:
    # Check connection and perform reconnection if needed
    if not client.is_connected():
        reconnect_to_mqtt()

    # Check connection and perform reconnection if needed
    if not client.is_connected():
        reconnect_to_mqtt()

    client.loop(timeout=1) # Process MQTT messages with a 1-second timeout


    with GPSDClient(host="127.0.0.1") as gps_client:

        for raw_result in gps_client.json_stream():
            result = json.loads(raw_result)
            if result.get("class") == "TPV":
                mode = result.get("mode")
                if mode == 1:
                    accuracy = "No fix"
                elif mode == 2:
                    accuracy = "2D fix"
                elif mode == 3:
                    accuracy = "3D fix"
                else:
                    accuracy = "Unknown"
                
                result["accuracy"] = accuracy

                # Modify the attribute names so Home Assistant gets position in the device_tracker 
                # (it expects longitute/latitude/altitude)
                if "alt" in result and result["alt"] is not None:
                    result["altitude"] = result.pop("alt")
                if "lon" in result and result["lon"] is not None:
                    result["longitude"] = result.pop("lon")
                if "lat" in result and result["lat"] is not None:
                    result["latitude"] = result.pop("lat")

                ## Publish the GPS accurancy to the state_topic
                # client.publish(mqtt_state, accuracy)
                
                # Publish the JSON message to the MQTT broker
                if (datetime.datetime.now() - last_published_time).total_seconds() >= publish_interval:
                    client.publish(mqtt_attr, json.dumps(result))
                    published_updates += 1 # Add one per publish for the summary log 
                    logger.debug(f"Published: {result} to topic: {mqtt_attr}")
                    last_published_time = datetime.datetime.now()

            # Check if a summary should be printed
            if (datetime.datetime.now() - last_summary_time).total_seconds() >= summary_interval:
                # Calculate the time elapsed since the last summary
                time_elapsed = (datetime.datetime.now() - last_summary_time).total_seconds() // 60

                # Print the summary message
                summary_message = f"Published {published_updates} updates in the last {time_elapsed} minutes"
                logger.info(summary_message)

                # Reset the counters
                published_updates = 0
                last_summary_time = datetime.datetime.now()

# Stop the MQTT network loop
client.disconnect()