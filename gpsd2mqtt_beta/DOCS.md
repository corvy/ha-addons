# GPSD to MQTT

Runs [gpsd](https://gpsd.gitlab.io/gpsd/) inside Home Assistant and publishes the
position it reports to MQTT, so you get a `device_tracker` entity that follows
your actual GPS position.

The typical use is a Home Assistant install that moves — a boat, a camper, a
vehicle — where you want the home zone to follow the installation rather than
sit at a fixed address.

## Requirements

- An MQTT broker. The [Mosquitto broker add-on](https://github.com/home-assistant/addons/tree/master/mosquitto)
  is the easiest option and needs to be installed **before** this add-on.
- A GPS receiver that gpsd supports, either attached over serial/USB or reachable
  over TCP.

## Installation

1. Install and start an MQTT broker.
2. Install this add-on.
3. Open the **Configuration** tab and set **Device type** and **GPS Device**
   (see below).
4. Start the add-on and check the **Log** tab.

The add-on publishes its entities automatically using MQTT discovery — there is
nothing to add to `configuration.yaml`.

## Configuration

### Connecting the GPS

**Device type** (`input_type`) — `serial` for a directly attached receiver (USB
dongle, GPS HAT, serial port), or `tcp` for one reached over the network.

**GPS Device** (`device`) — the serial device, for example `/dev/ttyUSB0` or
`/dev/ttyACM0`. Required even in TCP mode, where it is ignored; pick any device
from the list to satisfy the configuration form.

**TCP Hostname or IP** / **TCP Port** (`tcp_host`, `tcp_port`) — only used when
device type is `tcp`. Both must be set or the add-on stops with an error.

### Serial line settings

Only relevant for `serial`. The defaults suit most receivers, so change them
only if yours needs it.

| Option | Default | Notes |
|---|---|---|
| **Baudrate** (`baudrate`) | `9600` | Most GPS receivers use 9600 or 4800. |
| **Databits** (`charsize`) | `8` | |
| **Parity bit** (`parity`) | `false` | |
| **stopbit** (`stopbit`) | `1` | Either 1 or 2. |

### What gets published

**3D Fix Only** (`publish_3d_fix_only`) — default `true`. Only publish a position
once the receiver has a 3D fix. Leaving this on avoids feeding Home Assistant
low-quality positions while the receiver is still acquiring satellites.

**Required number of satellites** (`min_n_satellites`) — default `0` (no
requirement). A 3D fix needs 3 satellites, but more satellites means a more
accurate position. Setting this to 5–7 noticeably improves accuracy at the cost
of fewer updates, especially in the first minutes after starting or under poor
sky visibility. While the requirement is not met you will see `0 new updates` in
the summary log — that is expected; it will start reporting once coverage is
good enough.

**Update Interval in seconds** (`publish_interval`) — default `10`. Minimum delay
between position updates. Set to `0` to publish every update gpsd produces.

**Print Summary Interval in seconds** (`summary_interval`) — default `120`. How
often the add-on writes its summary line to the log.

### MQTT

Leave these empty when using the Mosquitto add-on: the add-on picks up Home
Assistant's integrated credentials automatically.

| Option | Default | Notes |
|---|---|---|
| **MQTT Server IP or Hostname** (`mqtt_broker`) | `core-mosquitto` | |
| **MQTT Server port** (`mqtt_port`) | `1883` | |
| **MQTT Username** (`mqtt_username`) | integrated auth | Set only for an external broker. |
| **MQTT Password** (`mqtt_pw`) | integrated auth | Only used if a username is set. |

If you set a username but the add-on cannot authenticate, check the log — it
reports whether it started with integrated or manual credentials.

### Advanced

**GPSD options** (`gpsd_options`) — extra flags passed to gpsd, for example
`-D3` for verbose gpsd logging. The add-on always passes `--nowait`,
`--readonly` and `--listenany`.

Do not pass `-N` (`--foreground`). The add-on starts gpsd as a background daemon
and then hands over to the MQTT publisher, so keeping gpsd in the foreground
means the publisher never starts and the add-on appears to hang.

**Debug** (`debug`) — verbose add-on logging, including every raw GPS report.
Useful when reporting a problem. The MQTT password is never written to the log.

## Entities

The add-on creates a single **GPSD Service** device with two entities:

**`device_tracker.gps_location`** — the position. Attributes include `latitude`,
`longitude`, `altitude`, `speed`, `track`, `magtrack` and `accuracy` (`No fix`,
`2D fix` or `3D fix`).

`track` and `magtrack` are only reported by gpsd while moving. They are published
as `null` when stationary so Home Assistant does not expire the attributes.

**`sensor.gpsd_service_sky_data`** — the number of satellites currently used for
the fix, with the full gpsd SKY report as attributes.

### Availability

Both entities go **unavailable** when the add-on stops, rather than keeping their
last position indefinitely. This covers a clean stop as well as a crash or a lost
connection — in the latter case the broker publishes it on the add-on's behalf.

Nothing is retained on the broker, so uninstalling the add-on leaves no trace: the
entities simply disappear rather than lingering as permanently unavailable.

### Recovery

The add-on restarts itself when things go wrong, rather than sitting there looking
healthy:

- If gpsd stops responding, Home Assistant's watchdog notices port 2947 has gone
  quiet and restarts the add-on. The add-on also gives up on its own after about a
  minute without any GPS data.
- If the MQTT broker restarts, the add-on reconnects and re-announces its entities
  automatically. No Home Assistant restart is needed.
- If the MQTT credentials are wrong, the add-on stops with a clear error in the log
  instead of retrying silently forever.

## Example: keep the home zone on your actual position

```yaml
alias: Dynamic Update Home
description: Update the Home location for Home Assistant based on GPS information
triggers:
  - trigger: state
    entity_id:
      - device_tracker.gps_location
    attribute: latitude
  - trigger: state
    entity_id:
      - device_tracker.gps_location
    attribute: longitude
conditions: []
actions:
  - action: homeassistant.set_location
    data:
      latitude: "{{ state_attr('device_tracker.gps_location', 'latitude') }}"
      longitude: "{{ state_attr('device_tracker.gps_location', 'longitude') }}"
mode: single
```

## Troubleshooting

**No entities appear.** Confirm the MQTT integration is set up and the broker is
running. The log shows `Published MQTT discovery message to topic: ...` once
discovery has been sent.

**Position never updates.** Check the summary line in the log. If it reports
fewer satellites than required, either lower **Required number of satellites** or
improve the receiver's view of the sky. A cold start can take several minutes.

**Entities show as unavailable.** The add-on is not running, or cannot reach the
broker. Check the add-on log — if it stopped on an MQTT error, the reason is the
last line.

**The add-on keeps restarting.** The watchdog restarts it when gpsd stops
answering. Look for gpsd's own startup errors near the top of the log; the usual
cause is a serial device that is missing, or is held open by something else.

**The add-on cannot open the serial device.** Make sure no other add-on or
integration (such as the GPSD integration) is holding the same device.

**Direct gpsd access.** Port `2947` is available but disabled by default. Enable
it in the **Network** section only if you want to point other gpsd clients at it.

## Support

Issues and questions: <https://github.com/corvy/ha-addons/issues>
