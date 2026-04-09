import json
import logging
import os
import urllib.request


DEFAULT_CONFIG = {
    "wallet_token": "",
    "poll_interval_minutes": 15,
    "mqtt_topic_prefix": "wallet_budgetbakers",
    "recent_transactions_limit": 10,
    "balance_overrides": [],
    "publish": ["accounts", "recent_transactions", "status"],
    "log_level": "info",
    "mqtt_host": None,
    "mqtt_port": 1883,
    "mqtt_username": None,
    "mqtt_password": None,
}


def read_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    options_path = "/data/options.json"

    if os.path.isfile(options_path):
        with open(options_path, encoding="utf-8") as handle:
            options = json.load(handle)

        config["wallet_token"] = options.get("wallet_token", config["wallet_token"])
        config["poll_interval_minutes"] = int(options.get("poll_interval_minutes", config["poll_interval_minutes"]))
        config["mqtt_topic_prefix"] = options.get("mqtt_topic_prefix", config["mqtt_topic_prefix"])
        config["recent_transactions_limit"] = int(options.get("recent_transactions_limit", config["recent_transactions_limit"]))
        config["balance_overrides"] = _normalize_balance_overrides(options.get("balance_overrides", config["balance_overrides"]))
        config["publish"] = options.get("publish", config["publish"])
        config["log_level"] = options.get("log_level", config["log_level"])

    config.update(_get_mqtt_from_supervisor())

    if not config["mqtt_host"]:
        config["mqtt_host"] = os.environ.get("MQTT_HOST")
        config["mqtt_port"] = int(os.environ.get("MQTT_PORT", config["mqtt_port"]))
        config["mqtt_username"] = os.environ.get("MQTT_USERNAME")
        config["mqtt_password"] = os.environ.get("MQTT_PASSWORD")

    if os.environ.get("WALLET_TOKEN"):
        config["wallet_token"] = os.environ["WALLET_TOKEN"]

    if not config["wallet_token"]:
        raise RuntimeError("Configuration value 'wallet_token' is required")

    if not config["mqtt_host"]:
        raise RuntimeError("No MQTT broker configured. Install Mosquitto or expose MQTT_HOST variables.")

    return config


def configure_logging(log_level: str) -> None:
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    logging.basicConfig(
        level=level_map.get(str(log_level).lower(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _normalize_balance_overrides(raw_overrides: list[dict] | None) -> list[dict]:
    if not raw_overrides:
        return []

    normalized = []
    for index, item in enumerate(raw_overrides, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"Configuration value 'balance_overrides[{index}]' must be an object")

        account_id = _optional_string(item.get("account_id"))
        account_name = _optional_string(item.get("account_name") or item.get("account"))
        if not account_id and not account_name:
            raise RuntimeError(
                f"Configuration value 'balance_overrides[{index}]' requires 'account_id' or 'account_name'"
            )

        starting_balance = item.get("starting_balance")
        if not isinstance(starting_balance, (int, float)):
            raise RuntimeError(f"Configuration value 'balance_overrides[{index}].starting_balance' must be numeric")

        as_of = _optional_string(item.get("as_of"))
        if not as_of:
            raise RuntimeError(f"Configuration value 'balance_overrides[{index}].as_of' is required")

        normalized.append(
            {
                "account_id": account_id,
                "account_name": account_name,
                "starting_balance": float(starting_balance),
                "as_of": as_of,
            }
        )

    return normalized


def _optional_string(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_mqtt_from_supervisor() -> dict:
    result = {
        "mqtt_host": None,
        "mqtt_port": 1883,
        "mqtt_username": None,
        "mqtt_password": None,
    }

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return result

    try:
        request = urllib.request.Request(
            "http://supervisor/services/mqtt",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        data = payload.get("data", payload)
        result["mqtt_host"] = data.get("host")
        result["mqtt_port"] = int(data.get("port", 1883))
        result["mqtt_username"] = data.get("username")
        result["mqtt_password"] = data.get("password")
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not get MQTT settings from Supervisor: %s", exc)

    return result
