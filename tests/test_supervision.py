"""Detection of a GPS source that has gone away behind a healthy gpsd.

gpsd keeps answering on its port and keeps emitting SKY frames when its own
source is dead, so neither the stream timeout nor the barren-session counter
notices. The absence of TPV is what these cover.
"""

import json

import pytest


class FakeGPSDClient:
    """Replays a fixed list of gpsd reports as one session."""

    def __init__(self, reports):
        self._reports = reports

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def json_stream(self):
        for report in self._reports:
            yield json.dumps(report)


@pytest.fixture
def stream(module, monkeypatch):
    """Runs stream_gps over a canned list of reports."""

    def run(reports, client, topics, config, stats, health):
        monkeypatch.setattr(module, "GPSDClient", lambda **kwargs: FakeGPSDClient(reports))
        return module.stream_gps(client, topics, config, stats, health)

    return run


def freeze(module, monkeypatch, seconds):
    """Pin time.monotonic so a drought can be simulated without waiting."""
    monkeypatch.setattr(module.time, "monotonic", lambda: seconds)


# --- what counts as a living source ----------------------------------------


def test_a_tpv_marks_the_source_alive(module, stream, client, topics, config_factory, health):
    health.last_tpv = module.time.monotonic() - 5000

    stream(
        [{"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0}],
        client, topics, config_factory(), module.Stats(), health,
    )

    assert health.silent_for() < 5


def test_a_withheld_tpv_still_marks_the_source_alive(
    module, stream, client, topics, config_factory, health
):
    """A TPV held back for want of satellites still proves gpsd has a source."""
    health.last_tpv = module.time.monotonic() - 700
    config = config_factory(min_n_satellites=8)

    stream(
        [
            {"class": "SKY", "uSat": 2},  # closes the position gate
            {"class": "TPV", "mode": 1},
        ],
        client, topics, config, module.Stats(), health,
    )

    assert health.silent_for() < 5


def test_sky_frames_alone_do_not_mark_the_source_alive(
    module, stream, client, topics, config_factory, health
):
    """The exact shape of the failure: gpsd chatting away with nothing to say."""
    health.last_tpv = module.time.monotonic() - 700

    stream(
        [{"class": "SKY", "uSat": 0}] * 20,
        client, topics, config_factory(), module.Stats(), health,
    )

    assert health.silent_for() > 600


# --- availability transitions ----------------------------------------------


def test_the_entities_go_unavailable_once_the_source_is_silent(
    module, client, topics, config_factory, health, caplog
):
    health.last_tpv = module.time.monotonic() - 700

    module.check_source_health(client, topics, health, config_factory())

    offline = client.for_topic(topics.availability)
    assert [call.payload for call in offline] == [module.PAYLOAD_OFFLINE]
    assert health.available is False
    assert "check the GPS source" in caplog.text


def test_going_unavailable_is_announced_only_once(
    module, client, topics, config_factory, health
):
    """Otherwise every SKY frame republishes it, once a second, indefinitely."""
    health.last_tpv = module.time.monotonic() - 700
    config = config_factory()

    for _ in range(10):
        module.check_source_health(client, topics, health, config)

    assert len(client.for_topic(topics.availability)) == 1


def test_the_entities_recover_when_position_reports_resume(
    module, client, topics, config_factory, health
):
    config = config_factory()
    health.last_tpv = module.time.monotonic() - 700
    module.check_source_health(client, topics, health, config)

    health.mark_tpv()
    module.check_source_health(client, topics, health, config)

    payloads = [call.payload for call in client.for_topic(topics.availability)]
    assert payloads == [module.PAYLOAD_OFFLINE, module.PAYLOAD_ONLINE]
    assert health.available is True


def test_availability_is_not_retained(module, client, topics, config_factory, health):
    """Same reason as discovery: nothing may outlive the add-on on the broker."""
    health.last_tpv = module.time.monotonic() - 700

    module.check_source_health(client, topics, health, config_factory())

    assert all(not call.retain for call in client.for_topic(topics.availability))


# --- giving up --------------------------------------------------------------


def test_a_long_drought_raises_source_lost(module, client, topics, config_factory, health):
    health.last_tpv = module.time.monotonic() - 1900

    with pytest.raises(module.SourceLost):
        module.check_source_health(client, topics, health, config_factory())


def test_the_lost_threshold_is_the_timeout_times_the_multiplier(
    module, client, topics, config_factory, health
):
    config = config_factory(source_timeout=100, source_lost_multiplier=4)
    health.last_tpv = module.time.monotonic() - 399

    module.check_source_health(client, topics, health, config)

    health.last_tpv = module.time.monotonic() - 401
    with pytest.raises(module.SourceLost):
        module.check_source_health(client, topics, health, config)


def test_a_zero_multiplier_never_gives_up(module, client, topics, config_factory, health):
    """For a source that is legitimately off for long stretches."""
    config = config_factory(source_lost_multiplier=0)
    health.last_tpv = module.time.monotonic() - 100000

    module.check_source_health(client, topics, health, config)

    assert health.available is False


def test_a_zero_timeout_disables_the_check(module, client, topics, config_factory, health):
    config = config_factory(source_timeout=0)
    health.last_tpv = module.time.monotonic() - 100000

    module.check_source_health(client, topics, health, config)

    assert client.published == []
    assert health.available is True


# --- reconnect must not resurrect the entities ------------------------------


def test_reconnecting_while_stale_announces_offline(
    module, config_factory, topics, client, health
):
    """publish_discovery ends with an availability payload; it must not lie."""
    health.available = False
    paho_client, _ = module.build_client(config_factory(), topics, "abc12345", health)

    paho_client.on_connect(client, None, None, 0)

    payloads = [call.payload for call in client.for_topic(topics.availability)]
    assert payloads == [module.PAYLOAD_OFFLINE]
    paho_client.loop_stop()


# --- the summary line -------------------------------------------------------


def test_emit_resets_the_accuracy(module, config_factory, caplog):
    """A retained accuracy reports the last fix as current long after it went."""
    stats = module.Stats()
    stats.accuracy = "3D fix"

    stats.emit(config_factory())

    assert stats.accuracy is None


def test_a_summary_without_any_position_warns(module, config_factory, caplog):
    stats = module.Stats()
    stats.accuracy = None

    stats.emit(config_factory())

    assert "No position reports from gpsd" in caplog.text
    assert "3D fix" not in caplog.text
