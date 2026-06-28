import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastmcp import Client

from duvo.credentials import FileStoreCredentialProvider
from duvo.mcp_server import create_server
from duvo.storelink_mock import MockStoreLinkClient


def test_mcp_server_exposes_buyer_workflow_tools(tmp_path) -> None:
    async def run() -> None:
        server = create_server(MockStoreLinkClient(), log_dir=tmp_path)

        async with Client(server) as client:
            tools = await client.list_tools()

        assert {tool.name for tool in tools} == {
            "list_stores",
            "get_current_on_hand",
            "get_recent_pos_transactions",
            "raise_replenishment_order",
            "get_replenishment_order_status",
        }

    asyncio.run(run())


def test_mcp_server_lists_only_credentialed_stores(tmp_path) -> None:
    async def run() -> None:
        server = create_server(
            MockStoreLinkClient(),
            credential_provider=FileStoreCredentialProvider(
                write_credentials(tmp_path / "credentials.json")
            ),
            log_dir=tmp_path,
        )

        async with Client(server) as client:
            stores = await client.call_tool("list_stores", {})

        assert [store["store_id"] for store in stores.data] == ["47"]

    asyncio.run(run())


def test_mcp_server_can_complete_inventory_pos_and_order_flow(tmp_path) -> None:
    async def run() -> None:
        server = create_server(MockStoreLinkClient(), log_dir=tmp_path)

        async with Client(server) as client:
            inventory = await client.call_tool(
                "get_current_on_hand",
                {"store_id": "47", "sku": "8847291"},
            )
            pos = await client.call_tool(
                "get_recent_pos_transactions",
                {
                    "store_id": "47",
                    "sku": "8847291",
                    "since": "2026-06-27T09:00:00+00:00",
                },
            )
            order = await client.call_tool(
                "raise_replenishment_order",
                {"store_id": "47", "sku": "8847291", "quantity": 24},
            )
            status = await client.call_tool(
                "get_replenishment_order_status",
                {"store_id": "47", "order_id": order.data["order_id"]},
            )

        assert inventory.data["on_hand_units"] == 4
        assert pos.data["total_units_sold"] == 17
        assert order.data["status"] == "submitted"
        assert status.data == order.data

    asyncio.run(run())


def test_mcp_server_rejects_store_without_credentials(tmp_path) -> None:
    async def run() -> None:
        server = create_server(
            MockStoreLinkClient(),
            credential_provider=FileStoreCredentialProvider(
                write_credentials(tmp_path / "credentials.json")
            ),
            log_dir=tmp_path,
        )

        async with Client(server) as client:
            result = await client.call_tool(
                "get_current_on_hand",
                {"store_id": "102", "sku": "8847291"},
            )

        assert result.data == {
            "error": {
                "code": "missing_store_credentials",
                "message": "No StoreLink credentials are configured for store 102.",
                "store_id": "102",
                "retryable": False,
            }
        }

    asyncio.run(run())

    audit_records = [
        json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()
    ]
    assert audit_records[0]["action"] == "storelink_credentials_rejected"
    assert audit_records[0]["store_id"] == "102"
    assert audit_records[0]["error_code"] == "missing_store_credentials"


def test_mcp_server_audits_credentials_due_to_rotate(tmp_path) -> None:
    async def run() -> None:
        credentials_path = write_credentials(
            tmp_path / "credentials.json",
            expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        )
        server = create_server(
            MockStoreLinkClient(),
            credential_provider=FileStoreCredentialProvider(credentials_path),
            log_dir=tmp_path,
        )

        async with Client(server) as client:
            await client.call_tool(
                "get_current_on_hand",
                {"store_id": "47", "sku": "8847291"},
            )

    asyncio.run(run())

    audit_records = [
        json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()
    ]
    assert audit_records[0]["action"] == "storelink_credentials_rotation_due"
    assert audit_records[0]["store_id"] == "47"
    assert audit_records[0]["rotation_status"] == "rotation_due"
    assert audit_records[1]["action"] == "checked_on_hand"


def test_mcp_server_writes_operational_and_audit_logs(tmp_path) -> None:
    async def run() -> None:
        server = create_server(MockStoreLinkClient(), log_dir=tmp_path)

        async with Client(server) as client:
            await client.call_tool(
                "get_current_on_hand",
                {"store_id": "47", "sku": "8847291"},
            )
            await client.call_tool(
                "raise_replenishment_order",
                {"store_id": "47", "sku": "8847291", "quantity": 24},
            )

    asyncio.run(run())

    operational_records = [
        json.loads(line)
        for line in (tmp_path / "operational.jsonl").read_text().splitlines()
    ]
    audit_records = [
        json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()
    ]

    assert [record["tool_name"] for record in operational_records] == [
        "get_current_on_hand",
        "raise_replenishment_order",
    ]
    assert all(record["status"] == "completed" for record in operational_records)
    assert all(record["correlation_id"] for record in operational_records)

    on_hand_audit = audit_records[0]
    order_audit = audit_records[1]

    assert on_hand_audit["action"] == "checked_on_hand"
    assert on_hand_audit["on_hand_units"] == 4
    assert on_hand_audit["correlation_id"] == operational_records[0]["correlation_id"]

    assert order_audit["action"] == "raised_replenishment_order"
    assert order_audit["order_id"] == "rep-47-1001"
    assert order_audit["correlation_id"] == operational_records[1]["correlation_id"]


def write_credentials(path, expires_at: str = "2030-01-01T00:00:00Z"):
    path.write_text(
        json.dumps(
            {
                "stores": {
                    "47": {
                        "api_key": "mock-storelink-key-store-47",
                        "version": "test-2026-06-24",
                        "expires_at": expires_at,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path
