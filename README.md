# Stian B. Barmens Home Assistant App repository

This App repository was made to publish my first App, since I was missing one that ran GPSD and published updated status to MQTT.

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fcorvy%2Fha-addons)

## Support the work I do
If you want to show your support for the efforts I make in supporting these Apps, please buy me a coffee!
[<img src="https://miro.medium.com/v2/resize:fit:320/format:webp/1*LUqcagBr2LbRg2GHZKQUJg.png">](https://buymeacoffee.com/sbarmen)

## Apps

This repository contains the following Apps.

### [GPSD to MQTT](./gpsd2mqtt)

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

Run gpsd and publish the position to MQTT as a device tracker. This is the one to install.

### [GPSD to MQTT Beta](./gpsd2mqtt_beta)

Development channel for the App above, flagged `experimental`. Not intended for general use — install the stable version instead.

## Development

Changes are made in `gpsd2mqtt_beta/` and promoted to `gpsd2mqtt/` by running
`./rsync.sh` from inside that directory. `config.yaml`, `CHANGELOG.md`,
`README.md` and the rsync files themselves stay separate between the two — see
`gpsd2mqtt_beta/exclude_list.txt`.

Remember to bump the `version` key in the relevant `config.yaml` and add a
`CHANGELOG.md` entry; the builder workflow publishes a new image whenever
`config.yaml`, `Dockerfile` or `build.yaml` changes.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
