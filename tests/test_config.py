"""Option parsing.

Three of these encode bugs fixed in 2026.8.0: a password containing spaces was
truncated, the password was written to the log at debug level, and `publish_interval: 0`
was silently replaced by the default.
"""

import json
import logging


def write_options(tmp_path, options):
    path = tmp_path / "options.json"
    path.write_text(json.dumps(options))
    return path


def test_publish_interval_zero_is_preserved(module, tmp_path):
    """0 means "publish every update" and must survive; `or` would swallow it."""
    path = write_options(tmp_path, {"device": "/dev/ttyS0", "publish_interval": 0})

    config = module.Config.load(path)

    assert config.publish_interval == 0


def test_publish_interval_defaults_when_absent(module, tmp_path):
    path = write_options(tmp_path, {"device": "/dev/ttyS0"})

    config = module.Config.load(path)

    assert config.publish_interval == 10


def test_defaults_are_applied(module, tmp_path):
    path = write_options(tmp_path, {"device": "/dev/ttyS0"})

    config = module.Config.load(path)

    assert config.baudrate == 9600
    assert config.mqtt_broker == "core-mosquitto"
    assert config.mqtt_port == 1883
    assert config.summary_interval == 120
    assert config.min_n_satellites == 0
    assert config.publish_3d_fix_only is True
    assert config.debug is False


def test_configured_values_win_over_defaults(module, tmp_path):
    path = write_options(
        tmp_path,
        {
            "device": "/dev/ttyUSB0",
            "baudrate": 38400,
            "mqtt_broker": "192.168.1.10",
            "mqtt_port": 8883,
            "min_n_satellites": 7,
            "summary_interval": 300,
            "publish_3d_fix_only": False,
            "debug": True,
        },
    )

    config = module.Config.load(path)

    assert config.device == "/dev/ttyUSB0"
    assert config.baudrate == 38400
    assert config.mqtt_broker == "192.168.1.10"
    assert config.mqtt_port == 8883
    assert config.min_n_satellites == 7
    assert config.summary_interval == 300
    assert config.publish_3d_fix_only is False
    assert config.debug is True


def test_environment_credentials_win_over_options(module, tmp_path, monkeypatch):
    """run.sh resolves Home Assistant's integrated credentials and exports them."""
    monkeypatch.setenv("MQTT_USER", "from-env")
    monkeypatch.setenv("MQTT_PASSWORD", "env-secret")
    path = write_options(
        tmp_path,
        {"device": "/dev/ttyS0", "mqtt_username": "from-file", "mqtt_pw": "file-secret"},
    )

    config = module.Config.load(path)

    assert config.mqtt_username == "from-env"
    assert config.mqtt_password == "env-secret"


def test_options_credentials_used_when_environment_is_empty(module, tmp_path, monkeypatch):
    monkeypatch.delenv("MQTT_USER", raising=False)
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)
    path = write_options(
        tmp_path,
        {"device": "/dev/ttyS0", "mqtt_username": "manual", "mqtt_pw": "manual-secret"},
    )

    config = module.Config.load(path)

    assert config.mqtt_username == "manual"
    assert config.mqtt_password == "manual-secret"


def test_password_with_spaces_survives_intact(module, tmp_path, monkeypatch):
    """Passing credentials via argv used to split this into separate arguments."""
    monkeypatch.setenv("MQTT_USER", "user")
    monkeypatch.setenv("MQTT_PASSWORD", "two words and more")
    path = write_options(tmp_path, {"device": "/dev/ttyS0"})

    config = module.Config.load(path)

    assert config.mqtt_password == "two words and more"


def test_missing_credentials_become_empty_strings(module, tmp_path, monkeypatch):
    monkeypatch.delenv("MQTT_USER", raising=False)
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)
    path = write_options(tmp_path, {"device": "/dev/ttyS0"})

    config = module.Config.load(path)

    assert config.mqtt_username == ""
    assert config.mqtt_password == ""


def test_log_options_never_logs_the_password(module, config_factory, caplog):
    config = config_factory(mqtt_password="hunter2-should-never-appear")

    with caplog.at_level(logging.DEBUG, logger="gpsd2mqtt"):
        config.log_options()

    assert caplog.text, "expected log_options to emit something at debug level"
    assert "hunter2-should-never-appear" not in caplog.text
    # The username is fine to log, and confirms the fixture really ran.
    assert config.mqtt_username in caplog.text
