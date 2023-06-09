import json
import datetime
import logging
import paho.mqtt.client as mqtt
from gpsdclient import GPSDClient

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
mqtt_config = data.get("mqtt_config", "homeassistant/device_tracker/gpsd/config")
mqtt_state = data.get("mqtt_state", "gpsd/state")
mqtt_attr = data.get("mqtt_attr", "gpsd/attribute")
debug = data.get("debug", False)
# Variables used to publish updates to the
summary_interval = data.get("summary_interval") or 120 # Interval in seconds
publish_interval = data.get("publish_interval") or 10
published_updates = 0
last_summary_time = datetime.datetime.now()
last_published_time = datetime.datetime.now()
result = None

# Set up logging
logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
logger = logging.getLogger("MQTT Publisher")

# Print the variables in use
logger.debug('These are the options in use.')
logger.debug('Serial device: ' + device)
logger.debug('Device Baudrate: ' + str(baudrate))
logger.debug('MQTT Hostname: ' + mqtt_broker)
logger.debug('MQTT TCP Port: ' + str(mqtt_port))
logger.debug('MQTT Username: ' + mqtt_username)
logger.debug('MQTT Password: ' + mqtt_pw)
logger.debug('Publish interval:' + str(publish_interval))
logger.debug('Summary interval:' + str(summary_interval))
logger.debug('Debug enabled: ' + str(debug))


# Next, define the necessary callback functions for the MQTT client
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
    else:
        logger.error("Failed to connect, return code: " + str(rc))

def on_disconnect(client, userdata, rc):
    logger.info("Disconnected from MQTT broker")

def on_log(client, userdata, level, buf):
    logger.debug(buf)

def on_message(client, userdata, msg):
    logger.debug("Received message: " + msg.topic + " " + str(msg.payload))

# Now, create an instance of the MQTT client and set up the appropriate callbacks:
client = mqtt.Client()

# Set the callback functions
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_log = on_log
client.on_message = on_message

# Set username and password, and connect to MQTT
client.username_pw_set(mqtt_username, mqtt_pw)
client.connect(mqtt_broker, mqtt_port)

# Create the device using the Home Assistant discovery protocol and set the state not_home
json_config = '''{{
    "state_topic": "{mqtt_state}",
    "unique_id": "gpsd_mqtt",
    "name": "GPS Location",
    "platform": "mqtt",
    "json_attributes_topic": "{mqtt_attr}"
}}'''.format(mqtt_state=mqtt_state, mqtt_attr=mqtt_attr)

client.publish(mqtt_config, json_config)
logger.info(f"Published MQTT discovery message to topic: {mqtt_attr}")
#client.publish(mqtt_state, "not_home") # Reset state to not_home on startup

# Main program loop
while True:
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