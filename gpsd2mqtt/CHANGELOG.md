# Changelog

## [2024.4.1] - 2024-04-01
 - Add option to only publish rwhen good GPS fix is achieved, and made it default. Option called "3D Fix Only"

## [2024.4.0] - 2024-04-01
 - Reworked addon to listen for LWT messages from Home Assistant. This ensures that the device tracker gets discovered after reboots.
 - Changed the discovery message so it becomes a device under MQTT and shows in the devices dashboard (config/devices/dashboard)
 - Added unique ID to discovery message, enabling the user to edit the device
 - Added automation example to github readme

## [2024.2.1] - 2024-02-18
 - Fixing bug, not updating MQTT in 2024.2.0.

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
- Changes to logging, now debug and info should be more visible in the logs. 
- Made a summary message in the log so you can get some information withouth overloading the log with info. 
- Configurable options to control how often updates are published to MQTT and also how often to get the summary in the log. Se options under optional config options (Publish Interval and Print Summary).
- Changed the versioning numbering to align with Home Assistant versioning.  

## [0.0.108] - 2023-06-07

### Changed

- Changes to check if lat/lon/lat is sent before rewriting attribute names
- Some changes to logging, still not perfect, needs more work

## [0.0.107] - 2023-06-06

### Changed

- Breaking change in attributes, renamed lat to latitude, lon to longitude and alt to altitude. This change done to get location to work in Home Assistant for the device_tracker. 
- Changes done to logging. If debug is off then the script will publish a log every X seonds (120s this release) to not clutter the logs more than necessary.

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



