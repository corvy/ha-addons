"""Bridge gpsd reports to MQTT for Home Assistant.

Reads TPV (position) and SKY (satellite) reports from a local gpsd instance and
publishes them to MQTT. Home Assistant's MQTT discovery protocol is used to
create a device_tracker entity for the position and a sensor for satellite
coverage.
"""

import dataclasses
import hashlib
import json
import logging
import os
import platform
import signal
import time

import paho.mqtt.client as mqtt  # type: ignore
from gpsdclient import GPSDClient  # type: ignore

OPTIONS_PATH = "/data/options.json"
GPSD_HOST = "127.0.0.1"
HA_STATUS_TOPIC = "homeassistant/status"

# Discovery topic used by add-on versions before the unique-identifier scheme.
# Still cleared on startup so upgraded installs do not keep a stale entity.
DEPRECATED_CONFIG_TOPIC = "homeassistant/device_tracker/gpsd/config"

# Bounds for paho's built-in reconnect backoff, in seconds.
RECONNECT_MIN_DELAY = 5
RECONNECT_MAX_DELAY = 300

# Availability payloads. "offline" is also registered as the last will.
PAYLOAD_ONLINE = "online"
PAYLOAD_OFFLINE = "offline"

# CONNACK codes that retrying cannot fix; the configuration has to change.
FATAL_CONNECT_CODES = {
    4: "bad username or password",
    5: "not authorised",
}

# Seconds to wait for the broker before giving up and exiting non-zero.
CONNECT_TIMEOUT = 120

# Grace for the final "offline" publish to reach the socket before shutdown.
SHUTDOWN_PUBLISH_TIMEOUT = 2

# Pause before reopening the gpsd stream, so a dead gpsd does not spin the loop.
GPSD_RETRY_DELAY = 5

# Hang-breaker, not a poll interval. gpsd emits about once a second, so this
# only fires when gpsd is wedged. A timeout ends the stream rather than pausing
# it: gpsdclient reads through makefile(), whose buffer is undefined after one.
GPSD_STREAM_TIMEOUT = 30

# Consecutive gpsd sessions yielding no reports before treating gpsd as gone.
MAX_BARREN_SESSIONS = 12

# gpsd keeps emitting SKY frames when its own source is dead, so a stream that
# is useless rather than silent never trips the timeout or the counter above.
# The absence of TPV is the signal instead. After source_timeout the entities
# are marked unavailable; after source_timeout * source_lost_multiplier the
# add-on exits, so the Supervisor restarts gpsd and it re-dials a tcp:// source,
# which gpsd does not do on its own. Both are add-on options: a timeout of 0
# disables the check, a multiplier of 0 keeps the entities unavailable without
# ever restarting.
DEFAULT_SOURCE_TIMEOUT = 600
DEFAULT_SOURCE_LOST_MULTIPLIER = 3

# gpsd TPV "mode" values, see https://gpsd.gitlab.io/gpsd/gpsd_json.html
FIX_MODES = {1: "No fix", 2: "2D fix", 3: "3D fix"}
MODE_3D_FIX = 3

logger = logging.getLogger("gpsd2mqtt")

# Cleared by SIGTERM/SIGINT so the add-on can stop without waiting for SIGKILL.
_running = True


