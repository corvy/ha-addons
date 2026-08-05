"""Report transformation, topic naming, throttling and the summary line."""

import logging
import time

# --- normalise_tpv ---------------------------------------------------------


def test_gpsd_fields_are_renamed_for_home_assistant(module):
    report = {"class": "TPV", "mode": 3, "lat": 59.9, "lon": 10.7, "alt": 12.5}

    result = module.normalise_tpv(report)

    assert result["latitude"] == 59.9
    assert result["longitude"] == 10.7
    assert result["altitude"] == 12.5
    # The gpsd names must be gone, or Home Assistant sees duplicate attributes.
    assert "lat" not in result
    assert "lon" not in result
    assert "alt" not in result


def test_absent_position_fields_are_not_invented(module):
    report = {"class": "TPV", "mode": 1}

    result = module.normalise_tpv(report)

    assert "latitude" not in result
    assert "longitude" not in result
    assert "altitude" not in result


def test_track_and_magtrack_are_published_as_null_when_absent(module):
    """gpsd stops sending these when stationary; explicit null stops HA expiring them."""
    report = {"class": "TPV", "mode": 3, "lat": 1.0, "lon": 2.0}

    result = module.normalise_tpv(report)

    assert result["track"] is None
    assert result["magtrack"] is None


def test_track_and_magtrack_are_preserved_when_present(module):
    report = {"class": "TPV", "mode": 3, "track": 187.4, "magtrack": 185.1}

    result = module.normalise_tpv(report)

    assert result["track"] == 187.4
    assert result["magtrack"] == 185.1


def test_mode_is_translated_to_a_readable_accuracy(module):
    assert module.normalise_tpv({"mode": 1})["accuracy"] == "No fix"
    assert module.normalise_tpv({"mode": 2})["accuracy"] == "2D fix"
    assert module.normalise_tpv({"mode": 3})["accuracy"] == "3D fix"


def test_unknown_mode_is_reported_as_unknown(module):
    assert module.normalise_tpv({})["accuracy"] == "Unknown"
    assert module.normalise_tpv({"mode": 0})["accuracy"] == "Unknown"


# --- Topics ----------------------------------------------------------------


def test_topic_names_are_stable(module):
    """These strings are a contract: changing one orphans every existing entity."""
    topics = module.Topics.for_device("abc12345")

    assert topics.config == "homeassistant/device_tracker/gpsd2mqtt/abc12345/config"
    assert topics.attr == "gpsd2mqtt/abc12345/attribute"
    assert topics.sky_config == "homeassistant/sensor/gpsd2mqtt/abc12345_sky/config"
    assert topics.sky_state == "gpsd2mqtt/abc12345_sky/state"
    assert topics.sky_attr == "gpsd2mqtt/abc12345_sky/attribute"
    assert topics.availability == "gpsd2mqtt/abc12345/availability"


def test_unique_identifier_is_stable_and_short(module):
    first = module.get_unique_identifier()
    second = module.get_unique_identifier()

    assert first == second
    assert len(first) == 8


# --- Throttle --------------------------------------------------------------


def test_zero_interval_disables_throttling(module):
    throttle = module.Throttle(0)

    assert throttle.ready()
    throttle.mark()
    assert throttle.ready(), "interval 0 means publish every update"


def test_throttle_withholds_until_the_interval_has_passed(module):
    throttle = module.Throttle(3600)

    throttle.mark()

    assert not throttle.ready()


def test_throttle_becomes_ready_after_the_interval(module):
    throttle = module.Throttle(0.01)

    throttle.mark()
    time.sleep(0.05)

    assert throttle.ready()


def test_throttle_reads_the_monotonic_clock(module, monkeypatch):
    """A backwards wall-clock step must not withhold updates until time catches up."""

    def forbidden():
        raise AssertionError("Throttle must not read the wall clock")

    clock = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module.time, "time", forbidden)

    throttle = module.Throttle(60)
    throttle.mark()

    assert not throttle.ready()

    clock[0] += 60

    assert throttle.ready()


