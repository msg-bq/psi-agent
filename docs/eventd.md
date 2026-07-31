# Generic Event Daemon

Event Daemon is a provider-neutral, durable event ingress and delivery queue.
It runs independently from AI, Session, Gateway, and Channel so those
components may stop or restart without losing events already accepted by the
daemon.

Provider SDKs, proprietary WebSocket protocols, signature verification, and
provider-specific enrichment are intentionally outside this component. Such
adapters submit normalized events through the same HTTP contract as any other
caller.

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

The response reports how many configured subscriptions matched:

```json
{"status": "created", "eventSeq": 42, "matchedSubscriptions": 1}
```

Zero matches still returns `202` because the Inbox accepted the event, but the
daemon logs a warning. An adapter that requires downstream processing should
publish with `EventdClient.publish(..., require_match=True)` and treat zero as
a configuration error.

When `PSI_EVENTD_TOKEN` or `daemon.apiTokenRef` is configured, callers use
`Authorization: Bearer ...`. A non-loopback TCP listener is rejected without
that token.

The running HTTP contract is available as OpenAPI 3.1 at
`GET /openapi.json`.

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

Hook tokens are capability secrets and only `env://` references are accepted.
Generated `webhookListeners` additionally require RFC 3986 unreserved
characters (`A-Z`, `a-z`, `0-9`, `-._~`), so use base64url or another URL-safe
generator rather than standard base64. Use long, independently revocable
values and configure access logs not to record hook paths. Unknown hooks and
incorrect tokens both return `404`.

### FusionFlow Webhook listeners

An event-enabled FusionFlow does not declare a business event catalog, payload
schema, public URL, or secret. It declares one lowercase logical Path such as
`expense_hook`. Provision the same identity with the `webhookListeners`
shorthand:

```yaml
webhookListeners:
  - id: expense_hook
    tokenRef: env://EXPENSE_HOOK_TOKEN
    idFrom:
      header: Idempotency-Key
```

This expands to exactly one Hook and one same-ID Subscription. The generated
transport contract is fixed:

- external URL:
  `{publicBaseUrl}/hooks/{listener_id}/{resolved_token}`;
- CloudEvent `source`: `webhook://eventd/{listener_id}/`;
- CloudEvent `type`: `external.event.received`;
- CloudEvent `data`: the complete incoming JSON value;
- Subscription filter: that listener's generated source, with no `type`
  filter.

`publicBaseUrl` is the operator-owned public origin or reverse-proxy origin; it
cannot be inferred safely from `daemon.listen`. The resolved token is supplied
out of band to the sender and must never be written to G4 or committed config.
This provisions a transport listener, not a set of domain events. Every JSON
body is accepted without declaring an event name or message schema.
If `webhookListeners` and manual `hooks` are mixed, declare manual
`subscriptions` explicitly; EventD refuses to synthesize one broad `default`
subscription that would also capture listener traffic.

The matching G4 executor is declared as
`Program, EventListeningProgram, Executor`, and
`program_path(listener) == expense_hook`. The EventD consumer posts the
delivery to Session with `routing.subscription_id=expense_hook`; a
`fire=tool` Trigger selects that listener with
`routing_filter.subscription_id`, then calls `run_flow_event` with that full
event context. For example:

```yaml
---
name: expense-hook
source: eventd
event: external.event.received
routing_filter:
  subscription_id: expense_hook
fire: tool
tool: run_flow_event
tool_args:
  flow_path: flows/workflows/expense/expense.workflow
event_context_arg: event_context_json
visibility: silent
---
```

Create this record through `trigger_manage` rather than editing
`TRIGGER.md` directly; the YAML above shows the persisted contract.
Session binds a private call context around that `fire=tool` invocation, so a
normal Agent tool call cannot fabricate an EventD activation. The tool injects
the strict five-field CloudEvent as the listener Step's sole
Artifact and waits for the rest of the workflow to complete before the
consumer ACKs.

Run the consumer only while its target Session is healthy. If a consumer keeps
claiming while Session is unavailable, repeated delivery failures can consume
`maxAttempts`; EventD itself should remain running so unclaimed events stay
durable until the bridge is healthy.

## Durable delivery

Subscriptions filter on `sourcePrefix` and exact `types`. Each accepted event
creates at most one delivery per matching subscription.

The consumer protocol is:

- `GET /internal/v1/subscriptions/{id}`
- `POST /internal/v1/subscriptions/{id}/claim`
- `POST /internal/v1/deliveries/{id}/renew`
- `POST /internal/v1/deliveries/{id}/ack`
- `POST /internal/v1/deliveries/{id}/nack`

The read-only subscription endpoint exposes the active filter, lease duration,
and maximum attempts. Adapter workers validate the subscription before their
claim loop, so a misspelled or removed ID fails with `404` instead of polling
an empty queue forever. Claiming with `leaseSeconds=0` or omitting the field
uses the subscription's configured lease.