@dataclasses.dataclass(frozen=True)
class Config:
    """Add-on options, as configured through the Home Assistant UI."""

    device: str
    baudrate: int
    mqtt_broker: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    publish_3d_fix_only: bool
    min_n_satellites: int
    publish_interval: int
    summary_interval: int
    source_timeout: int
    source_lost_multiplier: int
    debug: bool

    @classmethod
    def load(cls, path=OPTIONS_PATH):
        with open(path) as options_file:
            data = json.load(options_file)

        # publish_interval needs an explicit None check rather than `or`: 0 is a
        # valid setting meaning "publish every update", and would otherwise be
        # replaced by the default.
        publish_interval = data.get("publish_interval")
        if publish_interval is None:
            publish_interval = 10

        # Same reason: 0 disables the source check, and 0 for the multiplier
        # means never restart.
        source_timeout = data.get("source_timeout")
        if source_timeout is None:
            source_timeout = DEFAULT_SOURCE_TIMEOUT

        source_lost_multiplier = data.get("source_lost_multiplier")
        if source_lost_multiplier is None:
            source_lost_multiplier = DEFAULT_SOURCE_LOST_MULTIPLIER

        return cls(
            device=data.get("device"),
            baudrate=data.get("baudrate") or 9600,
            mqtt_broker=data.get("mqtt_broker") or "core-mosquitto",
            mqtt_port=data.get("mqtt_port") or 1883,
            # run.sh exports these, resolving Home Assistant's integrated MQTT
            # credentials when the user has not configured their own.
            mqtt_username=os.environ.get("MQTT_USER") or data.get("mqtt_username") or "",
            mqtt_password=os.environ.get("MQTT_PASSWORD") or data.get("mqtt_pw") or "",
            publish_3d_fix_only=data.get("publish_3d_fix_only", True),
            min_n_satellites=data.get("min_n_satellites") or 0,
            publish_interval=publish_interval,
            summary_interval=data.get("summary_interval") or 120,
            source_timeout=source_timeout,
            source_lost_multiplier=source_lost_multiplier,
            debug=data.get("debug", False),
        )

    def log_options(self):
        """Log the options in use. Deliberately never logs the MQTT password."""
        logger.debug("These are the options in use.")
        logger.debug("Serial device: %s", self.device)
        logger.debug("Device Baudrate: %s", self.baudrate)
        logger.debug("MQTT Hostname: %s", self.mqtt_broker)
        logger.debug("MQTT TCP Port: %s", self.mqtt_port)
        logger.debug("MQTT Username: %s", self.mqtt_username)
        logger.debug("Publish interval: %s", self.publish_interval)
        logger.debug("Summary interval: %s", self.summary_interval)
        logger.debug("Source timeout: %s", self.source_timeout)
        logger.debug("Source lost multiplier: %s", self.source_lost_multiplier)
        logger.debug("Required satellites: %s", self.min_n_satellites)
        logger.debug("Debug enabled: %s", self.debug)


@dataclasses.dataclass(frozen=True)
class Topics:
    """MQTT topics for one add-on instance, keyed by its unique identifier."""

    config: str
    attr: str
    sky_config: str
    sky_state: str
    sky_attr: str
    availability: str

    @classmethod
    def for_device(cls, unique_id):
        return cls(
            config=f"homeassistant/device_tracker/gpsd2mqtt/{unique_id}/config",
            attr=f"gpsd2mqtt/{unique_id}/attribute",
            sky_config=f"homeassistant/sensor/gpsd2mqtt/{unique_id}_sky/config",
            sky_state=f"gpsd2mqtt/{unique_id}_sky/state",
            sky_attr=f"gpsd2mqtt/{unique_id}_sky/attribute",
            availability=f"gpsd2mqtt/{unique_id}/availability",
        )


class Throttle:
    """Rate limiter for publishing. An interval of 0 disables throttling.

    Monotonic: chrony, often fed by gpsd itself, steps the system clock, and a
    backwards step would withhold every update until real time caught up.
    """

    def __init__(self, interval):
        self._interval = interval
        self._last = time.monotonic()

    def ready(self):
        if self._interval == 0:
            return True
        return time.monotonic() - self._last >= self._interval

    def mark(self):
        self._last = time.monotonic()


