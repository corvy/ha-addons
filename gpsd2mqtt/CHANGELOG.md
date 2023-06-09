# Changelog

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



