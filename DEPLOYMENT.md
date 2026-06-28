# Korral Deployment

## Recommendation

Your direction is correct: this should run in Korral's GCP environment, not in Duvo-hosted infrastructure. The runtime needs private network access to StoreLink, and the task explicitly says customer data must not leave Korral's GCP tenancy.

The initial deployment target should be a Korral-managed GCE VM or GKE workload because the current MCP server uses stdio and is meant to be spawned by an MCP client or supervisor. If Korral wants a network service later, we can add Streamable HTTP MCP and deploy that behind private GCP networking on GKE or Cloud Run.

For CI/CD, avoid storing long-lived GCP service account keys in Duvo systems. Prefer a Korral-granted, short-lived deployment identity such as Workload Identity Federation, scoped to push this image and update this runtime only.

## Runnable Artifact

Build the image:

```bash
docker build -t korral-storelink-mcp:local .
```

Run it locally over stdio with the mock one-store credentials file mounted read-only:

```bash
docker run --rm -i \
  -e STORELINK_CREDENTIALS_PATH=/run/secrets/storelink_credentials.json \
  -v "$PWD/config/storelink_credentials.json:/run/secrets/storelink_credentials.json:ro" \
  korral-storelink-mcp:local
```

In normal MCP usage, Codex or Claude Code should spawn that `docker run -i ...` command. Do not run the container interactively in a terminal and then point the client at it; stdio MCP expects the client to own the process stdin/stdout.

Example Codex MCP config for the containerized server:

```toml
[mcp_servers.korral_storelink]
command = "docker"
args = [
  "run",
  "--rm",
  "-i",
  "-e",
  "STORELINK_CREDENTIALS_PATH=/run/secrets/storelink_credentials.json",
  "-v",
  "/Users/tommurray/Documents/projects/duvo/config/storelink_credentials.json:/run/secrets/storelink_credentials.json:ro",
  "korral-storelink-mcp:local",
]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

## Where This Runs

Run the container in Korral's GCP project, attached to the VPC or subnet path that can reach StoreLink. The runtime should have no public ingress requirement for the current stdio transport.

The runtime needs:

- Private network route to StoreLink.
- Read access to StoreLink per-store credentials.
- Write access to local or customer-approved logs.
- No outbound path that sends customer data to Duvo-controlled infrastructure.

## How It Gets There

The deployable unit is a Docker image. The expected path is:

1. Duvo builds and tests the image from this repository.
2. CI publishes the image to a Korral-approved Artifact Registry repository.
3. A deployment job updates the Korral runtime to the approved image digest.
4. Korral IT can approve or block production rollout, depending on their change-control requirements.

Use immutable image digests for deployment, not floating tags like `latest`.

## Secrets

StoreLink keys should not be baked into the image. Mount them at runtime as a file and point the server at that file with:

```bash
STORELINK_CREDENTIALS_PATH=/run/secrets/storelink_credentials.json
```

For the current implementation, the file shape is:

```json
{
  "stores": {
    "47": {
      "api_key": "storelink-key",
      "version": "2026-06-24",
      "expires_at": "2026-07-01T00:00:00Z"
    }
  }
}
```

Korral should own the actual StoreLink keys. Duvo's CI/CD should not store long-lived customer service account keys. Prefer short-lived deployment identity such as Workload Identity Federation, scoped to push images and update only this service.

## Pipeline Ownership

Duvo should create and maintain the pipeline because Duvo owns the MCP server code and release process. Korral should own the GCP project, network, secrets, and final production approval policy.

Practical ownership split:

- Duvo owns code, tests, Dockerfile, image build, release notes, and rollback instructions.
- Korral owns GCP project permissions, StoreLink network access, secret rotation, and production approval gates.
- Deployment identity is granted by Korral and scoped narrowly to this artifact and runtime.

## 11pm Fix Path

When something breaks:

1. Use `logs/operational.jsonl` to find failing tool calls by correlation ID, tool name, store ID, SKU, status, duration, and error type.
2. Use `logs/audit.jsonl` to explain what the agent did in buyer-readable language.
3. Convert the issue into a failing unit test or eval.
4. Fix the bug.
5. Run regression tests.
6. Build a new image and deploy by immutable digest.
7. Use a Korral-approved rollout gate if required for production changes.
8. Keep the previous image digest available for rollback.

## Confirm With Korral IT Before Day 1

- Which GCP runtime they prefer: GCE VM, GKE, Cloud Run, or another managed environment.
- Whether the MCP client runs inside Korral's environment, and whether stdio is acceptable or they require Streamable HTTP.
- Exact network path from the runtime to StoreLink: DNS, ports, firewall rules, TLS, proxies, and allowed egress.
- How StoreLink keys are delivered and rotated: Secret Manager, mounted file, Config Connector, or another internal mechanism.
- Whether Duvo CI can push directly to Korral Artifact Registry, or whether Korral mirrors/promotes images from a Duvo registry.
- Required approval gates, maintenance windows, and emergency-change process.
- Log retention, access control, redaction rules, and whether logs must be shipped to Korral's SIEM.
- How to validate that no customer data leaves Korral's GCP tenancy.

## References

- Google Cloud Artifact Registry Docker images: https://cloud.google.com/artifact-registry/docs/docker
- Google Cloud Workload Identity Federation: https://cloud.google.com/iam/docs/workload-identity-federation
- Google Cloud Run Direct VPC networking: https://cloud.google.com/run/docs/configuring/vpc-direct-vpc
