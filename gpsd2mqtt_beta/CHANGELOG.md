# Changelog

## [2026.8.1b8] - 2026-08-05

### Changed
- No functional changes. This release only tidies comments in the source, corrects how the MQTT library pin is documented, and adds a test covering the publish rate limiter's clock

<details>
<summary>Older changes</summary>

## [2026.8.1b7] - 2026-08-04

### Changed
- No functional changes. This release only clears warnings from the container build

## [2026.8.1b6] - 2026-08-04

### Fixed
- Waiting for the MQTT broker no longer fills the log with errors. Starting before the broker is normal, and the add-on now reports only that it is waiting

### Changed
- The add-on waits up to 120 seconds for the MQTT service to appear, up from 60

## [2026.8.1b5] - 2026-08-04

### Changed
- No functional changes. This release only verifies the new container build process

## [2026.8.1b4] - 2026-08-03

### Fixed
- The entities no longer show as available for a while after every start before going unavailable again. They now stay unavailable until a position has actually been published, so a GPS that never produces one never claims to be working. What counts as a position follows your own **3D Fix Only** and **Required number of satellites** settings, and the log states which of them it is waiting for
- Once available, the entities stay available while the fix comes and goes. Only a GPS source that stops reporting altogether takes them unavailable, so poor sky no longer flaps them

## [2026.8.1b3] - 2026-08-03

### Fixed
- A GPS source that goes away while GPSD keeps running is now detected. GPSD carries on reporting satellite data with no position behind it, so the add-on kept publishing nothing while Home Assistant showed the last known position as if it were current. Both entities now go unavailable, and the add-on restarts to reconnect GPSD to the source
- The log summary no longer reports the last known fix long after it went stale. A summary interval with no position at all now says so
- The add-on waits for the MQTT service to appear instead of stopping at once when the Supervisor has not registered it yet, which could stop the add-on from starting after a reboot. The error when it really is missing now says what is actually wrong

### Added
- **GPS source timeout** and **GPS source restart multiplier** options control how long without a position before the entities go unavailable (default 10 minutes) and how many multiples of that before the add-on restarts (default 3, so 30 minutes). Set the multiplier to 0 to never restart, or the timeout to 0 to disable the check

### Changed
- The MQTT password is now masked in the add-on configuration instead of being shown in clear text

## [2026.8.1b2] - 2026-08-02

### Added
- The device tracker and Sky Data sensor now report availability. They show as unavailable when the add-on stops, whether it stops cleanly or crashes, and leave nothing behind on the broker when the add-on is uninstalled
- The add-on now reports itself unhealthy when GPSD stops responding, so enabling **Watchdog** on the Info tab restarts it automatically. Previously a dead GPSD left the add-on running and apparently healthy

### Fixed
- Publishing could stall for as long as the system clock was stepped backwards, which happens on installs where GPS is also used as a time source
- The entities are re-announced when the MQTT broker restarts, so they recover without restarting Home Assistant
- Wrong MQTT credentials now stop the add-on with a clear error instead of retrying silently forever
- Stopping the add-on no longer waits out the GPSD retry delay
- The add-on now gives up and restarts if GPSD produces no data at all for about a minute, instead of retrying indefinitely
- The log summary no longer reports "0.0 minutes" when the summary interval is under a minute

### Changed
- GPSD is now installed with a minimum version rather than an exact one, so a routine Alpine update no longer breaks the build at an arbitrary time
- The AppArmor profile no longer refers to a hardcoded Python version
- The startup log reports the Python version in use alongside the GPSD version

## [2026.8.1b1] - 2026-08-02

### Changed
- No functional change to the add-on. This beta exists to exercise the automated GitHub release workflow and the rewritten changed-file detection in the build workflow for the first time, before either is relied on for a release carrying real changes

### Added
- Automated tests and linting now run on every pull request, covering option parsing, GPS report transformation, publish throttling and the MQTT discovery payloads. Test code is not part of the add-on image

## [2026.8.0b2] - 2026-08-01

### Changed
- The log summary no longer says "of required 0 GPS satellites" when no satellite requirement is configured

### Fixed
- The GPSD options help text no longer suggests "-N". That flag keeps GPSD in the foreground and stops the add-on from finishing startup

## [2026.8.0b1] - 2026-08-01
- Upgrade to version 3.27.3 of GPSD, which includes the security fixes from 3.27.1 (CVE-2025-67268 and CVE-2025-67269)
- Fix: satellite (Sky Data) updates ignored the configured update interval and were published continuously whenever position updates were being held back by the required-satellites setting
- Fix: an MQTT password containing spaces was silently truncated and failed to authenticate
- Fix: the MQTT password was written to the log in clear text when debug logging was enabled
- Fix: the add-on now shuts down cleanly instead of being force-killed, so restarts are quicker
- New Documentation tab in the add-on, covering every configuration option, the entities created and troubleshooting
- Removed the unused "MQTT State Topic" option. It had no effect and could not be used to change any topic
- Marked this add-on `stage: experimental` — it is the development channel and should not be installed for normal use
- Internal: the add-on script has been reorganised into functions with no change to behaviour, and MQTT reconnection is now handled by the MQTT library itself

## [2025.7.0b5] - 2025-08-06
- Add option to connect to TCP based device for GPS data
- Upgrade to version 3.26.1 of GPSD
- Upstream changes:
  - Bump docker/login-action from 3.3.0 to 3.4.0
  - Bump home-assistant/builder from 2024.08.2 to 2025.03.0

## [2025.7.0] - 2025-07-21
- Apparmor fix,  add network capability. Thanks for PR from @cbiffle #46 
- Upstream changes:
  - Bump actions/checkout from 4.1.7 to 4.2.2
  - Bump frenck/action-addon-linter from 2.15 to 2.18

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