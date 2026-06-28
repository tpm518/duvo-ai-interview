from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any


class StoreLinkNotFoundError(ValueError):
    """Raised when the mock StoreLink data set does not contain a resource."""


_STORES: dict[str, dict[str, Any]] = {
    "47": {
        "store_id": "47",
        "name": "Korral Amsterdam Centrum",
        "city": "Amsterdam",
        "country": "NL",
        "timezone": "Europe/Amsterdam",
    },
    "102": {
        "store_id": "102",
        "name": "Korral Rotterdam West",
        "city": "Rotterdam",
        "country": "NL",
        "timezone": "Europe/Amsterdam",
    },
    "118": {
        "store_id": "118",
        "name": "Korral Utrecht Noord",
        "city": "Utrecht",
        "country": "NL",
        "timezone": "Europe/Amsterdam",
    },
}

_INVENTORY: dict[tuple[str, str], dict[str, Any]] = {
    ("47", "8847291"): {
        "store_id": "47",
        "sku": "8847291",
        "sku_name": "Madeta butter 250g",
        "on_hand_units": 4,
        "as_of": "2026-06-28T08:45:00+00:00",
    },
    ("102", "8847291"): {
        "store_id": "102",
        "sku": "8847291",
        "sku_name": "Madeta butter 250g",
        "on_hand_units": 9,
        "as_of": "2026-06-28T08:40:00+00:00",
    },
    ("118", "8847291"): {
        "store_id": "118",
        "sku": "8847291",
        "sku_name": "Madeta butter 250g",
        "on_hand_units": 28,
        "as_of": "2026-06-28T08:30:00+00:00",
    },
}

_POS_TRANSACTIONS: list[dict[str, Any]] = [
    {
        "transaction_id": "pos-47-1001",
        "store_id": "47",
        "sku": "8847291",
        "units": 8,
        "sold_at": "2026-06-28T08:10:00+00:00",
    },
    {
        "transaction_id": "pos-47-1002",
        "store_id": "47",
        "sku": "8847291",
        "units": 5,
        "sold_at": "2026-06-28T06:45:00+00:00",
    },
    {
        "transaction_id": "pos-47-1003",
        "store_id": "47",
        "sku": "8847291",
        "units": 4,
        "sold_at": "2026-06-27T13:30:00+00:00",
    },
    {
        "transaction_id": "pos-47-0998",
        "store_id": "47",
        "sku": "8847291",
        "units": 7,
        "sold_at": "2026-06-26T16:15:00+00:00",
    },
    {
        "transaction_id": "pos-102-2001",
        "store_id": "102",
        "sku": "8847291",
        "units": 2,
        "sold_at": "2026-06-28T08:25:00+00:00",
    },
    {
        "transaction_id": "pos-102-2002",
        "store_id": "102",
        "sku": "8847291",
        "units": 3,
        "sold_at": "2026-06-27T18:10:00+00:00",
    },
    {
        "transaction_id": "pos-102-2003",
        "store_id": "102",
        "sku": "8847291",
        "units": 4,
        "sold_at": "2026-06-27T10:20:00+00:00",
    },
]


class MockStoreLinkClient:
    """In-memory StoreLink client used while the MCP surface is being built."""

    def __init__(self) -> None:
        self._stores = deepcopy(_STORES)
        self._inventory = deepcopy(_INVENTORY)
        self._pos_transactions = deepcopy(_POS_TRANSACTIONS)
        self._orders: dict[tuple[str, str], dict[str, Any]] = {}
        self._next_order_number = 1000

    def get_stores(self) -> list[dict[str, Any]]:
        return list(deepcopy(self._stores).values())

    def get_current_on_hand(self, store_id: str, sku: str) -> dict[str, Any]:
        self._require_store(store_id)

        inventory = self._inventory.get((store_id, sku))
        if inventory is None:
            raise StoreLinkNotFoundError(
                f"No inventory found for store {store_id} and SKU {sku}"
            )

        return deepcopy(inventory)

    def get_recent_pos_transactions(
        self,
        store_id: str,
        sku: str,
        since: str,
    ) -> list[dict[str, Any]]:
        self._require_store(store_id)
        since_at = _parse_timestamp(since)

        transactions = [
            transaction
            for transaction in self._pos_transactions
            if transaction["store_id"] == store_id
            and transaction["sku"] == sku
            and _parse_timestamp(transaction["sold_at"]) >= since_at
        ]
        transactions.sort(key=lambda transaction: transaction["sold_at"], reverse=True)
        return deepcopy(transactions)

    def raise_replenishment(
        self,
        store_id: str,
        sku: str,
        quantity: int,
    ) -> dict[str, Any]:
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        self.get_current_on_hand(store_id, sku)

        self._next_order_number += 1
        order_id = f"rep-{store_id}-{self._next_order_number}"
        order = {
            "order_id": order_id,
            "store_id": store_id,
            "sku": sku,
            "quantity": quantity,
            "status": "submitted",
            "created_at": "2026-06-28T09:00:00+00:00",
            "eta_date": "2026-07-01",
        }
        self._orders[(store_id, order_id)] = order
        return deepcopy(order)

    def get_order_status(self, store_id: str, order_id: str) -> dict[str, Any]:
        self._require_store(store_id)

        order = self._orders.get((store_id, order_id))
        if order is None:
            raise StoreLinkNotFoundError(
                f"No replenishment order found for store {store_id} and order {order_id}"
            )

        return deepcopy(order)

    def _require_store(self, store_id: str) -> None:
        if store_id not in self._stores:
            raise StoreLinkNotFoundError(f"No store found for store {store_id}")


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"

    return datetime.fromisoformat(value)
