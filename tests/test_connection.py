"""Broker connection handling: the will, discovery on reconnect, and giving up.

`build_client` is exercised against a real paho client -- constructing one does
no I/O -- so the will is checked as paho actually stored it rather than as we
hoped to have set it.
"""

import pytest

# --- ConnectionState -------------------------------------------------------


def test_auth_failures_are_recognised_as_fatal(module):
    state = module.ConnectionState()

    for rc in (4, 5):
        state.last_rc = rc
        assert state.is_fatal, f"CONNACK {rc} can never succeed on retry"


def test_transient_failures_are_not_fatal(module):
    state = module.ConnectionState()

    # 3 is "server unavailable" -- worth waiting out, the broker may be booting.
    for rc in (None, 0, 1, 2, 3):
        state.last_rc = rc
        assert not state.is_fatal


def test_state_describes_the_failure_in_words(module):
    state = module.ConnectionState()

    assert "no response" in state.describe()
    state.last_rc = 5
    assert state.describe() == "not authorised"
    state.last_rc = 3
    assert "3" in state.describe()


# --- build_client ----------------------------------------------------------


@pytest.fixture
def built(module, config_factory, topics):
    client, state = module.build_client(config_factory(), topics, "abc12345")
    yield client, state
    client.loop_stop()


def test_last_will_is_registered_before_connecting(built, topics, module):
    client, _ = built

    assert client._will is True
    assert client._will_topic == topics.availability.encode()
    assert client._will_payload == module.PAYLOAD_OFFLINE.encode()


def test_last_will_is_not_retained(built):
    """A retained will would outlive the add-on on the broker after uninstall."""
    client, _ = built

    assert client._will_retain is False


def test_connecting_publishes_discovery(built, client, topics):
    """Not just on the first connect -- this is what makes a broker restart recover."""
    paho_client, _ = built

    paho_client.on_connect(client, None, None, 0)

    assert client.for_topic(topics.config)
    assert client.for_topic(topics.sky_config)
    assert client.for_topic(topics.availability)


def test_connecting_subscribes_to_home_assistant_status(built, client, module):
    paho_client, _ = built

    paho_client.on_connect(client, None, None, 0)

    assert module.HA_STATUS_TOPIC in client.subscribed


def test_a_rejected_connect_publishes_nothing(built, client):
    paho_client, state = built

    paho_client.on_connect(client, None, None, 5)

    assert client.published == []
    assert state.last_rc == 5


def test_home_assistant_restart_republishes_discovery(built, client, topics, module):
    paho_client, _ = built

    class Message:
        topic = module.HA_STATUS_TOPIC
        payload = b"online"

    paho_client.on_message(client, None, Message())

    assert client.for_topic(topics.config)


# --- wait_for_connection ---------------------------------------------------


class StubClient:
    def __init__(self, connected):
        self._connected = connected

    def is_connected(self):
        return self._connected


def test_wait_returns_immediately_when_connected(module, config_factory):
    state = module.ConnectionState()

    assert module.wait_for_connection(StubClient(True), config_factory(), state) is True


def test_wait_gives_up_on_bad_credentials(module, config_factory, caplog, monkeypatch):
    """Retrying a rejected password forever only buries the one useful log line."""
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    state = module.ConnectionState()
    state.last_rc = 5

    result = module.wait_for_connection(StubClient(False), config_factory(), state)

    assert result is False
    assert "not authorised" in caplog.text
    assert "username" in caplog.text.lower()


def test_wait_gives_up_after_the_timeout(module, config_factory, caplog, monkeypatch):
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(module, "CONNECT_TIMEOUT", 3)
    state = module.ConnectionState()

    result = module.wait_for_connection(StubClient(False), config_factory(), state)

    assert result is False
    assert "Gave up waiting" in caplog.text


def test_wait_reports_the_broker_it_is_waiting_for(
    module, config_factory, caplog, monkeypatch
):
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(module, "CONNECT_TIMEOUT", 20)
    state = module.ConnectionState()

    module.wait_for_connection(
        StubClient(False), config_factory(mqtt_broker="broker.example"), state
    )

    assert "broker.example" in caplog.text


# --- shutdown --------------------------------------------------------------


def test_interruptible_sleep_stops_when_shutdown_is_requested(module, monkeypatch):
    """A plain time.sleep is resumed after a signal, so a stop would wait it out."""
    monkeypatch.setattr(module, "_running", False)

    started = module.time.monotonic()
    module.interruptible_sleep(30)

    assert module.time.monotonic() - started < 1
