# GPSD to MQTT

This is a [gpsd — a GPS service daemon](https://gpsd.gitlab.io/gpsd/) to MQTT Home Assistant Addon.

This addon will run GPSD and serve the data to MQTT and show a device tracker device (device_tracker.gpsd_location). The addon uses Mosquitto MQTT but can also be configued to another broker if wanted.

Remember to install Mosquitto or another broker before setting up this addon.

Installation requires you to set up a username and password to publish to MQTT. Also you must select the serial device for GPSD in the configuration.

The configuration is done via editing the options: section of [config.yaml](config.yaml):

```
options:
  device: null
  mqtt_username: "mqtt"
  mqtt_pw: "changeme"
```