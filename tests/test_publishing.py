"""What actually goes onto the broker.

The retain assertions here are the important ones. Retained discovery configs outlive
the add-on: uninstall it and the broker keeps serving the config, so Home Assistant
recreates a permanently unavailable device on every restart until someone hand-clears
the topic. Re-announcing on `homeassistant/status` covers the restart case instead.
"""

import json

# --- discovery -------------------------------------------------------------


def test_discovery_configs_are_not_retained(module, client, topics):
    module.publish_discovery(client, topics, "abc12345")

    for topic in (topics.config, topics.sky_config):
        calls = client.for_topic(topic)
        assert len(calls) == 1, f"expected exactly one publish to {topic}"
        assert calls[0].retain is False, (
            f"{topic} must not be retained -- a retained discovery config orphans "
            "the entity when the add-on is uninstalled"
        )


def test_deprecated_topic_is_cleared_with_an_empty_retained_payload(
    module, client, topics
):
    """The one legitimate retain: an empty retained payload deletes a retained message."""
    module.publish_discovery(client, topics, "abc12345")

    calls = client.for_topic(module.DEPRECATED_CONFIG_TOPIC)

    assert len(calls) == 1
    assert calls[0].retain is True
    assert calls[0].payload == "", (
        "must be an empty payload -- a non-empty retained payload would create "
        "exactly the orphan this is meant to remove"
    )


def test_discovery_payloads_describe_both_entities(module, client, topics):
    module.publish_discovery(client, topics, "abc12345")

    tracker = client.for_topic(topics.config)[0].json()
    sky = client.for_topic(topics.sky_config)[0].json()

    assert tracker["unique_id"] == "abc12345"
    assert tracker["json_attributes_topic"] == topics.attr
    assert tracker["object_id"] == "gps_location"

    assert sky["unique_id"] == "abc12345_sky"
    assert sky["state_topic"] == topics.sky_state
    assert sky["json_attributes_topic"] == topics.sky_attr


def test_both_entities_share_one_device(module, client, topics):
    """Otherwise they appear as two unrelated devices in Home Assistant."""
    module.publish_discovery(client, topics, "abc12345")

    tracker = client.for_topic(topics.config)[0].json()
    sky = client.for_topic(topics.sky_config)[0].json()

    assert tracker["device"]["identifiers"] == "gpsd2mqtt_abc12345"
    assert sky["device"]["identifiers"] == tracker["device"]["identifiers"]


def test_discovery_payloads_are_valid_json(module, client, topics):
    module.publish_discovery(client, topics, "abc12345")

    for topic in (topics.config, topics.sky_config):
        json.loads(client.for_topic(topic)[0].payload)


# --- availability ----------------------------------------------------------


def test_discovery_announces_us_as_online(module, client, topics):
    module.publish_discovery(client, topics, "abc12345")

    calls = client.for_topic(topics.availability)

    assert len(calls) == 1
    assert calls[0].payload == module.PAYLOAD_ONLINE


def test_online_is_announced_after_the_configs(module, client, topics):
    """Home Assistant needs to know which topic to watch before being told we are up."""
    module.publish_discovery(client, topics, "abc12345")

    order = client.topics()

    assert order.index(topics.availability) > order.index(topics.config)
    assert order.index(topics.availability) > order.index(topics.sky_config)


def test_availability_is_not_retained(module, client, topics):
    """Same reasoning as discovery: nothing may outlive the add-on on the broker."""
    module.publish_discovery(client, topics, "abc12345")

    assert client.for_topic(topics.availability)[0].retain is False


def test_both_entities_declare_the_availability_topic(module, client, topics):
    module.publish_discovery(client, topics, "abc12345")

    tracker = client.for_topic(topics.config)[0].json()
    sky = client.for_topic(topics.sky_config)[0].json()

    for payload in (tracker, sky):
        assert payload["availability_topic"] == topics.availability
        assert payload["payload_available"] == module.PAYLOAD_ONLINE
        assert payload["payload_not_available"] == module.PAYLOAD_OFFLINE


def test_shutdown_announces_offline(module, client, topics):
    module.publish_offline(client, topics)

    calls = client.for_topic(topics.availability)

    assert len(calls) == 1
    assert calls[0].payload == module.PAYLOAD_OFFLINE
    assert calls[0].retain is False


def test_shutdown_survives_a_broker_that_has_already_gone(module, client, topics):
    """A failed goodbye must not turn a clean stop into a crash."""

    def exploding_publish(*args, **kwargs):
        raise RuntimeError("Message publish failed: The client is not currently connected.")

    client.publish = exploding_publish

    module.publish_offline(client, topics)  # must not raise


# --- SKY -------------------------------------------------------------------


def test_sky_publishes_satellite_count_as_state(module, client, topics, config_factory):
    stats = module.Stats()
    report = {"class": "SKY", "uSat": 9, "nSat": 14}

    module.handle_sky(
        client, topics, report, config_factory(), module.Throttle(0), stats
    )

    assert client.for_topic(topics.sky_state)[0].payload == "9"
    assert client.for_topic(topics.sky_attr)[0].json()["uSat"] == 9


