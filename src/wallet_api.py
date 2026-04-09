from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests


@dataclass
class WalletResponse:
    payload: dict
    metadata: dict


class WalletApiClient:
    def __init__(self, token: str, recent_transactions_limit: int) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        self._base_url = "https://rest.budgetbakers.com/wallet/v1/api"
        self._recent_transactions_limit = recent_transactions_limit

    def fetch_accounts(self) -> WalletResponse:
        accounts = []
        offset = 0
        metadata = None

        while True:
            response = self._session.get(
                f"{self._base_url}/accounts",
                params={"limit": 200, "offset": offset, "agentHints": "true"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            accounts.extend(data.get("accounts", []))
            metadata = self._metadata_from_response(response)

            next_offset = data.get("nextOffset")
            if next_offset is None:
                break

            offset = int(next_offset)

        return WalletResponse(
            payload={
                "accounts": accounts,
                "fetchedAt": _utc_now(),
                "metadata": metadata,
            },
            metadata=metadata or {},
        )

    def fetch_recent_transactions(self) -> WalletResponse:
        response = self._session.get(
            f"{self._base_url}/records",
            params={"limit": self._recent_transactions_limit, "agentHints": "true"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        metadata = self._metadata_from_response(response)

        return WalletResponse(
            payload={
                "records": data.get("records", []),
                "fetchedAt": _utc_now(),
                "metadata": metadata,
            },
            metadata=metadata,
        )

    def fetch_account_records(self, account_id: str) -> WalletResponse:
        records = []
        offset = 0
        metadata = None

        while True:
            response = self._session.get(
                f"{self._base_url}/records",
                params={
                    "limit": 200,
                    "offset": offset,
                    "accountId": f"eq.{account_id}",
                    "agentHints": "true",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            records.extend(data.get("records", []))
            metadata = self._metadata_from_response(response)

            next_offset = data.get("nextOffset")
            if next_offset is None:
                break

            offset = int(next_offset)

        return WalletResponse(
            payload={
                "records": records,
                "fetchedAt": _utc_now(),
                "metadata": metadata,
            },
            metadata=metadata or {},
        )

    @staticmethod
    def _metadata_from_response(response: requests.Response) -> dict:
        return {
            "lastDataChangeAt": response.headers.get("X-Last-Data-Change-At"),
            "lastDataChangeRevision": response.headers.get("X-Last-Data-Change-Rev"),
            "syncInProgress": response.headers.get("X-Sync-In-Progress", "false").lower() == "true",
            "rateLimitRemaining": _to_int(response.headers.get("X-Ratelimit-Remaining")),
            "rateLimitLimit": _to_int(response.headers.get("X-Ratelimit-Limit")),
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