def test_throttles_are_independent(module):
    """SKY and TPV share an interval but must not share a clock.

    Before 2026.8.0 a single timestamp was used for both, so SKY updates were only
    rate-limited when a TPV update happened to reset it -- and streamed unthrottled
    whenever TPV was being withheld by the satellite requirement.
    """
    sky = module.Throttle(0.01)
    tpv = module.Throttle(0.01)

    time.sleep(0.05)
    assert sky.ready() and tpv.ready()

    sky.mark()

    assert not sky.ready()
    assert tpv.ready(), "marking one throttle must not affect the other"


# --- Stats -----------------------------------------------------------------


def test_summary_omits_the_requirement_when_none_is_configured(
    module, config_factory, caplog
):
    """"of required 0 GPS satellites" was noise; fixed in 2026.8.0."""
    stats = module.Stats(published_updates=4, max_satellites=9, accuracy="3D fix")

    with caplog.at_level(logging.INFO, logger="gpsd2mqtt"):
        stats.emit(config_factory(min_n_satellites=0))

    assert "required" not in caplog.text
    assert "9 GPS satellites" in caplog.text


def test_summary_reports_the_requirement_when_it_is_met(module, config_factory, caplog):
    stats = module.Stats(published_updates=4, max_satellites=9, accuracy="3D fix")

    with caplog.at_level(logging.INFO, logger="gpsd2mqtt"):
        stats.emit(config_factory(min_n_satellites=5))

    assert "9 of required 5" in caplog.text
    assert "not at configured accuracy" not in caplog.text


def test_summary_flags_a_shortfall(module, config_factory, caplog):
    stats = module.Stats(published_updates=0, max_satellites=2, accuracy="2D fix")

    with caplog.at_level(logging.INFO, logger="gpsd2mqtt"):
        stats.emit(config_factory(min_n_satellites=6))

    assert "not at configured accuracy" in caplog.text
    assert "2 of required 6" in caplog.text


def test_emit_resets_the_counters(module, config_factory, caplog):
    stats = module.Stats(published_updates=11, max_satellites=8, accuracy="3D fix")

    with caplog.at_level(logging.INFO, logger="gpsd2mqtt"):
        stats.emit(config_factory())

    assert stats.published_updates == 0
    assert stats.max_satellites == 0


def test_summary_is_not_due_immediately(module):
    stats = module.Stats()

    assert not stats.due(3600)


def test_summary_reports_seconds_when_the_interval_is_short(
    module, config_factory, caplog
):
    """"in last 0 minutes" reads as a bug; sub-minute intervals are configurable."""
    stats = module.Stats(published_updates=1, max_satellites=5, accuracy="3D fix")

    with caplog.at_level(logging.INFO, logger="gpsd2mqtt"):
        stats.emit(config_factory())

    assert "0 minutes" not in caplog.text
    assert "seconds" in caplog.text


def test_summary_before_any_fix_does_not_say_none(module, config_factory, caplog):
    """The first summary can land before any TPV has arrived."""
    stats = module.Stats()

    with caplog.at_level(logging.INFO, logger="gpsd2mqtt"):
        stats.emit(config_factory())

    assert "Achieved None" not in caplog.text


def test_clocks_are_monotonic(module):
    """Wall clock would stall every publish if chrony stepped the clock backwards.

    gpsd is itself a common time source on these installs, so this is not
    hypothetical.
    """
    throttle = module.Throttle(10)
    stats = module.Stats()

    # A wall-clock implementation would hold a datetime here, not a float from
    # time.monotonic(). Monotonic values are also unrelated to the epoch.
    assert isinstance(throttle._last, float)
    assert isinstance(stats.last_summary, float)
    assert throttle._last < time.time() - 3600 * 24
    assert stats.last_summary < time.time() - 3600 * 24
