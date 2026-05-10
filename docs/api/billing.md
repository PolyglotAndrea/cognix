# Billing API

## Endpoints

### List Plans

```
GET /billing/plans
```

**Response (200):**

```json
[
  {
    "id": "free",
    "name": "Free",
    "price_monthly": 0,
    "features": {"agents": 1, "api_calls": 100, "tokens": 10000}
  },
  {
    "id": "starter",
    "name": "Starter",
    "price_monthly": 29,
    "features": {"agents": 5, "api_calls": 5000, "tokens": 500000}
  }
]
```

---

### Get Subscription

```
GET /billing/subscription
```

**Response (200):**

```json
{
  "id": "sub123",
  "plan_id": "starter",
  "status": "active",
  "current_period_start": "2026-01-01T00:00:00Z",
  "current_period_end": "2026-02-01T00:00:00Z"
}
```

---

### Create Checkout Session

```
POST /billing/checkout
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `plan_id` | string | ✅ | Plan to subscribe to |

**Response (200):**

```json
{
  "checkout_url": "https://checkout.stripe.com/..."
}
```

---

### Customer Portal

```
POST /billing/portal
```

**Response (200):**

```json
{
  "portal_url": "https://billing.stripe.com/..."
}
```

---

### Usage Stats

```
GET /billing/usage
```

**Response (200):**

```json
{
  "plan_id": "starter",
  "usage": {
    "api_calls": {"used": 150, "limit": 5000},
    "tokens": {"used": 45000, "limit": 500000},
    "agent_runs": {"used": 50, "limit": 1000}
  }
}
```

---

### Stripe Webhook

```
POST /billing/webhook
```

Handles Stripe webhook events. See [Billing Guide](../guides/billing.md) for supported events.
