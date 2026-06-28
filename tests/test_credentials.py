import json
from datetime import UTC, datetime

import pytest

from duvo.credentials import (
    FileStoreCredentialProvider,
    StoreCredentialNotFoundError,
)


def test_file_provider_loads_one_store_credential(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    write_credentials(path, api_key="store-47-key", version="v1")
    provider = FileStoreCredentialProvider(path)

    credential = provider.get_credential("47")

    assert provider.list_store_ids() == ["47"]
    assert credential.store_id == "47"
    assert credential.api_key == "store-47-key"
    assert credential.version == "v1"


def test_file_provider_does_not_guess_credentials_for_other_stores(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    write_credentials(path, api_key="store-47-key", version="v1")
    provider = FileStoreCredentialProvider(path)

    with pytest.raises(StoreCredentialNotFoundError) as exc:
        provider.get_credential("102")

    assert exc.value.code == "missing_store_credentials"
    assert exc.value.retryable is False


def test_file_provider_reads_rotated_key_on_next_lookup(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    write_credentials(path, api_key="old-store-47-key", version="v1")
    provider = FileStoreCredentialProvider(path)

    assert provider.get_credential("47").version == "v1"

    write_credentials(path, api_key="new-store-47-key", version="v2")

    credential = provider.get_credential("47")
    assert credential.api_key == "new-store-47-key"
    assert credential.version == "v2"


def test_file_provider_reports_rotation_status(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    write_credentials(
        path,
        api_key="store-47-key",
        version="v1",
        expires_at="2026-06-29T00:00:00Z",
    )
    provider = FileStoreCredentialProvider(path)

    status = provider.get_status("47", now=datetime(2026, 6, 28, 12, tzinfo=UTC))

    assert status == {
        "store_id": "47",
        "credential_version": "v1",
        "expires_at": "2026-06-29T00:00:00+00:00",
        "rotation_status": "rotation_due",
    }


def write_credentials(
    path,
    *,
    api_key: str,
    version: str,
    expires_at: str = "2030-01-01T00:00:00Z",
) -> None:
    path.write_text(
        json.dumps(
            {
                "stores": {
                    "47": {
                        "api_key": api_key,
                        "version": version,
                        "expires_at": expires_at,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
