from __future__ import annotations

import json
import logging
import threading
from typing import Iterable

import paho.mqtt.client as mqtt


logger = logging.getLogger(__name__)


class WalletMqttBridge:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        topic_prefix: str,
        publish_targets: Iterable[str],
    ) -> None:
        self.topic_prefix = topic_prefix.strip("/")
        self.publish_targets = {item.lower() for item in publish_targets}
        self.scan_requested = threading.Event()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{self.topic_prefix}_addon")
        if username:
            self._client.username_pw_set(username, password)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._host = host
        self._port = port
        self._connected = threading.Event()
        self._device = {
            "identifiers": ["budgetbakers_wallet_addon"],
            "name": "BudgetBakers Wallet",
            "manufacturer": "BudgetBakers",
            "model": "Wallet REST Add-on",
            "sw_version": "0.1.0",
        }
        self._published_account_discovery = set()

    def connect(self) -> bool:
        try:
            self._client.will_set(self._topic("availability"), payload="offline", retain=True)
            self._client.connect(self._host, self._port, keepalive=60)
            self._client.loop_start()
            connected = self._connected.wait(timeout=10)
            return connected
        except Exception as exc:
            logger.error("Failed to connect to MQTT broker: %s", exc)
            return False

    def disconnect(self) -> None:
        try:
            self.publish_offline()
        finally:
            self._client.loop_stop()
            self._client.disconnect()

    def publish_online(self) -> None:
        self._publish(self._topic("availability"), "online", retain=True)

    def publish_offline(self) -> None:
        self._publish(self._topic("availability"), "offline", retain=True)

    def publish_discovery(self) -> None:
        self._publish_discovery(
            "button",
            "sync_now",
            {
                "name": "BudgetBakers Wallet Sync Now",
                "unique_id": "budgetbakers_wallet_sync_now",
                "command_topic": self._topic("command/sync"),
                "payload_press": "now",
                "availability_topic": self._topic("availability"),
                "payload_available": "online",
                "payload_not_available": "offline",
                "icon": "mdi:refresh",
                "device": self._device,
            },
        )

        if "status" in self.publish_targets:
            self._publish_discovery(
                "binary_sensor",
                "api_status",
                {
                    "name": "BudgetBakers Wallet API Status",
                    "unique_id": "budgetbakers_wallet_api_status",
                    "state_topic": self._topic("status/state"),
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "json_attributes_topic": self._topic("status/attributes"),
                    "availability_topic": self._topic("availability"),
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "icon": "mdi:api",
                    "device": self._device,
                },
            )
            self._publish_discovery(
                "sensor",
                "last_sync",
                {
                    "name": "BudgetBakers Wallet Last Sync",
                    "unique_id": "budgetbakers_wallet_last_sync",
                    "state_topic": self._topic("last_sync"),
                    "value_template": "{{ value_json.lastSuccessfulSyncAt }}",
                    "json_attributes_topic": self._topic("last_sync"),
                    "availability_topic": self._topic("availability"),
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "device_class": "timestamp",
                    "icon": "mdi:clock-check-outline",
                    "device": self._device,
                },
            )

        if "accounts" in self.publish_targets:
            self._publish_discovery(
                "sensor",
                "accounts_count",
                {
                    "name": "BudgetBakers Wallet Accounts",
                    "unique_id": "budgetbakers_wallet_accounts_count",
                    "state_topic": self._topic("accounts/summary"),
                    "value_template": "{{ value_json.count }}",
                    "json_attributes_topic": self._topic("accounts/summary"),
                    "availability_topic": self._topic("availability"),
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "icon": "mdi:wallet-outline",
                    "device": self._device,
                },
            )

        if "recent_transactions" in self.publish_targets:
            self._publish_discovery(
                "sensor",
                "recent_transaction_count",
                {
                    "name": "BudgetBakers Wallet Recent Transactions",
                    "unique_id": "budgetbakers_wallet_recent_transaction_count",
                    "state_topic": self._topic("transactions/recent/summary"),
                    "value_template": "{{ value_json.count }}",
                    "json_attributes_topic": self._topic("transactions/recent/summary"),
                    "availability_topic": self._topic("availability"),
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "icon": "mdi:receipt-text-clock-outline",
                    "device": self._device,
                },
            )

    def publish_account_entities(self, account_summaries: list[dict]) -> None:
        for account in account_summaries:
            account_topic = self._account_topic(account["slug"])
            self._publish_json(account_topic, account)

            if account["slug"] in self._published_account_discovery:
                continue

            self._publish_account_discovery(account)
            self._published_account_discovery.add(account["slug"])

    def publish_status_success(self, attributes: dict) -> None:
        self._publish(self._topic("status/state"), "ON", retain=True)
        self._publish_json(self._topic("status/attributes"), attributes)
        self._publish_json(self._topic("last_sync"), attributes)

    def publish_status_error(self, attributes: dict) -> None:
        self._publish(self._topic("status/state"), "OFF", retain=True)
        self._publish_json(self._topic("status/attributes"), attributes)

    def publish_accounts(self, payload: dict) -> None:
        self._publish_json(self._topic("accounts/raw"), payload)
        accounts = payload.get("accounts", [])
        summary = {
            "count": len(accounts),
            "names": sorted([account.get("name") for account in accounts if account.get("name")]),
            "types": sorted(list({account.get("accountType") for account in accounts if account.get("accountType")})),
            "archivedCount": len([account for account in accounts if account.get("archived")]),
            "fetchedAt": payload.get("fetchedAt"),
        }
        self._publish_json(self._topic("accounts/summary"), summary)

    def publish_transactions(self, payload: dict) -> None:
        self._publish_json(self._topic("transactions/recent/raw"), payload)
        records = payload.get("records", [])
        summary = {
            "count": len(records),
            "latestRecordDate": max((record.get("recordDate") for record in records if record.get("recordDate")), default=None),
            "latestUpdatedAt": max((record.get("updatedAt") for record in records if record.get("updatedAt")), default=None),
            "categories": sorted(list({record.get("category", {}).get("name") for record in records if record.get("category", {}).get("name")})),
            "fetchedAt": payload.get("fetchedAt"),
        }
        self._publish_json(self._topic("transactions/recent/summary"), summary)

    def _publish_discovery(self, component: str, object_id: str, payload: dict) -> None:
        topic = f"homeassistant/{component}/{self.topic_prefix}_{object_id}/config"
        self._publish_json(topic, payload)

    def _publish_account_discovery(self, account: dict) -> None:
        slug = account["slug"]
        name = account["friendlyName"]
        account_topic = self._account_topic(slug)
        base_object_id = f"account_{slug}"

        self._publish_discovery(
            "sensor",
            f"{base_object_id}_balance",
            {
                "name": f"{name} Balance",
                "unique_id": f"budgetbakers_wallet_{slug}_balance",
                "state_topic": account_topic,
                "value_template": "{{ value_json.balance if value_json.balance is not none else 'unknown' }}",
                "json_attributes_topic": account_topic,
                "availability_topic": self._topic("availability"),
                "payload_available": "online",
                "payload_not_available": "offline",
                "icon": "mdi:cash",
                "device": self._device,
            },
        )
        self._publish_discovery(
            "sensor",
            f"{base_object_id}_currency",
            {
                "name": f"{name} Currency",
                "unique_id": f"budgetbakers_wallet_{slug}_currency",
                "state_topic": account_topic,
                "value_template": "{{ value_json.currencyCode if value_json.currencyCode else 'unknown' }}",
                "json_attributes_topic": account_topic,
                "availability_topic": self._topic("availability"),
                "payload_available": "online",
                "payload_not_available": "offline",
                "icon": "mdi:currency-php",
                "device": self._device,
            },
        )
        self._publish_discovery(
            "sensor",
            f"{base_object_id}_record_count",
            {
                "name": f"{name} Record Count",
                "unique_id": f"budgetbakers_wallet_{slug}_record_count",
                "state_topic": account_topic,
                "value_template": "{{ value_json.recordCount }}",
                "json_attributes_topic": account_topic,
                "availability_topic": self._topic("availability"),
                "payload_available": "online",
                "payload_not_available": "offline",
                "icon": "mdi:counter",
                "device": self._device,
            },
        )
        self._publish_discovery(
            "sensor",
            f"{base_object_id}_last_record_date",
            {
                "name": f"{name} Last Record Date",
                "unique_id": f"budgetbakers_wallet_{slug}_last_record_date",
                "state_topic": account_topic,
                "value_template": "{{ value_json.lastRecordDate if value_json.lastRecordDate else 'unknown' }}",
                "json_attributes_topic": account_topic,
                "availability_topic": self._topic("availability"),
                "payload_available": "online",
                "payload_not_available": "offline",
                "device_class": "timestamp",
                "icon": "mdi:calendar-clock",
                "device": self._device,
            },
        )
        self._publish_discovery(
            "binary_sensor",
            f"{base_object_id}_archived",
            {
                "name": f"{name} Archived",
                "unique_id": f"budgetbakers_wallet_{slug}_archived",
                "state_topic": account_topic,
                "value_template": "{{ 'ON' if value_json.archived else 'OFF' }}",
                "payload_on": "ON",
                "payload_off": "OFF",
                "json_attributes_topic": account_topic,
                "availability_topic": self._topic("availability"),
                "payload_available": "online",
                "payload_not_available": "offline",
                "icon": "mdi:archive",
                "device": self._device,
            },
        )

    def _publish_json(self, topic: str, payload: dict) -> None:
        self._publish(topic, json.dumps(payload, separators=(",", ":")), retain=True)

    def _publish(self, topic: str, payload: str, retain: bool) -> None:
        self._client.publish(topic, payload=payload, qos=1, retain=retain)

    def _topic(self, suffix: str) -> str:
        return f"{self.topic_prefix}/{suffix}"

    def _account_topic(self, slug: str) -> str:
        return self._topic(f"accounts/{slug}/summary")

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            self._connected.set()
            client.subscribe(self._topic("command/sync"), qos=1)
            logger.info("Connected to MQTT broker and subscribed to %s", self._topic("command/sync"))
        else:
            logger.error("MQTT connection failed with reason code %s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self._connected.clear()
        logger.warning("Disconnected from MQTT broker: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        payload = message.payload.decode("utf-8").strip().lower()
        if payload == "now":
            logger.info("Manual sync requested via MQTT")
            self.scan_requested.set()
