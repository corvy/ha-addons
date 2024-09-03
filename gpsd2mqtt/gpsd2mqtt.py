import json
import datetime
import logging
import time
import platform
import hashlib
import signal
import sys
import paho.mqtt.client as mqtt  # type: ignore
from gpsdclient import GPSDClient  # type: ignore

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


# Read the config options from the JSON file
with open("/data/options.json", "r") as jsonfile:
    data = json.load(jsonfile)
    
# Replace the variables with the values from the config options
device = data.get("device")
baudrate = data.get("baudrate") or 9600
mqtt_broker = data.get("mqtt_broker") or "core-mosquitto"
mqtt_port = data.get("mqtt_port") or 1883
mqtt_username = sys.argv[1] or data.get("mqtt_username")
mqtt_config = None
# mqtt_username = data.get("mqtt_username") or "addons"
mqtt_pw = sys.argv[2] or data.get("mqtt_pw")
# Default confiuration options, should normally not be changed
publish_3d_fix_only = data.get("publish_3d_fix_only", True)  # Default to True to reduce "unknown" positions
min_n_satellites = data.get("min_n_satellites") or 0 # Default to 0 (all results) 
debug = data.get("debug", False)
# Variables used to publish updates to the
summary_interval = data.get("summary_interval") or 120 # Interval in seconds
publish_interval = data.get("publish_interval") 
if publish_interval is None:
    publish_interval = 10  # Default to 10 Interval in seconds
published_updates = 0
last_summary_time = datetime.datetime.now()
last_publish_time = datetime.datetime.now()
result = None

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
logger.debug('Publish interval: ' + str(publish_interval))
logger.debug('Summary interval: ' + str(summary_interval))
logger.debug('Debug enabled: ' + str(debug))


# Define the necessary callback functions for the MQTT client
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        # Subscribe to the homeassistant/status topic. This ensures the script detects 
        # HA reboots and then resubmits the discovery mesage
        client.subscribe("homeassistant/status")
        logger.info("Subscribe to MQTT topic homeassistant/status to listen for HA reboots.")
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
            # If reconnection successful, subscribe to 
            # the necessary topics and exit the loop
            client.subscribe("homeassistant/status")
            logger.info("Reconnect successful, resubscribing to necessary topics.")
            break  
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
        publish_json_configs()
        logger.info("Home Assistant reboot detected. Re-sent MQTT discovery message.")

def on_log(client, userdata, level, buf):
    logger.debug(buf)

# Now, create an instance of the MQTT client and set up the appropriate callbacks:
client = mqtt.Client()

# Set the callback functions
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_log = on_log
client.on_message = on_message

# set the username and password for MQTT
client.username_pw_set(mqtt_username, mqtt_pw)

client.loop_start()
logger.info("Connecting to MQTT broker")
client.connect(mqtt_broker, mqtt_port)

# Pause to make sure MQTT is connected before resuming
while not client.is_connected():
    time.sleep(1) 
    logger.info("Verifying MQTT Connection ....")

# Not sure we need this part, commenting out for now
# def shutdown():
#    # Publish blank config to delete entities configured but the addon
#    logger.info("Shutdown detected, cleaning up.")
#    # client.publish(mqtt_config)

# def signal_handler(sig, frame):
#    # Handle shutdown signal
#    shutdown()
#    client.disconnect()
#    sys.exit(0)

# Register signal handler for SIGTERM and SIGINT
# signal.signal(signal.SIGTERM, signal_handler)
# signal.signal(signal.SIGINT, signal_handler)

def publish_json_configs():
    unique_identifier = get_unique_identifier()
    mqtt_config_deprecated = "homeassistant/device_tracker/gpsd/config"
    mqtt_config = f"homeassistant/device_tracker/gpsd2mqtt/{unique_identifier}/config"
    # mqtt_state = f"gpsd2mqtt/{unique_identifier}/state"
    mqtt_attr = f"gpsd2mqtt/{unique_identifier}/attribute"
    mqtt_sky_config = f"homeassistant/sensor/gpsd2mqtt/{unique_identifier}_sky/config"
    mqtt_sky_state = f"gpsd2mqtt/{unique_identifier}_sky/state"
    mqtt_sky_attr = f"gpsd2mqtt/{unique_identifier}_sky/attribute"

    logger.debug('Unique ID: ' + unique_identifier)
    logger.debug('MQTT Config: ' + mqtt_config)
    # logger.debug('MQTT State: ' + mqtt_state)
    logger.debug('MQTT Attribute: ' + mqtt_attr)

    # Create the device using the Home Assistant discovery protocol and set the state not_home
    # "state_topic": "{mqtt_state}", (Removed from json_config)
    # Serialize JSON objects separately
    json_config_device_tracker = f'''
    {{
        "unique_id": "{unique_identifier}",
        "name": "Location",
        "platform": "mqtt",
        "json_attributes_topic": "{mqtt_attr}",
        "payload_home": "home",
        "payload_not_home": "not_home",
        "payload_reset": "check_zone",
        "object_id": "gps_location",
        "icon":"mdi:map-marker",
        "device": {{
            "name": "GPSD Service",
            "identifiers": "gpsd2mqtt_{unique_identifier}", 
            "configuration_url": "https://github.com/corvy/ha-addons/tree/main/gpsd2mqtt",
            "model": "gpsd2MQTT",
            "manufacturer": "GPSD and @sbarmen"
        }}
    }}
    '''

    json_config_sensor = f'''
    {{
        "unique_id": "{unique_identifier}_sky",
        "name": "Sky Data",
        "icon": "mdi:satellite-variant",
        "platform": "mqtt",
        "state_topic": "{mqtt_sky_state}",
        "json_attributes_topic": "{mqtt_sky_attr}",
        "device": {{
            "name": "GPSD Service",
            "identifiers": "gpsd2mqtt_{unique_identifier}"
        }}
    }}
    '''

    client.publish(mqtt_config_deprecated) # Empty config for deprecated device to cleanup
    client.publish(mqtt_config, json_config_device_tracker) # Publish the device tracker discovery message
    client.publish(mqtt_sky_config, json_config_sensor) # Publish the sensor discovery message

    logger.info(f"Published MQTT discovery message to topic: {mqtt_config}")
    logger.debug(f"Published {json_config_device_tracker} discovery message to topic: {mqtt_config}")
    logger.debug(f"Published {json_config_sensor} discovery message to topic: {mqtt_sky_config}")

    return mqtt_attr, mqtt_sky_state, mqtt_sky_attr

