from __future__ import annotations

from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from duvo.credentials import FileStoreCredentialProvider, StoreCredentialError
from duvo.observability import FileObservability, ObservabilityMiddleware, audit_event
from duvo.storelink_mock import MockStoreLinkClient


INSTRUCTIONS = (
    "Use these tools for Korral StoreLink buyer workflows. Check current on-hand "
    "and recent POS before raising replenishment. raise_replenishment_order creates "
    "a StoreLink order; use exact store_id, sku, and quantity values."
)


def create_server(
    client: MockStoreLinkClient | None = None,
    credential_provider: FileStoreCredentialProvider | None = None,
    log_dir: str | Path | None = None,
) -> FastMCP:
    storelink = client or MockStoreLinkClient()
    credentials = credential_provider or FileStoreCredentialProvider()
    mcp = FastMCP("korral-storelink", instructions=INSTRUCTIONS)
    mcp.add_middleware(ObservabilityMiddleware(FileObservability(log_dir)))

    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

    @mcp.tool(annotations=read_only)
    def list_stores() -> list[dict[str, Any]]:
        """List Korral stores this MCP server has StoreLink credentials for."""
        credentialed_store_ids = set(credentials.list_store_ids())
        stores = [
            store
            for store in storelink.get_stores()
            if store["store_id"] in credentialed_store_ids
        ]
        audit_event(
            "listed_stores",
            f"Listed {len(stores)} credentialed StoreLink stores available to the MCP server.",
            store_count=len(stores),
        )
        return stores

    @mcp.tool(annotations=read_only)
    def get_current_on_hand(store_id: str, sku: str) -> dict[str, Any]:
        """Get current on-hand inventory units for one SKU at one store."""
        credential_error = _credential_error(credentials, store_id)
        if credential_error is not None:
            return credential_error

        inventory = storelink.get_current_on_hand(store_id, sku)
        audit_event(
            "checked_on_hand",
            (
                f"Checked on-hand for SKU {sku} at store {store_id}: "
                f"{inventory['on_hand_units']} units."
            ),
            store_id=store_id,
            sku=sku,
            sku_name=inventory["sku_name"],
            on_hand_units=inventory["on_hand_units"],
            as_of=inventory["as_of"],
        )
        return inventory

    @mcp.tool(annotations=read_only)
    def get_recent_pos_transactions(
        store_id: str,
        sku: str,
        since: str,
    ) -> dict[str, Any]:
        """Get POS transactions for one SKU at one store since an ISO timestamp."""
        credential_error = _credential_error(credentials, store_id)
        if credential_error is not None:
            return credential_error

        transactions = storelink.get_recent_pos_transactions(store_id, sku, since)
        result = {
            "store_id": store_id,
            "sku": sku,
            "since": since,
            "transaction_count": len(transactions),
            "total_units_sold": sum(transaction["units"] for transaction in transactions),
            "transactions": transactions,
        }
        audit_event(
            "checked_recent_pos",
            (
                f"Checked POS for SKU {sku} at store {store_id} since {since}: "
                f"{result['total_units_sold']} units sold."
            ),
            store_id=store_id,
            sku=sku,
            since=since,
            transaction_count=result["transaction_count"],
            total_units_sold=result["total_units_sold"],
        )
        return result

    @mcp.tool(
        annotations=ToolAnnotations(
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def raise_replenishment_order(
        store_id: str,
        sku: str,
        quantity: int,
    ) -> dict[str, Any]:
        """Create a replenishment order for one SKU at one store."""
        credential_error = _credential_error(credentials, store_id)
        if credential_error is not None:
            return credential_error

        order = storelink.raise_replenishment(store_id, sku, quantity)
        audit_event(
            "raised_replenishment_order",
            (
                f"Raised replenishment order {order['order_id']} for SKU {sku} "
                f"at store {store_id}: {quantity} units."
            ),
            store_id=store_id,
            sku=sku,
            quantity=quantity,
            order_id=order["order_id"],
            status=order["status"],
            eta_date=order["eta_date"],
        )
        return order

    @mcp.tool(annotations=read_only)
    def get_replenishment_order_status(store_id: str, order_id: str) -> dict[str, Any]:
        """Get the current status of a replenishment order."""
        credential_error = _credential_error(credentials, store_id)
        if credential_error is not None:
            return credential_error

        order = storelink.get_order_status(store_id, order_id)
        audit_event(
            "checked_replenishment_order_status",
            (
                f"Checked replenishment order {order_id} for store {store_id}: "
                f"{order['status']}."
            ),
            store_id=store_id,
            sku=order["sku"],
            quantity=order["quantity"],
            order_id=order_id,
            status=order["status"],
            eta_date=order["eta_date"],
        )
        return order

    return mcp


def _credential_error(
    credentials: FileStoreCredentialProvider,
    store_id: str,
) -> dict[str, Any] | None:
    try:
        status = credentials.get_status(store_id)
    except StoreCredentialError as exc:
        audit_event(
            "storelink_credentials_rejected",
            str(exc),
            store_id=store_id,
            error_code=exc.code,
            retryable=exc.retryable,
        )
        return {
            "error": {
                "code": exc.code,
                "message": str(exc),
                "store_id": store_id,
                "retryable": exc.retryable,
            }
        }

    if status["rotation_status"] == "rotation_due":
        audit_event(
            "storelink_credentials_rotation_due",
            (
                f"StoreLink credentials for store {store_id} are due to rotate "
                f"at {status['expires_at']}."
            ),
            store_id=store_id,
            credential_version=status["credential_version"],
            expires_at=status["expires_at"],
            rotation_status=status["rotation_status"],
        )

    return None


mcp = create_server()


if __name__ == "__main__":
    mcp.run()
