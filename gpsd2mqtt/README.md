# GPSD to MQTT

This is a [gpsd — a GPS service daemon](https://gpsd.gitlab.io/gpsd/) to MQTT Home Assistant Addon.

This addon will run gpsd and serve the data to MQTT and show a device tracker device (device_tracker.gpsd_location). The addon uses Mosquitto MQTT but can also be configued to use another broker if wanted. The idea is to update the home zone in Home Assistant with the actual position from gpsd, in order to run automations based on actual position.

Remember to install Mosquitto or another broker before setting up this addon.

If using Mosquitto on Home Assistant, the addon will use integrated authentication to log in. Normally you should not need to configure username or password for MQTT. If you have set up a custom MQTT broker, you must manually configure username and password (and potentially more).

Also you must select the serial device for GPSD in the configuration.

The configuration is done via the addon GUI inside Home Assistant after installation.

## Example automation to dynamically update position

    alias: Dynamic Update Home
    description: Update the Home location for Home Assistant based on GPS information
    trigger:
      - platform: state
        entity_id:
          - device_tracker.gps_location
        attribute: latitude
      - platform: state
        entity_id:
          - device_tracker.gps_location
        attribute: longitude
    condition: []
    action:
      - service: homeassistant.set_location
        data_template:
          latitude: "{{ state_attr('device_tracker.gps_location', 'latitude') }}"
          longitude: "{{ state_attr('device_tracker.gps_location', 'longitude') }}"
    mode: single
