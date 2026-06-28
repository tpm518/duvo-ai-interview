from __future__ import annotations

import json
import os
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastmcp.server.middleware import Middleware, MiddlewareContext


_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
_OBSERVABILITY_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "duvo_observability_context",
    default=None,
)


class FileObservability:
    def __init__(self, log_dir: str | Path | None = None) -> None:
        self.log_dir = Path(log_dir or os.environ.get("DUVO_LOG_DIR", _DEFAULT_LOG_DIR))
        self.operational_log_path = self.log_dir / "operational.jsonl"
        self.audit_log_path = self.log_dir / "audit.jsonl"

    def write_operational(self, record: dict[str, Any]) -> None:
        self._write_jsonl(self.operational_log_path, record)

    def write_audit(self, record: dict[str, Any]) -> None:
        self._write_jsonl(self.audit_log_path, record)

    def _write_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, sort_keys=True) + "\n")


class ObservabilityMiddleware(Middleware):
    def __init__(self, observability: FileObservability) -> None:
        self.observability = observability

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        started_at = time.perf_counter()
        tool_name = context.message.name
        arguments = context.message.arguments or {}
        mcp_request_id = _mcp_request_id(context)
        correlation_id = mcp_request_id or uuid4().hex

        token = _OBSERVABILITY_CONTEXT.set(
            {
                "correlation_id": correlation_id,
                "mcp_request_id": mcp_request_id,
                "observability": self.observability,
                "tool_name": tool_name,
            }
        )

        try:
            result = await call_next(context)
        except Exception as exc:
            self._write_tool_record(
                arguments=arguments,
                correlation_id=correlation_id,
                duration_ms=_duration_ms(started_at),
                error_type=type(exc).__name__,
                mcp_request_id=mcp_request_id,
                status="failed",
                tool_name=tool_name,
            )
            raise
        finally:
            _OBSERVABILITY_CONTEXT.reset(token)

        status = "error" if result.is_error else "completed"
        self._write_tool_record(
            arguments=arguments,
            correlation_id=correlation_id,
            duration_ms=_duration_ms(started_at),
            error_type=None,
            mcp_request_id=mcp_request_id,
            status=status,
            tool_name=tool_name,
        )
        return result

    def _write_tool_record(
        self,
        *,
        arguments: dict[str, Any],
        correlation_id: str,
        duration_ms: float,
        error_type: str | None,
        mcp_request_id: str | None,
        status: str,
        tool_name: str,
    ) -> None:
        record = {
            "timestamp": _now(),
            "correlation_id": correlation_id,
            "mcp_request_id": mcp_request_id,
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "argument_keys": sorted(arguments),
            **_business_fields(arguments),
        }
        if error_type is not None:
            record["error_type"] = error_type

        self.observability.write_operational(record)


def audit_event(action: str, message: str, **fields: Any) -> None:
    context = _OBSERVABILITY_CONTEXT.get()
    if context is None:
        raise RuntimeError("audit_event must be called during an observed MCP tool call")

    record = {
        "timestamp": _now(),
        "correlation_id": context["correlation_id"],
        "mcp_request_id": context["mcp_request_id"],
        "tool_name": context["tool_name"],
        "action": action,
        "message": message,
        **fields,
    }
    context["observability"].write_audit(record)


def _mcp_request_id(context: MiddlewareContext) -> str | None:
    if context.fastmcp_context is None:
        return None

    if context.fastmcp_context.request_context is None:
        return None

    return context.fastmcp_context.request_id


def _business_fields(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        key: arguments[key]
        for key in ("store_id", "sku", "order_id", "quantity", "since")
        if key in arguments
    }


def _duration_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _now() -> str:
    return datetime.now(UTC).isoformat()
