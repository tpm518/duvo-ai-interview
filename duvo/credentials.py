from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_CREDENTIALS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "storelink_credentials.json"
)
ROTATION_WARNING_WINDOW = timedelta(days=1)


class StoreCredentialError(ValueError):
    def __init__(
        self,
        *,
        code: str,
        store_id: str,
        message: str,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.store_id = store_id
        self.retryable = retryable


class StoreCredentialNotFoundError(StoreCredentialError):
    def __init__(self, store_id: str) -> None:
        super().__init__(
            code="missing_store_credentials",
            store_id=store_id,
            message=f"No StoreLink credentials are configured for store {store_id}.",
            retryable=False,
        )


class StoreCredentialExpiredError(StoreCredentialError):
    def __init__(self, store_id: str, expires_at: datetime) -> None:
        super().__init__(
            code="expired_store_credentials",
            store_id=store_id,
            message=(
                f"StoreLink credentials for store {store_id} expired at "
                f"{expires_at.isoformat()}."
            ),
            retryable=False,
        )


@dataclass(frozen=True)
class StoreCredential:
    store_id: str
    api_key: str
    version: str
    expires_at: datetime | None

    def status(self, now: datetime | None = None) -> dict[str, Any]:
        checked_at = now or datetime.now(UTC)

        if self.expires_at is None:
            rotation_status = "unknown"
            expires_at = None
        else:
            expires_at = self.expires_at.isoformat()
            if self.expires_at <= checked_at:
                rotation_status = "expired"
            elif self.expires_at <= checked_at + ROTATION_WARNING_WINDOW:
                rotation_status = "rotation_due"
            else:
                rotation_status = "active"

        return {
            "store_id": self.store_id,
            "credential_version": self.version,
            "expires_at": expires_at,
            "rotation_status": rotation_status,
        }


class FileStoreCredentialProvider:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(
            path
            or os.environ.get("STORELINK_CREDENTIALS_PATH")
            or DEFAULT_CREDENTIALS_PATH
        )

    def list_store_ids(self) -> list[str]:
        return sorted(self._load_credentials())

    def get_credential(self, store_id: str) -> StoreCredential:
        credential = self._load_credentials().get(store_id)
        if credential is None:
            raise StoreCredentialNotFoundError(store_id)

        if credential.expires_at is not None and credential.expires_at <= datetime.now(
            UTC
        ):
            raise StoreCredentialExpiredError(store_id, credential.expires_at)

        return credential

    def get_status(self, store_id: str, now: datetime | None = None) -> dict[str, Any]:
        return self.get_credential(store_id).status(now)

    def refresh(self, store_id: str) -> StoreCredential:
        return self.get_credential(store_id)

    def _load_credentials(self) -> dict[str, StoreCredential]:
        if not self.path.exists():
            return {}

        data = json.loads(self.path.read_text(encoding="utf-8"))
        stores = data.get("stores")
        if not isinstance(stores, dict):
            raise ValueError("StoreLink credentials file must contain a stores object.")

        credentials: dict[str, StoreCredential] = {}
        for store_id, record in stores.items():
            if not isinstance(record, dict):
                raise ValueError(f"Credentials for store {store_id} must be an object.")

            api_key = record.get("api_key")
            if not isinstance(api_key, str) or not api_key:
                raise ValueError(f"Credentials for store {store_id} must include api_key.")

            version = record.get("version")
            if not isinstance(version, str) or not version:
                raise ValueError(f"Credentials for store {store_id} must include version.")

            expires_at = record.get("expires_at")
            if expires_at is not None and not isinstance(expires_at, str):
                raise ValueError(
                    f"Credentials for store {store_id} expires_at must be a string."
                )

            credentials[str(store_id)] = StoreCredential(
                store_id=str(store_id),
                api_key=api_key,
                version=version,
                expires_at=_parse_datetime(expires_at) if expires_at is not None else None,
            )

        return credentials


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Credential timestamps must include a timezone.")

    return parsed.astimezone(UTC)