mqtt_attr, mqtt_sky_state, mqtt_sky_attr = publish_json_configs()

# Publish the serialized JSON objects
# Main program loop to update the device location from GPS
while True:

    # Check connection and perform reconnection if needed
    if not client.is_connected():
        reconnect_to_mqtt()

    logger.info("Starting location detection and sending GPS updates.")
    client.loop(timeout=1) # Process MQTT messages with a 1-second timeout

    with GPSDClient(host="127.0.0.1") as gps_client:

        tpv_publish_flag = False # Set to false, no updates until required number of satellites is found
        log_satellites = 0 # Initialize variable for log printing, want the highest seen satellites for the log round
        accuracy = None # Initialize variable, to ensure no error

        for raw_result in gps_client.json_stream():
            try:
                result = json.loads(raw_result)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON: {e}")
                continue

            # Log the entire result object
            logger.debug(f"RAW GPS data: {result}")

            if result.get("class") == "SKY":
                # USat is the current number of satellites used to calculate the position - the more the better
                n_satellites = result.get("uSat", 0)

                # Set the highest number of satellites used for positioning in this log round
                if log_satellites < n_satellites:
                    log_satellites = n_satellites

                # If the user has configured a minimum # of satellites needed for a "good position"
                if n_satellites >= min_n_satellites:
                    tpv_publish_flag = True
                else:
                    tpv_publish_flag = False

                logger.debug(f"Number of satellites: {n_satellites} of required {min_n_satellites}")
                logger.debug(f"Published SKY: {result} to topic: {mqtt_sky_attr}")
 
                # Publish SKY data
                if (datetime.datetime.now() - last_publish_time).total_seconds() >= publish_interval or publish_interval == 0:
                    client.publish(mqtt_sky_attr, json.dumps(result))
                    client.publish(mqtt_sky_state, str(n_satellites)) 
                    logger.debug(f"Published SKY: {str(n_satellites)} to topic: {mqtt_sky_state}")
                    logger.debug(f"Published SKY: {result} to topic: {mqtt_sky_attr}")

            if result.get("class") == "TPV" and tpv_publish_flag: # Check if it is TPV, and that we meet the minimum # of satellites
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

                # Track and magtrack are reported when GPSD starts, but will stop reporting when the GPS is stationary.
                # This will report 'null', but still send the attribute so it does not get expired in Home Assistant.
                if "track" not in result:
                    result["track"] = None 
                    logger.debug(f"Attribute track not in result, setting value to none")

                if "magtrack" not in result:
                    result["magtrack"] = None
                    logger.debug(f"Attribute magtrack not in result, setting value to none")

                logger.debug(f"Processed TPV Data: {result}")
            
                # Limit the GPS updates to the configured value, or publish all if disabled (0)
                if (datetime.datetime.now() - last_publish_time).total_seconds() >= publish_interval or publish_interval == 0:

                    logger.debug("Accuracy achieved:" + result["accuracy"])
                    # Publish the JSON message to the MQTT broker only if mode is 3D fix
                    if (publish_3d_fix_only and mode == 3):
                        client.publish(mqtt_attr, json.dumps(result))
                        published_updates += 1 # Add one per publish for the summary log 
                        logger.debug(f"Published TPV: {result} to topic: {mqtt_attr} (3D-fix-only)")
                        
                    elif not publish_3d_fix_only :
                        # If not filtering on 3D fix, we publish all updates
                        client.publish(mqtt_attr, json.dumps(result))
                        published_updates += 1 # Add one per publish for the summary log 
                        logger.debug(f"Published TPV: {result} to topic: {mqtt_attr}")
                    
                    last_publish_time = datetime.datetime.now()
                    
            
            # Check if a summary should be printed
            if (datetime.datetime.now() - last_summary_time).total_seconds() >= summary_interval:
                # Calculate the time elapsed since the last summary
                time_elapsed = (datetime.datetime.now() - last_summary_time).total_seconds() // 60

                # Print the summary message
                if log_satellites >= min_n_satellites:
                    summary_message = f"Published {published_updates} updates to the device_tracker in last {time_elapsed} minutes. Achieved {accuracy}, position with {log_satellites} of required {min_n_satellites} GPS satellites."
                else:
                    summary_message = f"Published {published_updates} updates to the device_tracker in last {time_elapsed} minutes. Achieved {accuracy}. Position not at configured accuracy with only {log_satellites} of required {min_n_satellites} GPS satellites."
                
                logger.info(summary_message)

                # Reset the counters
                published_updates = 0
                log_satellites = 0
                last_summary_time = datetime.datetime.now()

# Stop the MQTT network loop
client.disconnect()