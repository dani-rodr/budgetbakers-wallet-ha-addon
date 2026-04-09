import logging
import os
import signal
import sys
import re
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import __version__
from src.config import configure_logging, read_config
from src.mqtt_bridge import WalletMqttBridge
from src.wallet_api import WalletApiClient


logger = logging.getLogger(__name__)
_running = True


def _signal_handler(signum, frame):
    global _running
    logger.info("Received signal %s, shutting down...", signum)
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def main() -> None:
    bootstrap_config = read_config()
    configure_logging(bootstrap_config["log_level"])

    logger.info("Starting BudgetBakers Wallet app v%s...", __version__)
    logger.info(
        "Config: poll_interval_minutes=%s, topic=%s, publish=%s",
        bootstrap_config["poll_interval_minutes"],
        bootstrap_config["mqtt_topic_prefix"],
        ",".join(bootstrap_config["publish"]),
    )

    bridge = WalletMqttBridge(
        host=bootstrap_config["mqtt_host"],
        port=bootstrap_config["mqtt_port"],
        username=bootstrap_config["mqtt_username"],
        password=bootstrap_config["mqtt_password"],
        topic_prefix=bootstrap_config["mqtt_topic_prefix"],
        publish_targets=bootstrap_config["publish"],
    )

    if not bridge.connect():
        logger.error("Failed to connect to MQTT broker")
        sys.exit(1)

    bridge.publish_online()
    bridge.publish_discovery()

    client = WalletApiClient(
        token=bootstrap_config["wallet_token"],
        recent_transactions_limit=bootstrap_config["recent_transactions_limit"],
    )

    last_successful_sync_at = None
    last_successful_sync_at = do_sync(
        client,
        bridge,
        bootstrap_config,
        trigger="startup",
        last_successful_sync_at=last_successful_sync_at,
    )
    next_run = datetime.now(timezone.utc) + timedelta(minutes=bootstrap_config["poll_interval_minutes"])

    try:
        while _running:
            if bridge.scan_requested.wait(timeout=1):
                bridge.scan_requested.clear()
                last_successful_sync_at = do_sync(
                    client,
                    bridge,
                    bootstrap_config,
                    trigger="mqtt_button",
                    last_successful_sync_at=last_successful_sync_at,
                )
                next_run = datetime.now(timezone.utc) + timedelta(minutes=bootstrap_config["poll_interval_minutes"])
                continue

            if datetime.now(timezone.utc) >= next_run:
                last_successful_sync_at = do_sync(
                    client,
                    bridge,
                    bootstrap_config,
                    trigger="poll",
                    last_successful_sync_at=last_successful_sync_at,
                )
                next_run = datetime.now(timezone.utc) + timedelta(minutes=bootstrap_config["poll_interval_minutes"])

    finally:
        bridge.disconnect()
        logger.info("Goodbye.")


def do_sync(client: WalletApiClient, bridge: WalletMqttBridge, config: dict, trigger: str, last_successful_sync_at):
    started_at = datetime.now(timezone.utc).isoformat()
    metadata = {}

    try:
        logger.info("Running Wallet sync triggered by %s", trigger)

        if "accounts" in config["publish"]:
            accounts_response = client.fetch_accounts()
            bridge.publish_accounts(accounts_response.payload)
            bridge.publish_account_entities(_build_account_summaries(client, accounts_response.payload))
            metadata = accounts_response.metadata

        if "recent_transactions" in config["publish"]:
            transactions_response = client.fetch_recent_transactions()
            bridge.publish_transactions(transactions_response.payload)
            metadata = transactions_response.metadata

        completed_at = datetime.now(timezone.utc)

        if "status" in config["publish"]:
            bridge.publish_status_success(
                {
                    "trigger": trigger,
                    "state": "online",
                    "lastAttemptedSyncAt": started_at,
                    "lastSuccessfulSyncAt": completed_at.isoformat(),
                    "lastError": None,
                    "lastDataChangeAt": metadata.get("lastDataChangeAt"),
                    "lastDataChangeRevision": metadata.get("lastDataChangeRevision"),
                    "syncInProgress": metadata.get("syncInProgress"),
                    "rateLimitRemaining": metadata.get("rateLimitRemaining"),
                    "rateLimitLimit": metadata.get("rateLimitLimit"),
                }
            )
        return completed_at
    except Exception as exc:
        logger.error("Wallet sync failed: %s", exc, exc_info=True)
        if "status" in config["publish"]:
            bridge.publish_status_error(
                {
                    "trigger": trigger,
                    "state": "offline",
                    "lastAttemptedSyncAt": started_at,
                    "lastSuccessfulSyncAt": last_successful_sync_at.isoformat() if last_successful_sync_at else None,
                    "lastError": str(exc),
                }
            )
        return last_successful_sync_at
def _build_account_summaries(client: WalletApiClient, accounts_payload: dict) -> list[dict]:
    account_summaries = []

    for account in accounts_payload.get("accounts", []):
        account_id = account.get("id")
        if not account_id:
            continue

        account_records_response = client.fetch_account_records(account_id)
        records = account_records_response.payload.get("records", [])
        initial_balance = _get_initial_balance_value(account)
        currency_code = _get_currency_code(account, records)
        balance = None
        balance_source = "unknown"

        if initial_balance is not None:
            balance = initial_balance + sum(_record_amount(record) for record in records)
            balance_source = "derived"

        friendly_name = account.get("name") or account_id
        account_summaries.append(
            {
                "id": account_id,
                "slug": _slugify(f"{friendly_name}-{account_id[:8]}"),
                "friendlyName": friendly_name,
                "accountType": account.get("accountType"),
                "archived": bool(account.get("archived")),
                "excludeFromStats": bool(account.get("excludeFromStats")),
                "recordCount": account.get("recordStats", {}).get("recordCount", len(records)),
                "lastRecordDate": _max_record_date(records),
                "balance": round(balance, 2) if balance is not None else None,
                "currencyCode": currency_code,
                "balanceSource": balance_source,
                "fetchedAt": accounts_payload.get("fetchedAt"),
            }
        )

    return account_summaries


def _get_initial_balance_value(account: dict) -> float | None:
    for key in ("initialBalance", "initialBaseBalance"):
        value = account.get(key, {}).get("value")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _get_currency_code(account: dict, records: list[dict]) -> str | None:
    for key in ("initialBalance", "initialBaseBalance"):
        value = account.get(key, {}).get("currencyCode")
        if value:
            return value

    for record in records:
        value = record.get("amount", {}).get("currencyCode")
        if value:
            return value

    return None


def _record_amount(record: dict) -> float:
    value = record.get("amount", {}).get("value")
    return float(value) if isinstance(value, (int, float)) else 0.0


def _max_record_date(records: list[dict]) -> str | None:
    values = [record.get("recordDate") for record in records if record.get("recordDate")]
    return max(values) if values else None


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or "account"


if __name__ == "__main__":
    main()
