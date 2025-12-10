# Changelog

## [2025.12.0] - 2025-12-10
- Add option to connect to TCP based device for GPS data
- Upgrade to version 3.26.1 of GPSD
- Upstream changes:
  - Bump docker/login-action from 3.3.0 to 3.4.0
  - Bump home-assistant/builder from 2024.08.2 to 2025.11.0
  - Bump actions/checkout from 5 to 6
  - Bump frenck/action_addon_linter from 2.18 to 2.21
  - Remove arch support for armhf, armv7 and i386 no longer supported as of Home Assistant 2025.12


## [2025.7.0] - 2025-07-21
- Apparmor fix,  add network capability. Thanks for PR from @cbiffle #46 
- Upstream changes:
  - Bump actions/checkout from 4.1.7 to 4.2.2
  - Bump frenck/action-addon-linter from 2.15 to 2.18

<details>
<summary>Older changes</summary>

## [2024.9.0] - 2024-09-03
 - Added optional debug logging to check if all attributes received gets published to MQTT
 - Added logic to make sure attributes track and magtrack does not expire in Home Assistant even if not reported for an extended period, this can happen if the GPS is stationary
 - Merged upstream PR changes (builder)
 - Change to fix that disabling the interval for publishing updates defaulted to 10 (setting config option to 0)

## [2024.7.0] - 2024-07-25
 - Changes done to Apparmor to fix permissions error causing problem for certain USB GPS devices
 - Removed settings for sock, should not be needed
 
## [2024.4.4] - 2024-05-28
 - Reworked changes that broke republishing of MQTT devices after HA reboot

## [2024.4.3] - 2024-05-26
 - Small fixes

## [2024.4.2] - 2024-04-17
 - Added option to configure required number of satellites to establish the position. 3D fix is 3 satellites, but sometimes you need a more accurate position rather than frequent updates. Setting this to 5, or even 6 or 7 will greatly increase the accuracy of the position reported to device_tracker. Note that the updated position frequency could be reduced if the GPS sensor has bad coverage, especially the first minutes after the add-on is started. You will then get 0 new updates in the log, but be patient and it will start reporting if the coverage is good enough
 - Introduced a new sensor for Sky data. Under Settings -> Integrations -> Entities (MQTT) -> GPSD Service. This device shows the Sky coverage data as attributes. The sensor is called sensor.gpsd_service_sky_data and the state is the current number of satellites used to establish position

## [2024.4.1] - 2024-04-10
 - NEW OPTION: No username or password required for MQTT if using Mosquitto on Home Assistant. If you use custom username / password this can be deleted if the previous is true
 - NEW OPTION: Add option to only publish when good GPS fix is achieved, and made it default. Option called "3D Fix Only". Turn it off if you like to get all updates
 - Fix the configurable publish interval setting. This is 10 seconds default, can be changed in options, set to 0 to publish all updates. Did not work in previous releases
 - Many small fixes and improvements


## [2024.4.0] - 2024-04-01
 - Reworked addon to listen for LWT messages from Home Assistant. This ensures that the device tracker gets discovered after reboots
 - Changed the discovery message so it becomes a device under MQTT and shows in the devices dashboard (config/devices/dashboard)
 - Added unique ID to discovery message, enabling the user to edit the device
 - Added automation example to github readme

## [2024.2.1] - 2024-02-18
 - Fixing bug, not updating MQTT in 2024.2.0

## [2024.2.0] - 2024-02-18
 - Setting baudrate directly to GPSD binary option, defaults to 9600 without it

## [2024.1.0] - 2024-01-27
 - Improved serial device handling, added som more debugging
 - Merged upstream changes from Home Assistant builder

## [2023.8.0] - 2023-08-28

- Updated and improved logging with timestamps
- Improved MQTT connection resilience, and introdused a reconnect feature
- Merged upstream changes from Home Assistant builder

## [2023.6.2] - 2023-06-09

- BREAKING CHANGE!! Improved security of addon by disabling listening to GPSD port, that is not needed for MQTT. The port is an optional config option if anyone wants to use the addon to talk to GPSD directly
- Improved security of addon by implementing CAS signing and apparmour
- Merged upstream changes from Home Assistant builder
- Merged upstream changes from Home Assistant builder

### Changed

## [2023.6.1] - 2023-06-09

### Changed

- Changes done to state. It no longer posts the GPS accuracy as state, but should use the zone settings from Home Assistant (home, not_home)
- Changes to logging, now debug and info should be more visible in the logs
- Made a summary message in the log so you can get some information withouth overloading the log with info
- Configurable options to control how often updates are published to MQTT and also how often to get the summary in the log. Se options under optional config options (Publish Interval and Print Summary)
- Changed the versioning numbering to align with Home Assistant versioning

## [0.0.108] - 2023-06-07

### Changed

- Changes to check if lat/lon/lat is sent before rewriting attribute names
- Some changes to logging, still not perfect, needs more work

## [0.0.107] - 2023-06-06

### Changed

- Breaking change in attributes, renamed lat to latitude, lon to longitude and alt to altitude. This change done to get location to work in Home Assistant for the device_tracker
- Changes done to logging. If debug is off then the script will publish a log every X seonds (120s this release) to not clutter the logs more than necessary

## [0.0.106] - 2023-06-01

### Added

- Updated readme from h0bbel


## [0.0.105] - 2023-06-01

### Added

- Changed username and password for MQTT to mandatory


## [0.0.103] - 2023-06-01

### Added

- Changed username and password for MQTT to mandatory

## [0.0.102] - 2023-06-01

### Added

- Compiled images and published

## [0.0.101] - 2023-05-30

### Added

- Small fixes

## [0.0.101] - 2023-05-30

### Added

- Small fixes

## [Unreleased]

## [0.0.99] - 2023-05-29

### Added

- First release added

</details>