@dataclasses.dataclass
class Stats:
    """Counters behind the periodic summary log line."""

    published_updates: int = 0
    max_satellites: int = 0
    # None once a summary has been emitted with no position report in it.
    accuracy: str | None = "no fix yet"
    # Monotonic, for the same reason as Throttle.
    last_summary: float = dataclasses.field(default_factory=time.monotonic)

    def due(self, summary_interval):
        return time.monotonic() - self.last_summary >= summary_interval

    def emit(self, config):
        elapsed = time.monotonic() - self.last_summary
        minutes = int(elapsed // 60)
        # summary_interval can be under a minute, where "0 minutes" reads as a bug.
        span = f"{minutes} minutes" if minutes else f"{int(elapsed)} seconds"
        preamble = (
            f"Published {self.published_updates} updates to the device_tracker "
            f"in last {span}."
        )

        if self.accuracy is None:
            # No TPV at all this interval, which is what a dead GPS source looks
            # like: gpsd keeps sending SKY, so the counters alone look benign.
            logger.warning(
                "%s No position reports from gpsd in this interval -- check the "
                "GPS source.",
                preamble,
            )
        elif config.min_n_satellites == 0:
            # No requirement configured, so there is nothing to fall short of --
            # reporting "of required 0" just reads as noise.
            logger.info(
                "%s Achieved %s, position with %s GPS satellites.",
                preamble,
                self.accuracy,
                self.max_satellites,
            )
        elif self.max_satellites >= config.min_n_satellites:
            logger.info(
                "%s Achieved %s, position with %s of required %s GPS satellites.",
                preamble,
                self.accuracy,
                self.max_satellites,
                config.min_n_satellites,
            )
        else:
            logger.info(
                "%s Achieved %s. Position not at configured accuracy with only "
                "%s of required %s GPS satellites.",
                preamble,
                self.accuracy,
                self.max_satellites,
                config.min_n_satellites,
            )

        self.published_updates = 0
        self.max_satellites = 0
        # Reset with the counters: a retained accuracy reports the last fix as
        # current long after the source has gone.
        self.accuracy = None
        self.last_summary = time.monotonic()


class SourceLost(Exception):
    """gpsd has produced no position reports for long enough to give up on."""


@dataclasses.dataclass
class SourceHealth:
    """Tracks how long gpsd has gone without a position report.

    Monotonic for the same reason as Throttle. Held in main() rather than the
    stream loop, so a drought spanning several gpsd sessions still adds up.
    """

    last_tpv: float = dataclasses.field(default_factory=time.monotonic)
    available: bool = True

    def mark_tpv(self):
        self.last_tpv = time.monotonic()

    def silent_for(self):
        return time.monotonic() - self.last_tpv


def get_unique_identifier():
    """Build a stable 8-character ID so Home Assistant sees a consistent device."""
    system_info = platform.uname()

    seed = "-".join([
        system_info.node,  # Hostname - increases the chance of uniqueness
        system_info.system,  # System - e.g. Windows or Linux
        system_info.machine,  # Machine - for instance x86
    ])

    return hashlib.sha256(seed.encode()).hexdigest()[:8]


def publish_availability(client, topics, available):
    """Announce whether the entities should be shown as available."""
    client.publish(
        topics.availability, PAYLOAD_ONLINE if available else PAYLOAD_OFFLINE
    )


def check_source_health(client, topics, health, config):
    """Mark the entities unavailable while gpsd has no position to give.

    Raises SourceLost once the drought is long enough that only a restart is
    likely to help.
    """
    if config.source_timeout == 0:
        return

    silent = health.silent_for()
    lost_after = config.source_timeout * config.source_lost_multiplier

    if config.source_lost_multiplier and silent >= lost_after:
        raise SourceLost(f"No position reports from gpsd for {int(silent)} seconds.")

    stale = silent >= config.source_timeout
    if stale and health.available:
        health.available = False
        publish_availability(client, topics, False)
        logger.warning(
            "No position reports from gpsd for %s seconds. Marking the entities "
            "unavailable -- check the GPS source.",
            int(silent),
        )
    elif not stale and not health.available:
        health.available = True
        publish_availability(client, topics, True)
        logger.info("Position reports from gpsd resumed. Entities are available again.")


def publish_discovery(client, topics, unique_id, available=True):
    """Publish the Home Assistant MQTT discovery configs.

    Deliberately NOT retained. A retained config outlives the add-on: uninstall
    it and the broker keeps serving the config, so Home Assistant recreates a
    permanently unavailable device on every restart until someone manually
    clears the topic. Re-announcing on `homeassistant/status` covers the restart
    case instead, and leaves nothing behind.

    Called from on_connect, so it re-fires on every reconnect. Nothing is
    retained, so after a broker restart no copy of the config exists anywhere.
    """
    device = {
        "name": "GPSD Service",
        "identifiers": f"gpsd2mqtt_{unique_id}",
    }

    # Marks both entities unavailable on "offline" or on the last will.
    availability = {
        "availability_topic": topics.availability,
        "payload_available": PAYLOAD_ONLINE,
        "payload_not_available": PAYLOAD_OFFLINE,
    }

    device_tracker = {
        "unique_id": unique_id,
        "name": "Location",
        "platform": "mqtt",
        "json_attributes_topic": topics.attr,
        "payload_home": "home",
        "payload_not_home": "not_home",
        "payload_reset": "check_zone",
        "object_id": "gps_location",
        "icon": "mdi:map-marker",
        **availability,
        "device": {
            **device,
            "configuration_url": "https://github.com/corvy/ha-addons/tree/main/gpsd2mqtt",
            "model": "gpsd2MQTT",
            "manufacturer": "GPSD and @sbarmen",
        },
    }

    sky_sensor = {
        "unique_id": f"{unique_id}_sky",
        "name": "Sky Data",
        "icon": "mdi:satellite-variant",
        "platform": "mqtt",
        "state_topic": topics.sky_state,
        "json_attributes_topic": topics.sky_attr,
        **availability,
        "device": device,
    }

    # The one place retain is correct: an empty retained payload is what deletes
    # a retained message, so this clears the config an older version of the
    # add-on may have left behind. If nothing is retained there it is a no-op --
    # brokers do not store empty retained payloads, so this cannot leave garbage.
    client.publish(DEPRECATED_CONFIG_TOPIC, "", retain=True)

    client.publish(topics.config, json.dumps(device_tracker))
    client.publish(topics.sky_config, json.dumps(sky_sensor))

    # After the configs, so Home Assistant knows which topic to watch first.
    # Not unconditionally online: a reconnect while the GPS source is dead must
    # not resurrect the entities.
    publish_availability(client, topics, available)

    logger.info("Published MQTT discovery message to topic: %s", topics.config)
    logger.debug("Device tracker discovery payload: %s", device_tracker)
    logger.debug("Sky sensor discovery payload: %s", sky_sensor)


class ConnectionState:
    """Last CONNACK result, written by the paho thread and read by main()."""

    def __init__(self):
        self.last_rc = None

    @property
    def is_fatal(self):
        return self.last_rc in FATAL_CONNECT_CODES

    def describe(self):
        if self.last_rc is None:
            return "no response from broker yet"
        return FATAL_CONNECT_CODES.get(self.last_rc, f"return code {self.last_rc}")


def build_client(config, topics, unique_id, health):
    """Create the MQTT client and wire up its callbacks.

    Reconnection is left to paho: loop_start() retries in the background using
    the backoff set by reconnect_delay_set(), and on_connect runs again on every
    successful reconnect.

    Returns the client and the ConnectionState its callbacks write to.
    """
    state = ConnectionState()

    def on_connect(client, userdata, flags, rc):
        state.last_rc = rc
        if rc != 0:
            logger.error("Failed to connect: %s", state.describe())
            return

        logger.info("Connected to MQTT broker")
        # Watching homeassistant/status lets the add-on notice a Home Assistant
        # restart and re-announce itself.
        client.subscribe(HA_STATUS_TOPIC)
        logger.info(
            "Subscribe to MQTT topic %s to listen for HA reboots.", HA_STATUS_TOPIC
        )
        # On every connect, not just the first: nothing is retained, so a broker
        # restart leaves Home Assistant with no config to rediscover us from.
        publish_discovery(client, topics, unique_id, health.available)

    def on_disconnect(client, userdata, rc):
        if rc != 0:
            logger.warning(
                "Disconnected from MQTT broker. Automatic reconnection in progress..."
            )

    def on_message(client, userdata, msg):
        logger.debug("Received message: %s %s", msg.topic, msg.payload)
        if msg.topic == HA_STATUS_TOPIC and msg.payload.decode() == "online":
            publish_discovery(client, topics, unique_id, health.available)
            logger.info("Home Assistant reboot detected. Re-sent MQTT discovery message.")

    def on_log(client, userdata, level, buf):
        logger.debug(buf)

    # NOTE: these are paho-mqtt 1.x callback signatures, and mqtt.Client() takes
    # no arguments there. paho-mqtt 2.x requires an explicit CallbackAPIVersion,
    # which is why the Dockerfile constrains the package to 1.x.
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.on_log = on_log

    client.username_pw_set(config.mqtt_username, config.mqtt_password)
    client.reconnect_delay_set(
        min_delay=RECONNECT_MIN_DELAY, max_delay=RECONNECT_MAX_DELAY
    )

    # Unretained, so nothing lingers on the broker after an uninstall. Must be
    # set before connecting; paho sends it as part of CONNECT.
    client.will_set(topics.availability, PAYLOAD_OFFLINE, retain=False)

    return client, state


def normalise_tpv(report):
    """Rename gpsd's TPV fields to the ones Home Assistant's device_tracker wants."""
    report["accuracy"] = FIX_MODES.get(report.get("mode"), "Unknown")

    for gpsd_name, ha_name in (
        ("alt", "altitude"),
        ("lon", "longitude"),
        ("lat", "latitude"),
    ):
        if report.get(gpsd_name) is not None:
            report[ha_name] = report.pop(gpsd_name)

    # track and magtrack are reported when gpsd starts but stop being sent once
    # the GPS is stationary. Publishing them explicitly as null keeps Home
    # Assistant from expiring the attributes.
    for name in ("track", "magtrack"):
        if name not in report:
            report[name] = None
            logger.debug("Attribute %s not in result, setting value to none", name)

    return report


def handle_sky(client, topics, report, config, throttle, stats):
    """Publish satellite coverage, and report whether position updates are wanted."""
    # uSat is the number of satellites actually used for the fix - the more the
    # better.
    n_satellites = report.get("uSat", 0)
    stats.max_satellites = max(stats.max_satellites, n_satellites)

    logger.debug(
        "Number of satellites: %s of required %s",
        n_satellites,
        config.min_n_satellites,
    )

    if throttle.ready():
        client.publish(topics.sky_attr, json.dumps(report))
        client.publish(topics.sky_state, str(n_satellites))
        throttle.mark()
        logger.debug("Published SKY: %s to topic: %s", n_satellites, topics.sky_state)
        logger.debug("Published SKY: %s to topic: %s", report, topics.sky_attr)

    return n_satellites >= config.min_n_satellites


def handle_tpv(client, topics, report, config, throttle, stats):
    """Publish a position update, subject to the fix and throttle settings."""
    report = normalise_tpv(report)
    stats.accuracy = report["accuracy"]
    logger.debug("Processed TPV Data: %s", report)

    if not throttle.ready():
        return

    logger.debug("Accuracy achieved: %s", report["accuracy"])

    # Only publish a good fix, unless the user has opted into every update.
    if config.publish_3d_fix_only and report.get("mode") != MODE_3D_FIX:
        return

    client.publish(topics.attr, json.dumps(report))
    stats.published_updates += 1
    throttle.mark()
    logger.debug("Published TPV: %s to topic: %s", report, topics.attr)


def stream_gps(client, topics, config, stats, health):
    """Consume one gpsd session, publishing until the stream ends.

    Returns the number of reports seen, so the caller can tell a gpsd that is
    restarting from one that is simply not there.
    """
    # SKY and TPV each get their own throttle. Sharing a single timestamp meant
    # SKY updates were only rate-limited when a TPV update happened to reset the
    # clock, so they streamed unthrottled whenever TPV was being withheld.
    sky_throttle = Throttle(config.publish_interval)
    tpv_throttle = Throttle(config.publish_interval)

    # Withhold position updates until the configured satellite count is met.
    publish_position = config.min_n_satellites == 0
    seen = 0

    with GPSDClient(host=GPSD_HOST, timeout=GPSD_STREAM_TIMEOUT) as gps_client:
        for raw_report in gps_client.json_stream():
            seen += 1
            if not _running:
                return seen

            try:
                report = json.loads(raw_report)
            except json.JSONDecodeError as err:
                logger.error("Failed to decode JSON: %s", err)
                continue

            logger.debug("RAW GPS data: %s", report)

            report_class = report.get("class")
            if report_class == "SKY":
                publish_position = handle_sky(
                    client, topics, report, config, sky_throttle, stats
                )
            elif report_class == "TPV":
                # Marked before the gate: a TPV withheld for want of satellites
                # still proves the source is alive.
                health.mark_tpv()
                if publish_position:
                    handle_tpv(client, topics, report, config, tpv_throttle, stats)

            check_source_health(client, topics, health, config)

            if stats.due(config.summary_interval):
                stats.emit(config)

    return seen


def interruptible_sleep(seconds):
    """Sleep in slices so a shutdown request is noticed.

    time.sleep() is resumed after a signal handler runs (PEP 475), so a plain
    sleep would wait out its full duration on SIGTERM.
    """
    deadline = time.monotonic() + seconds
    while _running and time.monotonic() < deadline:
        time.sleep(0.25)


def wait_for_connection(client, config, state):
    """Block until the broker accepts us. Returns True if it did."""
    waited = 0
    while _running and not client.is_connected():
        if state.is_fatal:
            logger.error(
                "MQTT broker rejected the connection: %s. Check the MQTT username "
                "and password in the add-on configuration.",
                state.describe(),
            )
            return False

        if waited >= CONNECT_TIMEOUT:
            logger.error(
                "Gave up waiting for MQTT broker %s:%s after %s seconds (%s).",
                config.mqtt_broker,
                config.mqtt_port,
                CONNECT_TIMEOUT,
                state.describe(),
            )
            return False

        time.sleep(1)
        waited += 1
        if waited % 15 == 0:
            logger.info(
                "Still waiting for MQTT broker %s:%s (%s).",
                config.mqtt_broker,
                config.mqtt_port,
                state.describe(),
            )

    return client.is_connected()


def handle_shutdown(signum, frame):
    global _running
    logger.info("Received %s, shutting down.", signal.Signals(signum).name)
    _running = False


def main():
    config = Config.load()

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    config.log_options()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    unique_id = get_unique_identifier()
    topics = Topics.for_device(unique_id)
    logger.debug("Unique ID: %s", unique_id)
    logger.debug("MQTT Config: %s", topics.config)
    logger.debug("MQTT Attribute: %s", topics.attr)

    health = SourceHealth()
    client, state = build_client(config, topics, unique_id, health)

    # connect_async tolerates a broker that is not up yet: loop_start keeps
    # retrying in the background instead of raising here.
    logger.info("Connecting to MQTT broker")
    client.connect_async(config.mqtt_broker, config.mqtt_port)
    client.loop_start()

    # paho drops QoS 0 publishes while disconnected, so wait before streaming.
    # Discovery is sent from on_connect.
    if not wait_for_connection(client, config, state):
        client.loop_stop()
        return 0 if not _running else 1

    exit_code = 0
    stats = Stats()
    barren_sessions = 0

    while _running:
        logger.info("Starting location detection and sending GPS updates.")
        try:
            seen = stream_gps(client, topics, config, stats, health)
        except SourceLost as err:
            # gpsd is answering but has nothing to say. Restarting takes gpsd
            # with it, which is what re-dials a dropped tcp:// source.
            logger.error(
                "%s Giving up so the add-on is restarted -- check the GPS source "
                "and the log above for gpsd startup errors.",
                err,
            )
            exit_code = 1
            break
        except TimeoutError:
            # gpsd went quiet; the stream can only be reopened, not resumed.
            seen = 0
            logger.info(
                "No data from gpsd in %s seconds, reopening the stream.",
                GPSD_STREAM_TIMEOUT,
            )
        except Exception as err:  # gpsd restarting, socket dropped, bad frame
            seen = 0
            logger.error("Lost connection to gpsd: %s", err)
        else:
            logger.info("gpsd stream ended after %s reports.", seen)

        # A session yielding nothing means gpsd is absent, not just restarting.
        # Enough in a row and we exit non-zero so the Supervisor restarts the
        # add-on, and gpsd with it.
        barren_sessions = barren_sessions + 1 if seen == 0 else 0
        if barren_sessions >= MAX_BARREN_SESSIONS:
            logger.error(
                "No data from gpsd across %s attempts. Giving up so the add-on "
                "is restarted -- check the GPS device and the log above for gpsd "
                "startup errors.",
                barren_sessions,
            )
            exit_code = 1
            break

        if _running:
            logger.info(
                "gpsd stream ended, reconnecting in %s seconds.", GPSD_RETRY_DELAY
            )
            interruptible_sleep(GPSD_RETRY_DELAY)

    logger.info("Disconnecting from MQTT broker.")
    publish_offline(client, topics)
    # disconnect() before loop_stop(): the network loop writes the packet.
    client.disconnect()
    client.loop_stop()
    return exit_code


def publish_offline(client, topics):
    """Announce departure and wait for it to reach the socket.

    The broker discards the last will on a clean disconnect, so a clean stop has
    to say so itself. publish() only queues, and the network thread is stopping.
    """
    try:
        info = client.publish(topics.availability, PAYLOAD_OFFLINE)
        info.wait_for_publish(timeout=SHUTDOWN_PUBLISH_TIMEOUT)
    except (ValueError, RuntimeError) as err:
        # Not worth failing a shutdown over; the broker sends the will instead.
        logger.debug("Could not publish offline availability: %s", err)


if __name__ == "__main__":
    raise SystemExit(main())
