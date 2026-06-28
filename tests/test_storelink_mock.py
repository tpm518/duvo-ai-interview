import pytest

from duvo.storelink_mock import MockStoreLinkClient, StoreLinkNotFoundError


def test_get_stores_includes_pilot_stores() -> None:
    client = MockStoreLinkClient()

    stores = client.get_stores()

    store_ids = {store["store_id"] for store in stores}
    assert {"47", "102"}.issubset(store_ids)


def test_get_current_on_hand_for_madeta_butter() -> None:
    client = MockStoreLinkClient()

    inventory = client.get_current_on_hand("47", "8847291")

    assert inventory == {
        "store_id": "47",
        "sku": "8847291",
        "sku_name": "Madeta butter 250g",
        "on_hand_units": 4,
        "as_of": "2026-06-28T08:45:00+00:00",
    }


def test_get_recent_pos_transactions_filters_by_store_sku_and_since() -> None:
    client = MockStoreLinkClient()

    transactions = client.get_recent_pos_transactions(
        "47",
        "8847291",
        "2026-06-27T09:00:00+00:00",
    )

    assert [transaction["transaction_id"] for transaction in transactions] == [
        "pos-47-1001",
        "pos-47-1002",
        "pos-47-1003",
    ]
    assert sum(transaction["units"] for transaction in transactions) == 17


def test_replenishment_order_can_be_created_and_checked() -> None:
    client = MockStoreLinkClient()

    order = client.raise_replenishment("47", "8847291", 24)

    assert order["order_id"] == "rep-47-1001"
    assert order["status"] == "submitted"
    assert client.get_order_status("47", "rep-47-1001") == order


def test_missing_inventory_is_informative() -> None:
    client = MockStoreLinkClient()

    with pytest.raises(StoreLinkNotFoundError, match="No inventory found"):
        client.get_current_on_hand("47", "missing-sku")
