# GPSD to MQTT (Beta)

> **This is the development channel and is not intended for general use.**
> Install the stable [GPSD to MQTT](../gpsd2mqtt) add-on instead.

This is a [gpsd — a GPS service daemon](https://gpsd.gitlab.io/gpsd/) to MQTT Home Assistant add-on.

It runs gpsd and publishes the position to MQTT as a device tracker
(`device_tracker.gps_location`), so Home Assistant's home zone can follow your
actual position and automations can act on it. Mosquitto is the expected broker,
but another one can be configured.

Changes land here first, get tested, and are then promoted to the stable add-on
with `./rsync.sh`.

See [DOCS.md](./DOCS.md) for setup, all configuration options, the entities the
add-on creates, and an example automation.