def test_sky_updates_are_throttled(module, client, topics, config_factory):
    """The 2026.8.0 bug: SKY ignored publish_interval entirely."""
    stats = module.Stats()
    throttle = module.Throttle(3600)
    config = config_factory()

    for _ in range(5):
        module.handle_sky(
            client, topics, {"class": "SKY", "uSat": 9}, config, throttle, stats
        )

    assert client.for_topic(topics.sky_state) == []


def test_sky_tracks_the_best_satellite_count(module, client, topics, config_factory):
    stats = module.Stats()
    config = config_factory()

    for count in (4, 11, 7):
        module.handle_sky(
            client, topics, {"class": "SKY", "uSat": count}, config,
            module.Throttle(0), stats,
        )

    assert stats.max_satellites == 11


def test_sky_gates_position_on_the_satellite_requirement(
    module, client, topics, config_factory
):
    config = config_factory(min_n_satellites=6)
    stats = module.Stats()

    too_few = module.handle_sky(
        client, topics, {"class": "SKY", "uSat": 4}, config, module.Throttle(0), stats
    )
    enough = module.handle_sky(
        client, topics, {"class": "SKY", "uSat": 6}, config, module.Throttle(0), stats
    )

    assert too_few is False
    assert enough is True


def test_sky_gate_is_open_when_no_requirement_is_set(
    module, client, topics, config_factory
):
    stats = module.Stats()

    allowed = module.handle_sky(
        client, topics, {"class": "SKY", "uSat": 0}, config_factory(min_n_satellites=0),
        module.Throttle(0), stats,
    )

    assert allowed is True


# --- TPV -------------------------------------------------------------------


def test_tpv_publishes_a_normalised_position(module, client, topics, config_factory):
    stats = module.Stats()
    report = {"class": "TPV", "mode": 3, "lat": 59.9, "lon": 10.7}

    module.handle_tpv(
        client, topics, report, config_factory(), module.Throttle(0), stats
    )

    published = client.for_topic(topics.attr)[0].json()
    assert published["latitude"] == 59.9
    assert published["longitude"] == 10.7
    assert published["accuracy"] == "3D fix"
    assert stats.published_updates == 1


def test_tpv_position_updates_are_not_retained(module, client, topics, config_factory):
    module.handle_tpv(
        client, topics, {"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0},
        config_factory(), module.Throttle(0), module.Stats(),
    )

    assert client.for_topic(topics.attr)[0].retain is False


def test_tpv_withholds_a_poor_fix_by_default(module, client, topics, config_factory):
    stats = module.Stats()

    for mode in (1, 2):
        module.handle_tpv(
            client, topics, {"class": "TPV", "mode": mode, "lat": 1.0, "lon": 2.0},
            config_factory(publish_3d_fix_only=True), module.Throttle(0), stats,
        )

    assert client.for_topic(topics.attr) == []
    assert stats.published_updates == 0


def test_tpv_publishes_a_poor_fix_when_the_user_opts_in(
    module, client, topics, config_factory
):
    stats = module.Stats()

    module.handle_tpv(
        client, topics, {"class": "TPV", "mode": 2, "lat": 1.0, "lon": 2.0},
        config_factory(publish_3d_fix_only=False), module.Throttle(0), stats,
    )

    assert len(client.for_topic(topics.attr)) == 1


def test_tpv_records_accuracy_even_when_the_update_is_withheld(
    module, client, topics, config_factory
):
    """The summary should still report what was achieved, not stay blank."""
    stats = module.Stats()

    module.handle_tpv(
        client, topics, {"class": "TPV", "mode": 2, "lat": 1.0, "lon": 2.0},
        config_factory(publish_3d_fix_only=True), module.Throttle(0), stats,
    )

    assert stats.accuracy == "2D fix"


def test_tpv_updates_are_throttled(module, client, topics, config_factory):
    stats = module.Stats()
    throttle = module.Throttle(3600)
    config = config_factory()

    for _ in range(5):
        module.handle_tpv(
            client, topics, {"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0},
            config, throttle, stats,
        )

    assert client.for_topic(topics.attr) == []


def test_a_withheld_poor_fix_does_not_consume_the_throttle(
    module, client, topics, config_factory
):
    """A 2D fix must not reset the clock and delay the 3D fix that follows it."""
    stats = module.Stats()
    throttle = module.Throttle(0.01)
    config = config_factory(publish_3d_fix_only=True)

    import time

    time.sleep(0.05)
    module.handle_tpv(
        client, topics, {"class": "TPV", "mode": 2, "lat": 1.0, "lon": 2.0},
        config, throttle, stats,
    )
    module.handle_tpv(
        client, topics, {"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0},
        config, throttle, stats,
    )

    assert len(client.for_topic(topics.attr)) == 1
