"""Bridge gpsd reports to MQTT for Home Assistant.

Reads TPV (position) and SKY (satellite) reports from a local gpsd instance and
publishes them to MQTT. Home Assistant's MQTT discovery protocol is used to
create a device_tracker entity for the position and a sensor for satellite
coverage.
"""

import dataclasses
import datetime
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

# Pause before reopening the gpsd stream after it drops, so a gpsd that is down
# does not spin this loop at full speed.
GPSD_RETRY_DELAY = 5

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
    debug: bool

    @classmethod
    def load(cls, path=OPTIONS_PATH):
        with open(path, "r") as options_file:
            data = json.load(options_file)

        # publish_interval needs an explicit None check rather than `or`: 0 is a
        # valid setting meaning "publish every update", and would otherwise be
        # replaced by the default.
        publish_interval = data.get("publish_interval")
        if publish_interval is None:
            publish_interval = 10

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

    @classmethod
    def for_device(cls, unique_id):
        return cls(
            config=f"homeassistant/device_tracker/gpsd2mqtt/{unique_id}/config",
            attr=f"gpsd2mqtt/{unique_id}/attribute",
            sky_config=f"homeassistant/sensor/gpsd2mqtt/{unique_id}_sky/config",
            sky_state=f"gpsd2mqtt/{unique_id}_sky/state",
            sky_attr=f"gpsd2mqtt/{unique_id}_sky/attribute",
        )


class Throttle:
    """Rate limiter for publishing. An interval of 0 disables throttling."""

    def __init__(self, interval):
        self._interval = interval
        self._last = datetime.datetime.now()

    def ready(self):
        if self._interval == 0:
            return True
        return (datetime.datetime.now() - self._last).total_seconds() >= self._interval

    def mark(self):
        self._last = datetime.datetime.now()


@dataclasses.dataclass
class Stats:
    """Counters behind the periodic summary log line."""

    published_updates: int = 0
    max_satellites: int = 0
    accuracy: str = None
    last_summary: datetime.datetime = dataclasses.field(
        default_factory=datetime.datetime.now
    )

    def due(self, summary_interval):
        elapsed = (datetime.datetime.now() - self.last_summary).total_seconds()
        return elapsed >= summary_interval

    def emit(self, config):
        minutes = (datetime.datetime.now() - self.last_summary).total_seconds() // 60
        preamble = (
            f"Published {self.published_updates} updates to the device_tracker "
            f"in last {minutes} minutes."
        )

        if self.max_satellites >= config.min_n_satellites:
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
        self.last_summary = datetime.datetime.now()


def get_unique_identifier():
    """Build a stable 8-character ID so Home Assistant sees a consistent device."""
    system_info = platform.uname()

    seed = "-".join([
        system_info.node,  # Hostname - increases the chance of uniqueness
        system_info.system,  # System - e.g. Windows or Linux
        system_info.machine,  # Machine - for instance x86
    ])

    return hashlib.sha256(seed.encode()).hexdigest()[:8]


def publish_discovery(client, topics, unique_id):
    """Publish the Home Assistant MQTT discovery configs.

    Deliberately NOT retained. A retained config outlives the add-on: uninstall
    it and the broker keeps serving the config, so Home Assistant recreates a
    permanently unavailable device on every restart until someone manually
    clears the topic. Re-announcing on `homeassistant/status` covers the restart
    case instead, and leaves nothing behind.
    """
    device = {
        "name": "GPSD Service",
        "identifiers": f"gpsd2mqtt_{unique_id}",
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
        "device": device,
    }

    # The one place retain is correct: an empty retained payload is what deletes
    # a retained message, so this clears the config an older version of the
    # add-on may have left behind. If nothing is retained there it is a no-op --
    # brokers do not store empty retained payloads, so this cannot leave garbage.
    client.publish(DEPRECATED_CONFIG_TOPIC, "", retain=True)

    client.publish(topics.config, json.dumps(device_tracker))
    client.publish(topics.sky_config, json.dumps(sky_sensor))

    logger.info("Published MQTT discovery message to topic: %s", topics.config)
    logger.debug("Device tracker discovery payload: %s", device_tracker)
    logger.debug("Sky sensor discovery payload: %s", sky_sensor)


def build_client(config, topics, unique_id):
    """Create the MQTT client and wire up its callbacks.

    Reconnection is left to paho: loop_start() retries in the background using
    the backoff set by reconnect_delay_set(), and on_connect runs again on every
    successful reconnect.
    """

    def on_connect(client, userdata, flags, rc):
        if rc != 0:
            logger.error("Failed to connect, return code: %s", rc)
            return

        logger.info("Connected to MQTT broker")
        # Watching homeassistant/status lets the add-on notice a Home Assistant
        # restart and re-announce itself.
        client.subscribe(HA_STATUS_TOPIC)
        logger.info(
            "Subscribe to MQTT topic %s to listen for HA reboots.", HA_STATUS_TOPIC
        )

    def on_disconnect(client, userdata, rc):
        if rc != 0:
            logger.warning(
                "Disconnected from MQTT broker. Automatic reconnection in progress..."
            )

    def on_message(client, userdata, msg):
        logger.debug("Received message: %s %s", msg.topic, msg.payload)
        if msg.topic == HA_STATUS_TOPIC and msg.payload.decode() == "online":
            publish_discovery(client, topics, unique_id)
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

    return client


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


def stream_gps(client, topics, config, stats):
    """Consume one gpsd session, publishing reports until the stream ends."""
    # SKY and TPV each get their own throttle. Sharing a single timestamp meant
    # SKY updates were only rate-limited when a TPV update happened to reset the
    # clock, so they streamed unthrottled whenever TPV was being withheld.
    sky_throttle = Throttle(config.publish_interval)
    tpv_throttle = Throttle(config.publish_interval)

    # Withhold position updates until the configured satellite count is met.
    publish_position = config.min_n_satellites == 0

    with GPSDClient(host=GPSD_HOST) as gps_client:
        for raw_report in gps_client.json_stream():
            if not _running:
                return

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
            elif report_class == "TPV" and publish_position:
                handle_tpv(client, topics, report, config, tpv_throttle, stats)

            if stats.due(config.summary_interval):
                stats.emit(config)


def wait_for_connection(client):
    """Block until the broker accepts us, or until we are asked to shut down."""
    waited = 0
    while _running and not client.is_connected():
        time.sleep(1)
        waited += 1
        if waited % 5 == 0:
            logger.info("Verifying MQTT Connection ....")


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

    client = build_client(config, topics, unique_id)

    # connect_async tolerates a broker that is not up yet: loop_start keeps
    # retrying in the background instead of raising here.
    logger.info("Connecting to MQTT broker")
    client.connect_async(config.mqtt_broker, config.mqtt_port)
    client.loop_start()
    wait_for_connection(client)

    if _running:
        publish_discovery(client, topics, unique_id)

    stats = Stats()
    while _running:
        logger.info("Starting location detection and sending GPS updates.")
        try:
            stream_gps(client, topics, config, stats)
        except Exception as err:  # gpsd restarting, socket dropped, bad frame
            logger.error("Lost connection to gpsd: %s", err)

        if _running:
            logger.info(
                "gpsd stream ended, reconnecting in %s seconds.", GPSD_RETRY_DELAY
            )
            time.sleep(GPSD_RETRY_DELAY)

    logger.info("Disconnecting from MQTT broker.")
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
