# Event Daemon

Event Daemon keeps provider connections and durable event state independent of
AI, Session, Gateway, and Channel lifetimes. The first implementation supports
Feishu approval events over WebSocket and a strict five-field CloudEvent.

## Processes

Run Event Daemon as its own OS service:

```powershell
$env:PSI_FEISHU_APP_SECRET = "..."
$env:PSI_EVENTD_TOKEN = "..."
psi-agent eventd --config docs/eventd.example.yml
```

Run the consumer with Haitun/Session. It may stop and restart without stopping
the daemon:

```powershell
psi-agent event-consumer --config docs/eventd.example.yml
```

When the normal Feishu Channel and Event Daemon use the same app, start the
Channel with `--no-respond-to-approvals`. Otherwise the legacy in-Channel
approval DM handler and the durable pipeline both process the same event.

The default database is `{AppData}/eventd/events.sqlite3`, resolved through
`PSI_APPDATA` and `platformdirs`. Set `PSI_APPDATA` to a directory inside a test
workspace when the test must not write elsewhere.

## Guarantees

- Raw Feishu notifications commit to SQLite before the SDK callback returns.
- Detail enrichment runs after raw persistence and retries from disk.
- A normalization interrupted by daemon termination is reclaimed after its
  stale timeout instead of remaining permanently in `NORMALIZING`.
- Inbox identity is `UNIQUE(source, event_id)`; different content conflicts.
- Delivery is at least once through `claim`, `renew`, `ack`, and `nack` leases.
- Expired leases become claimable; poison deliveries become `DEAD` after the
  subscription's maximum attempts.
- Lease control is conditional on `deliveryId + leaseToken + unexpired lease`;
  an old consumer cannot ACK, NACK, or renew a replacement lease.
- Startup and periodic reconciliation query a persisted overlapping time
  window and use the same deterministic approval-transition identity as live
  WebSocket delivery.
- Feishu connection failures are isolated per connection and supervised with
  exponential backoff plus jitter; the eventd HTTP service stays available.
- Consumer ACKs only a successful Session Trigger result or a recognized
  duplicate. Missing triggers and failed tools are NACKed.
- Completed trigger keys are persisted per Session in AppData, so an ordinary
  Session restart does not erase the consumer's deduplication ledger. The
  `delivery_id`, CloudEvent source, and CloudEvent ID are also included in the
  Session envelope's `routing` object.

The consumer translates `approval.status.changed` into the existing
`feishu.approval.status.changed` Session envelope. The agent package declares
that name with `channel_events/feishu/approval_status_changed/EVENT.yaml` using
`kind: durable`.

## HTTP surface

- `POST /v1/events`: accept a strict five-field CloudEvent.
- `POST /internal/v1/subscriptions/{id}/claim`: long-poll deliveries.
- `POST /internal/v1/deliveries/{id}/renew|ack|nack`: lease control.
- `GET /livez`, `/readyz`, `/health/ingress`: health and backlog state.

Set `PSI_EVENTD_TOKEN` (or use an `env://` `apiTokenRef`); callers then use
`Authorization: Bearer ...`. Literal API tokens in YAML are rejected, and a
non-loopback TCP listener is rejected when no token is configured. Keep the
listener on loopback or an OS-local transport. The provider webhook route is
reserved and returns 501 until a provider-specific verifier/decrypter is
configured; unsigned generic webhook acceptance is intentionally forbidden.

## Remaining production stages

The SQLite single-machine implementation is the usable MVP. PostgreSQL,
multi-host WebSocket leader election, provider-specific signed webhooks,
operator DLQ replay APIs, mTLS, and full metrics export remain production-stage
work. A Windows installer must register Event Daemon separately and preserve
AppData on agent upgrades or uninstall.

The persistent Session ledger narrows the common "tool completed, ACK response
lost" duplicate window, but it cannot make an arbitrary external side effect
and the local ledger write one atomic transaction. Tools that mutate external
systems must use `routing.delivery_id` (or `source + id`) as that system's
idempotency key when strict duplicate suppression is required.
