# Feishu Approval Event Adapter

The Feishu approval adapter is a provider-specific process layered on the
generic Event Daemon. Feishu does not expose a reusable WebSocket URL:
`lark-channel-sdk` obtains and authenticates the connection from an app ID and
secret, registers native event processors, and dispatches proprietary payloads.

The adapter is deliberately outside `psi_agent.eventd`. It knows nothing about
Event Daemon SQLite internals and communicates only through the documented
CloudEvent and lease HTTP APIs.

## Required Feishu setup

Create a dedicated Feishu app for the durable approval adapter:

1. Enable long-connection event delivery.
2. Grant the approval permissions needed to subscribe to definitions and read
   instance details.
3. Put each approval definition code in `approvalCodes`.
4. Set the app secret and Event Daemon token through environment variables.

Do not run the normal Feishu Channel and this adapter as separate long
connections using the same app. Feishu distributes events among concurrent
connections rather than broadcasting every event to every connection, so an
approval event may land on the Channel connection instead of the durable
adapter. `channel feishu --no-respond-to-approvals` prevents duplicate legacy
handling but does not change that distribution rule. A dedicated app, or no
simultaneous Channel connection for that app, is required for reliable ingress.

## Configuration and startup

Start from [`eventd-feishu.example.yml`](eventd-feishu.example.yml), then set:

```powershell
$env:PSI_EVENTD_TOKEN = "local-eventd-token"
$env:PSI_FEISHU_APPROVAL_APP_SECRET = "feishu-app-secret"
```

Run the three independent processes:

```powershell
psi-agent eventd --config docs/eventd-feishu.example.yml
psi-agent event-adapter-feishu-approval --config docs/eventd-feishu.example.yml
psi-agent event-consumer --config docs/eventd-feishu.example.yml
```

The adapter confirms the configured approval-definition subscriptions at every
WebSocket start. The Feishu API operation is idempotent.

## Two-stage durability

Feishu expects a long-connection callback to finish in about three seconds.
The adapter therefore does not query instance details in that callback:

```text
Feishu callback
  -> POST raw CloudEvent to Event Daemon
  -> wait for HTTP 202 (SQLite commit)
  -> return from callback

raw subscription
  -> adapter claims with a renewable lease
  -> query Feishu instance details
  -> POST normalized CloudEvent
  -> ACK raw delivery
```

`callbackTimeoutSeconds` defaults to `2.5` and must remain below `3`. A timeout,
network error, or non-202 response raises back into the SDK callback instead of
pretending that the event was stored.

The raw event is:

```json
{
  "specversion": "1.0",
  "id": "provider-event-id",
  "source": "feishu://tenant-a/cli_adapter/approval/raw",
  "type": "feishu.approval.instance.received",
  "data": {
    "header": {},
    "event": {
      "approval_code": "EXPENSE_001",
      "instance_code": "instance-1",
      "status": "APPROVED"
    }
  }
}
```

When Feishu supplies no event ID, the adapter hashes the canonical raw payload.
The normalized event ID is derived from the complete canonical normalized
content, including its source and type:

```json
{
  "specversion": "1.0",
  "id": "sha256-content-id",
  "source": "feishu://tenant-a/cli_adapter/approval",
  "type": "approval.status.changed",
  "data": {
    "approval_code": "EXPENSE_001",
    "instance_code": "instance-1",
    "approval_name": "Expense",
    "status": "APPROVED",
    "instance_operate_time": "1000",
    "applicant": "ou_user",
    "form": [],
    "attachments": [],
    "task_list": [],
    "timeline": []
  }
}
```

Publishing an already stored identical normalized event is success. If a later
detail fetch for the same transition contains changed form, task, timeline, or
other fields, it produces a different ID instead of colliding with the earlier
content and retrying until dead-letter. Future reconciliation must use the same
canonical content identity.

The normalizer does not claim raw deliveries until the Feishu API is ready.
When a claimed delivery overlaps a WebSocket reconnect, it renews the existing
lease while waiting for API readiness instead of NACKing and consuming an
attempt without performing normalization.

## SDK compatibility boundary

`lark-channel-sdk` 1.2.0 has no typed approval processor. The adapter isolates
the required `dispatcher._processorMap` compatibility code in
`event_adapters/feishu/sdk.py` and registers both `p1.approval_instance` and
`p2.approval_instance` after `start_background()`, because startup rebuilds the
dispatcher. An incompatible SDK fails explicitly instead of leaving an
apparently healthy adapter that receives no approvals.

## Scope

This adapter covers WebSocket ingestion, approval-definition subscription,
detail enrichment, reconnect supervision, and durable normalization. Signed
Feishu webhooks and reconciliation scans with durable cursors are separate
work. The generic Event Daemon remains provider-neutral.
