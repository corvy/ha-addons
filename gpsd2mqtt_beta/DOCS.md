# GPSD to MQTT

Runs [gpsd](https://gpsd.gitlab.io/gpsd/) inside Home Assistant and publishes the
position it reports to MQTT, so you get a `device_tracker` entity that follows
your actual GPS position.

The typical use is a Home Assistant install that moves — a boat, a camper, a
vehicle — where you want the home zone to follow the installation rather than
sit at a fixed address.

## Requirements

- An MQTT broker. The [Mosquitto broker App](https://github.com/home-assistant/addons/tree/master/mosquitto)
  is the easiest option and needs to be installed **before** this App.
- A GPS receiver that gpsd supports, either attached over serial/USB or reachable
  over TCP.

## Installation

1. Install and start an MQTT broker.
2. Install this App.
3. Open the **Configuration** tab and set **Device type** and **GPS Device**.
4. Start the App and check the **Log** tab.

The App publishes its entities automatically using MQTT discovery — there is
nothing to add to `configuration.yaml`.

## Entities

The App creates a single **GPSD Service** device with two entities.

| Entity | What it reports |
|---|---|
| `device_tracker.gps_location` | The position. Attributes include `latitude`, `longitude`, `altitude`, `speed`, `track`, `magtrack` and `accuracy` (`No fix`, `2D fix` or `3D fix`). |
| `sensor.gpsd_service_sky_data` | The number of satellites currently used for the fix, with the full gpsd SKY report as attributes. |

`track` and `magtrack` are only reported by gpsd while moving. They are published
as `null` when stationary so Home Assistant does not expire the attributes.

Both entities start **unavailable** and become available once a position has
actually been published — the App being up says nothing about whether there is a
GPS position. What counts as a position is your own **3D Fix Only** and
**Required number of satellites** settings; the log states which of them it is
waiting for at startup. On a cold start that means the entities stay unavailable
until the receiver gets its first fix, which can take a few minutes.

Once available they stay available while the fix comes and goes, so driving
through a tunnel does not flap them. Only the App stopping, or the GPS source
going silent for `source_timeout`, takes them unavailable again.

Nothing is retained on the broker, so uninstalling the App leaves no trace — the
entities disappear rather than lingering as permanently unavailable.

## Example: keep the home zone on your actual position

The most common reason to install this. Home Assistant's home zone follows the
GPS instead of sitting at a fixed address.

```yaml
alias: Dynamic Update Home
description: Move the Home zone to the position reported by the GPS.
triggers:
  - trigger: state
    entity_id: device_tracker.gps_location
    attribute: latitude
  - trigger: state
    entity_id: device_tracker.gps_location
    attribute: longitude
conditions:
  - condition: not
    conditions:
      - condition: state
        entity_id: device_tracker.gps_location
        state:
          - unavailable
          - unknown
    note: Skip while the GPS source is lost, so the home zone keeps its last good position.
actions:
  - action: homeassistant.set_location
    data:
      latitude: "{{ state_attr('device_tracker.gps_location', 'latitude') }}"
      longitude: "{{ state_attr('device_tracker.gps_location', 'longitude') }}"
mode: single
max_exceeded: silent
```

Both attributes change together, so the two triggers fire as a pair and one run
is skipped every time; `max_exceeded: silent` keeps that out of the log.

The home zone moves on every published position, so every zone-based automation
re-evaluates that often. Raise **Update Interval** if that is more churn than you
want.

## Configuration

### Connecting the GPS

| Option | Default | Notes |
|---|---|---|
| **Device type** (`input_type`) | `serial` | `serial` for a directly attached receiver (USB dongle, GPS HAT, serial port), `tcp` for one reached over the network. |
| **GPS Device** (`device`) | — | For example `/dev/ttyUSB0` or `/dev/ttyACM0`. Required even in TCP mode, where it is ignored — pick any device from the list to satisfy the form. |
| **TCP Hostname or IP** (`tcp_host`) | — | TCP mode only. |
| **TCP Port** (`tcp_port`) | — | TCP mode only. Both host and port must be set or the App stops with an error. |

### Serial line settings

Only relevant for `serial`. The defaults suit most receivers.

| Option | Default | Notes |
|---|---|---|
| **Baudrate** (`baudrate`) | `9600` | Most GPS receivers use 9600 or 4800. |
| **Databits** (`charsize`) | `8` | |
| **Parity bit** (`parity`) | `false` | |
| **stopbit** (`stopbit`) | `1` | Either 1 or 2. |

### What gets published

| Option | Default | Notes |
|---|---|---|
| **3D Fix Only** (`publish_3d_fix_only`) | `true` | Only publish once the receiver has a 3D fix, so Home Assistant is not fed low-quality positions while it is still acquiring satellites. |
| **Required number of satellites** (`min_n_satellites`) | `0` | A 3D fix needs 3 satellites; more means a more accurate position. 5–7 noticeably improves accuracy at the cost of fewer updates, especially in the first minutes or under poor sky visibility. While the requirement is unmet the summary reports 0 updates — that is expected. |
| **Update Interval in seconds** (`publish_interval`) | `10` | Minimum delay between position updates. `0` publishes every update gpsd produces. |
| **Print Summary Interval in seconds** (`summary_interval`) | `120` | How often the App writes its summary line to the log. |

### GPS source supervision

gpsd keeps running and keeps reporting satellite data when its own source goes
away, so these two options are what notice a receiver that has stopped producing
positions.

| Option | Default | Notes |
|---|---|---|
| **GPS source timeout in seconds** (`source_timeout`) | `600` | Time without a position report before both entities are marked unavailable. `0` disables the check. |
| **GPS source restart multiplier** (`source_lost_multiplier`) | `3` | Multiples of the timeout to wait before restarting the App so gpsd reconnects to the source — 30 minutes at the default timeout. `0` keeps the entities unavailable without ever restarting. |

### MQTT

Leave these empty when using the Mosquitto App: the App picks up Home
Assistant's integrated credentials automatically.

| Option | Default | Notes |
|---|---|---|
| **MQTT Server IP or Hostname** (`mqtt_broker`) | `core-mosquitto` | |
| **MQTT Server port** (`mqtt_port`) | `1883` | |
| **MQTT Username** (`mqtt_username`) | integrated auth | Set only for an external broker. |
| **MQTT Password** (`mqtt_pw`) | integrated auth | Only used if a username is set. |

If you set a username but the App cannot authenticate, check the log — it
reports whether it started with integrated or manual credentials.

### Advanced

| Option | Default | Notes |
|---|---|---|
| **GPSD options** (`gpsd_options`) | — | Extra flags passed to gpsd, for example `-D3` for verbose gpsd logging. The App always passes `--nowait`, `--readonly` and `--listenany`. |
| **Debug** (`debug`) | `false` | Verbose App logging, including every raw GPS report. Useful when reporting a problem. The MQTT password is never written to the log. |

Do not pass `-N` (`--foreground`) in **GPSD options**. The App starts gpsd as a
background daemon and then hands over to the MQTT publisher, so keeping gpsd in
the foreground means the publisher never starts and the App appears to hang.

Changing any option takes effect on the next start — restart the App after
saving.

## When things go wrong

The App recovers or restarts itself rather than sitting there looking healthy.

| Situation | What the App does |
|---|---|
| gpsd stops responding | Reports itself unhealthy. Enable **Watchdog** on the App's Info tab and Home Assistant restarts it. It also gives up on its own after about a minute without any GPS data, which restarts it the same way. |
| The GPS source disappears behind a gpsd that is still running — an unplugged receiver, or a TCP source that has gone away | Both entities go unavailable after `source_timeout`, and the App restarts after `source_timeout × source_lost_multiplier` so gpsd reconnects to the source. The entities recover on their own if position reports come back first. |
| The MQTT broker restarts | Reconnects and re-announces its entities automatically. No Home Assistant restart needed. |
| The MQTT credentials are wrong | Stops with a clear error in the log instead of retrying silently forever. |
| The Supervisor has not registered the MQTT service yet | Waits for it for a minute before giving up, rather than failing immediately at boot. |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| No entities appear | Confirm the MQTT integration is set up and the broker is running. The log shows `Published MQTT discovery message to topic: ...` once discovery has been sent. |
| Position never updates | Check the summary line in the log. If it reports fewer satellites than required, either lower **Required number of satellites** or improve the receiver's view of the sky. A cold start can take several minutes. |
| Entities show as unavailable | The App is not running, cannot reach the broker, or has had no position from gpsd for `source_timeout`. The last line of the App log gives the reason. |
| The App keeps restarting | With **Watchdog** enabled, Home Assistant restarts it whenever gpsd stops answering. Look for gpsd's own startup errors near the top of the log; the usual cause is a serial device that is missing or held open by something else. |
| The App cannot open the serial device | Make sure no other App or integration (such as the GPSD integration) is holding the same device. |
| Another gpsd client needs access | Port `2947` is available but disabled by default. Enable it in the **Network** section only if you want to point other gpsd clients at it. |

## Support

Issues and questions: <https://github.com/corvy/ha-addons/issues>
