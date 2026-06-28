# StoreLink Store-Key Verification Gap

## Current state

The MCP server currently checks whether a requested `store_id` exists in the local credentials file before it calls StoreLink.

That prevents the agent from accessing stores we have no configured credentials for. For example, if the credentials file only contains store `47`, a request for store `102` returns `missing_store_credentials`.

## Gap

We are not yet verifying that the configured API key actually belongs to the requested store.

Today, if the credentials file maps store `47` to a key that actually belongs to store `102`, the mock StoreLink client would still allow the store `47` request because it never receives or validates the API key.

This means the current implementation proves that a credential exists for the store ID, but not that the credential is valid for that store.

## Desired behavior

Every store-scoped StoreLink call should pass the resolved key into the StoreLink client boundary:

```python
credential = credentials.get_credential(store_id)
storelink.get_current_on_hand(store_id, sku, api_key=credential.api_key)
```

The mock StoreLink client should simulate StoreLink auth enforcement by checking the provided key against the expected key for that exact store.

If the key is missing, expired, invalid, or belongs to another store, the request should fail safely before returning StoreLink data.

## Real StoreLink behavior

With the real HTTP client, this check happens at StoreLink:

```http
GET /v1/stores/47/inventory?sku=8847291
X-Korral-Store-Key: <key>
```

If `<key>` is scoped to a different store, StoreLink should return `401` or `403`. The MCP server should translate that into a structured, non-secret-leaking error for the agent and operational logs.

## Follow-up implementation

- Add `api_key` parameters to store-scoped methods on `MockStoreLinkClient`.
- Add mock expected keys per store inside the mock StoreLink data.
- Raise a StoreLink auth error when the provided key does not match the requested store.
- Update MCP tools to call `credentials.get_credential(store_id)` and pass `credential.api_key` into the StoreLink client.
- Keep `list_stores` filtered to credentialed stores.
- Do not expose raw API keys in tool results, audit logs, operational logs, or test assertions.

## Follow-up tests

- Store `47` with the store `47` key succeeds.
- Store `47` with a store `102` key fails.
- Store `102` with no configured credential returns `missing_store_credentials`.
- StoreLink auth failures produce a structured error and an operational/audit record without logging the key.
