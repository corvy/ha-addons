"""Detection of a GPS source that has gone away behind a healthy gpsd.

gpsd keeps answering on its port and keeps emitting SKY frames when its own
source is dead, so neither the stream timeout nor the barren-session counter
notices. The absence of TPV is what these cover.
"""

import json
import logging

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


def established(health):
    """Put health in the state it reaches after the first position is published."""
    health.has_position = True
    health.available = True
    return health


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


# --- becoming available in the first place ---------------------------------


def test_the_entities_start_unavailable(module):
    """The add-on being up says nothing about whether there is a position."""
    assert module.SourceHealth().available is False
    assert module.SourceHealth().has_position is False


def test_discovery_on_a_fresh_start_announces_offline(
    module, config_factory, topics, client, health
):
    paho_client, _ = module.build_client(config_factory(), topics, "abc12345", health)

    paho_client.on_connect(client, None, None, 0)

    payloads = [call.payload for call in client.for_topic(topics.availability)]
    assert payloads == [module.PAYLOAD_OFFLINE]
    paho_client.loop_stop()


def test_a_withheld_fix_does_not_make_the_entities_available(
    module, stream, client, topics, config_factory, health
):
    """publish_3d_fix_only is the user's gate; availability follows it."""
    stream(
        [{"class": "TPV", "mode": 1, "lat": 1.0, "lon": 2.0}] * 5,
        client, topics, config_factory(publish_3d_fix_only=True),
        module.Stats(), health,
    )

    assert health.has_position is False
    assert health.available is False


def test_a_published_position_makes_the_entities_available(
    module, stream, client, topics, config_factory, health, caplog
):
    with caplog.at_level(logging.INFO, logger="gpsd2mqtt"):
        stream(
            [{"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0}],
            client, topics,
            config_factory(publish_3d_fix_only=True, publish_interval=0),
            module.Stats(), health,
        )

    assert health.available is True
    assert client.for_topic(topics.availability)[-1].payload == module.PAYLOAD_ONLINE
    assert "Entities are now available" in caplog.text


def test_a_poor_fix_makes_them_available_when_the_user_allows_it(
    module, stream, client, topics, config_factory, health
):
    stream(
        [{"class": "TPV", "mode": 1, "lat": 1.0, "lon": 2.0}],
        client, topics, config_factory(publish_3d_fix_only=False, publish_interval=0),
        module.Stats(), health,
    )

    assert health.available is True


def test_the_satellite_requirement_also_gates_availability(
    module, stream, client, topics, config_factory, health
):
    config = config_factory(
        min_n_satellites=8, publish_3d_fix_only=False, publish_interval=0
    )

    stream(
        [{"class": "SKY", "uSat": 2}, {"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0}],
        client, topics, config, module.Stats(), health,
    )

    assert health.available is False


def test_the_gate_is_described_for_the_log(module, config_factory):
    assert "3D fix" in module.describe_position_gate(config_factory())
    assert "8 satellites" in module.describe_position_gate(
        config_factory(min_n_satellites=8)
    )
    assert "any position" in module.describe_position_gate(
        config_factory(publish_3d_fix_only=False, min_n_satellites=0)
    )


# --- availability transitions after that -----------------------------------


def test_the_entities_go_unavailable_once_the_source_is_silent(
    module, client, topics, config_factory, health, caplog
):
    established(health).last_tpv = module.time.monotonic() - 700

    module.check_source_health(client, topics, health, config_factory())

    offline = client.for_topic(topics.availability)
    assert [call.payload for call in offline] == [module.PAYLOAD_OFFLINE]
    assert health.available is False
    assert "check the GPS source" in caplog.text


def test_going_unavailable_is_announced_only_once(
    module, client, topics, config_factory, health
):
    """Otherwise every SKY frame republishes it, once a second, indefinitely."""
    established(health).last_tpv = module.time.monotonic() - 700
    config = config_factory()

    for _ in range(10):
        module.check_source_health(client, topics, health, config)

    assert len(client.for_topic(topics.availability)) == 1


def test_the_entities_recover_when_position_reports_resume(
    module, client, topics, config_factory, health
):
    config = config_factory()
    established(health).last_tpv = module.time.monotonic() - 700
    module.check_source_health(client, topics, health, config)

    health.mark_tpv()
    module.check_source_health(client, topics, health, config)

    payloads = [call.payload for call in client.for_topic(topics.availability)]
    assert payloads == [module.PAYLOAD_OFFLINE, module.PAYLOAD_ONLINE]
    assert health.available is True


def test_a_lost_fix_alone_does_not_make_them_unavailable(
    module, stream, client, topics, config_factory, health
):
    """Latched: only a drought revokes availability, so poor sky does not flap it."""
    config = config_factory(publish_3d_fix_only=True, publish_interval=0)
    stream(
        [{"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0}],
        client, topics, config, module.Stats(), health,
    )
    assert health.available is True

    stream(
        [{"class": "TPV", "mode": 1}] * 20,
        client, topics, config, module.Stats(), health,
    )

    assert health.available is True


def test_availability_is_not_retained(module, client, topics, config_factory, health):
    """Same reason as discovery: nothing may outlive the add-on on the broker."""
    established(health).last_tpv = module.time.monotonic() - 700

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
    established(health).last_tpv = module.time.monotonic() - 100000

    module.check_source_health(client, topics, health, config)

    assert health.available is False


def test_a_zero_timeout_never_revokes_availability(
    module, client, topics, config_factory, health
):
    established(health).last_tpv = module.time.monotonic() - 100000

    module.check_source_health(client, topics, health, config_factory(source_timeout=0))

    assert client.published == []
    assert health.available is True


def test_a_zero_timeout_still_grants_availability(
    module, client, topics, config_factory, health
):
    """Disabling the drought check must not strand the entities as unavailable."""
    health.mark_position()

    module.check_source_health(client, topics, health, config_factory(source_timeout=0))

    assert health.available is True
    assert client.for_topic(topics.availability)[-1].payload == module.PAYLOAD_ONLINE


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
