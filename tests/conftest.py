"""Shared fixtures.

Imports the add-on script from `gpsd2mqtt_beta/`, the source of truth;
`gpsd2mqtt/` is an rsync copy. Tests live at the repository root so rsync does
not duplicate them into the release folder.
"""

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ADDON_SOURCE = REPO_ROOT / "gpsd2mqtt_beta"

# Prepended so the module file wins over the prod directory of the same name.
sys.path.insert(0, str(ADDON_SOURCE))

import gpsd2mqtt  # noqa: E402


@pytest.fixture
def module():
    """The add-on module under test."""
    return gpsd2mqtt


class FakePublish:
    """One recorded call to `client.publish()`, doubling as its MQTTMessageInfo."""

    def __init__(self, topic, payload, retain):
        self.topic = topic
        self.payload = payload
        self.retain = retain
        self.waited_for = None

    def wait_for_publish(self, timeout=None):
        self.waited_for = timeout

    def json(self):
        import json

        return json.loads(self.payload)

    def __repr__(self):
        return f"FakePublish(topic={self.topic!r}, retain={self.retain!r})"


class FakeClient:
    """Stands in for a paho MQTT client, recording what was published."""

    def __init__(self):
        self.published = []
        self.subscribed = []
        self.will = None

    def publish(self, topic, payload=None, qos=0, retain=False):
        call = FakePublish(topic, payload, retain)
        self.published.append(call)
        return call

    def subscribe(self, topic):
        self.subscribed.append(topic)

    def will_set(self, topic, payload=None, qos=0, retain=False):
        self.will = FakePublish(topic, payload, retain)

    def topics(self):
        return [call.topic for call in self.published]

    def for_topic(self, topic):
        return [call for call in self.published if call.topic == topic]


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def topics(module):
    return module.Topics.for_device("abc12345")


@pytest.fixture
def health(module):
    return module.SourceHealth()


def make_config(module, **overrides):
    """Build a Config without going through options.json."""
    defaults = dict(
        device="/dev/ttyS0",
        baudrate=9600,
        mqtt_broker="core-mosquitto",
        mqtt_port=1883,
        mqtt_username="user",
        mqtt_password="pass",
        publish_3d_fix_only=True,
        min_n_satellites=0,
        publish_interval=10,
        summary_interval=120,
        source_timeout=600,
        source_lost_multiplier=3,
        debug=False,
    )
    defaults.update(overrides)
    return module.Config(**defaults)


@pytest.fixture
def config_factory(module):
    def factory(**overrides):
        return make_config(module, **overrides)

    return factory
