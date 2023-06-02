import json
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
debug = data.get("debug")

# Print the variables in use
if debug:
    print('These are the options in use.')
    print('Serial device: ' + device)
    print('Device Baudrate: ' + str(baudrate))
    print('MQTT Hostname: ' + mqtt_broker)
    print('MQTT TCP Port: ' + str(mqtt_port))
    print('MQTT Username: ' + mqtt_username)
    print('MQTT Password: ' + mqtt_pw)
    print('Debug enabled: ' + str(debug))

# Next, define the necessary callback functions for the MQTT client
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
    else:
        print("Failed to connect, return code: " + str(rc))

def on_disconnect(client, userdata, rc):
    print("Disconnected from MQTT broker")

def on_log(client, userdata, level, buf):
    print(buf)

def on_message(client, userdata, msg):
    if debug:
        print("Received message: " + msg.topic + " " + str(msg.payload))


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

# Start the network loop to handle incoming and outgoing messages
client.loop_start()

with GPSDClient(host="127.0.0.1") as gps_client:
    for raw_result in gps_client.json_stream():
        result = json.loads(raw_result)
        if result.get("class") == "TPV":
            mode = result.get("mode")
            if mode == 1:
                state = "No fix"
            elif mode == 2:
                state = "2D fix"
            elif mode == 3:
                state = "3D fix"
            else:
                state = "Unknown"

            # Publish the GPS accurancy to the state_topic
            client.publish(mqtt_state, state)
            # Publish the JSON message to the MQTT broker
            client.publish(mqtt_attr, json.dumps(result))
            if debug:
                # Print the published message for verification
                print(f"Published: {result} to topic: {mqtt_attr}")
    
# Start the MQTT network loop (keeps the client connected)
client.loop_forever()