Delivery is at least once. Claim creates a random lease token. Renew, ACK, and
NACK require `deliveryId + leaseToken + an unexpired lease`; a previous
consumer cannot control a replacement lease. Expired leases become claimable
again, and deliveries become `DEAD` after `maxAttempts`.

## Reusable adapter runtime

Provider adapters use the shared HTTP and lease runtime instead of
reimplementing queue plumbing:

```python
async with EventdClient(endpoint, token) as client:
    await client.publish(event, require_match=True)
    worker = LeaseWorker(
        client=client,
        subscription_id="provider-normalizer",
        handler=normalize_delivery,
    )
    await worker.run()
```

`EventdClient` provides publish, subscription lookup, claim, renew, ACK, and
NACK. `LeaseWorker` validates the subscription, claims one delivery at a time,
long-polls, renews the lease through completion of ACK/NACK, and retries
transport errors, `429`, `5xx`, and stale delivery leases. It refreshes a
subscription-provided lease default before every claim so daemon configuration
changes cannot silently shorten an active worker's renewal window.
Authentication errors, unknown subscriptions, and invalid response contracts
fail immediately.

Provider config parsers may reuse `mapping`, `string_list`, `positive_int`,
`non_negative_int`, `secret_from_env_ref`, and `read_yaml` from
`psi_agent.eventd.config`.

The generic consumer translates an event to Session without changing its
business type:

```json
{
  "source": "eventd",
  "event": "order.paid",
  "payload": {"order_id": "1001"},
  "idempotency_key": "cloudevent/sha256:<source-and-id-hash>",
  "routing": {
    "delivery_id": "delivery_...",
    "event_source": "shop://orders",
    "event_id": "event-123"
  },
  "cloud_event": {
    "specversion": "1.0",
    "id": "event-123",
    "source": "shop://orders",
    "type": "order.paid",
    "data": {"order_id": "1001"}
  }
}
```

Non-object `data` is wrapped as `{"value": data}` because the existing Session
event protocol requires an object `payload`. The optional `cloud_event` field
preserves the exact five-field event, so scalar, list, object, and `null`
`data` remain distinguishable. `idempotency_key` is a deterministic,
collision-resistant hash of the CloudEvent `(source, id)` identity.

Every `fire=prompt` Trigger receives its static `TRIGGER.md` body followed by a
delimited full event-context JSON block. The block is explicitly marked as
untrusted data, and delimiter characters inside JSON strings are escaped. That
protects the envelope boundary; it does not make semantic prompt injection
impossible. Prompt handlers must treat all event fields as attacker-controlled
and should delegate irreversible side effects to validating tools.

`fire=tool` remains backward compatible: existing static `tool_args` are
unchanged. A Trigger can opt into the current event through one dynamic string
argument:

```yaml
---
name: handle-paid-order
source: eventd
event: order.paid
routing_filter:
  subscription_id: order_hook
fire: tool
tool: handle_paid_order
tool_args:
  queue: finance
event_context_arg: event_json
---
```

At dispatch, `event_json` receives deterministic JSON for the complete Session
event envelope, including `cloud_event`, `routing`, and `idempotency_key`.
`routing_filter` is an exact-subset match against the envelope's routing
object; generated Webhook listeners must use it to prevent one listener's
delivery from firing another listener's workflow.
The configured name must be a valid Python parameter, the tool must declare
it, and it must not also appear in static `tool_args`. Dynamic event JSON is
passed directly to the tool and masked from logs and persisted conversation
history; the tool remains responsible for schema and authorization checks.

The consumer ACKs only when Session reports at least one successful matching
Trigger and no failures, or when Session recognizes an already completed
event. Missing Triggers and raised execution failures are NACKed. Existing
Program semantics still treat a captured launch, exit, or output-format
failure as a completed `$fusion_flow/program_error` Artifact, so that value is
ACKed unless a downstream Step deliberately raises.

## Guarantees and limits

- SQLite uses WAL, `synchronous=FULL`, foreign keys, and a busy timeout.
- Inbox identity is `UNIQUE(source, event_id)`.
- Session dispatch idempotency for EventD is scoped by
  `(CloudEvent identity, subscription_id)`, so one event may legitimately run
  once for each matching durable subscription.
- Delivery survives ordinary daemon and consumer restarts.
- External side effects are not transactionally coupled to the local ACK.
  Mutating tools must use the delivery or CloudEvent identity as their
  idempotency key.
- Event workflow JobStore records and materialized Artifact files currently
  have no automatic retention policy. Operators must budget disk and must not
  delete them casually: deterministic completed-run reuse is part of
  idempotency.
- A failed event run is bound to the workflow definition digest with which it
  started. Editing that workflow does not silently resume the old delivery
  under new semantics; replay/version migration tooling is not included.
- This release is single-machine. PostgreSQL, multi-node coordination,
  provider adapters, provider-specific signed webhooks, DLQ replay APIs,
  retention/GC, workflow-version migration, and full metrics export are
  separate work.
