# Generic Event Daemon

Event Daemon is a provider-neutral, durable event ingress and delivery queue.
It runs independently from AI, Session, Gateway, and Channel so those
components may stop or restart without losing events already accepted by the
daemon.

Provider SDKs, proprietary WebSocket protocols, signature verification, and
provider-specific enrichment are intentionally outside this component. Such
adapters submit normalized events through the same HTTP contract as any other
caller.

The standalone Feishu approval adapter is documented in
[`eventd-feishu.md`](eventd-feishu.md).

## Processes

Run the daemon as an independent OS service:

```powershell
$env:PSI_EVENTD_TOKEN = "local-api-token"
$env:ORDERS_HOOK_TOKEN = "long-random-capability"
psi-agent eventd --config docs/eventd.example.yml
```

Run the consumer with Session:

```powershell
psi-agent event-consumer --config docs/eventd.example.yml
```

The default database is `{AppData}/eventd/events.sqlite3`, resolved through
`PSI_APPDATA` and `platformdirs`. Tests must pass an AppData or database path
inside their temporary workspace.

## Canonical ingress

`POST /v1/events` accepts a strict five-field CloudEvent:

```json
{
  "specversion": "1.0",
  "id": "event-123",
  "source": "shop://orders",
  "type": "order.paid",
  "data": {"order_id": "1001"}
}
```

The top level contains exactly `specversion`, `id`, `source`, `type`, and
`data`. A successful `202` means the SQLite transaction committed. Identity is
`(source, id)`: an identical retry returns `202` with `status=duplicate`, while
different content for the same identity returns `409`.

When `PSI_EVENTD_TOKEN` or `daemon.apiTokenRef` is configured, callers use
`Authorization: Bearer ...`. A non-loopback TCP listener is rejected without
that token.

## URL-only JSON hooks

`POST /hooks/{hook_id}/{token}` accepts arbitrary JSON and wraps it as a
CloudEvent using the hook's configured `source` and `type`. The original JSON
becomes `data`.

An event ID may be read from one request header:

```yaml
idFrom:
  header: X-Event-Id
```

or from one JSON Pointer:

```yaml
idFrom:
  pointer: /event/id
```

When neither yields a value, the daemon generates a UUID. That convenience
mode cannot deduplicate sender retries. Reliable senders should provide a
stable ID and reuse both ID and body for every retry.

Hook tokens are capability secrets. Only `env://` references are accepted.
Use long, independently revocable values and configure access logs not to
record hook paths. Unknown hooks and incorrect tokens both return `404`.

## Durable delivery

Subscriptions filter on `sourcePrefix` and exact `types`. Each accepted event
creates at most one delivery per matching subscription.

The consumer protocol is:

- `POST /internal/v1/subscriptions/{id}/claim`
- `POST /internal/v1/deliveries/{id}/renew`
- `POST /internal/v1/deliveries/{id}/ack`
- `POST /internal/v1/deliveries/{id}/nack`

Delivery is at least once. Claim creates a random lease token. Renew, ACK, and
NACK require `deliveryId + leaseToken + an unexpired lease`; a previous
consumer cannot control a replacement lease. Expired leases become claimable
again, and deliveries become `DEAD` after `maxAttempts`.

The generic consumer translates an event to Session without changing its
business type:

```json
{
  "source": "eventd",
  "event": "order.paid",
  "payload": {"order_id": "1001"},
  "idempotency_key": "shop://orders|event-123",
  "routing": {
    "delivery_id": "delivery_...",
    "event_source": "shop://orders",
    "event_id": "event-123"
  }
}
```

Non-object `data` is wrapped as `{"value": data}` because the existing Session
event protocol requires an object payload.

The consumer ACKs only when Session reports at least one successful matching
Trigger and no failures, or when Session recognizes an already completed
event. Missing Triggers and execution failures are NACKed.

## Guarantees and limits

- SQLite uses WAL, `synchronous=FULL`, foreign keys, and a busy timeout.
- Inbox identity is `UNIQUE(source, event_id)`.
- Delivery survives ordinary daemon and consumer restarts.
- External side effects are not transactionally coupled to the local ACK.
  Mutating tools must use the delivery or CloudEvent identity as their
  idempotency key.
- This release is single-machine. PostgreSQL, multi-node coordination,
  provider adapters, provider-specific signed webhooks, DLQ replay APIs, and
  full metrics export are separate work.
