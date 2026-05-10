# Billing

Cognix includes Stripe-based subscription billing with usage tracking.

## Plans

| Plan | Price | Agents | API Calls/mo | Tokens/mo |
|------|-------|--------|--------------|-----------|
| Free | $0 | 1 | 100 | 10,000 |
| Starter | $29/mo | 5 | 5,000 | 500,000 |
| Pro | $99/mo | 25 | 50,000 | 5,000,000 |
| Enterprise | Custom | Unlimited | Unlimited | Unlimited |

## API Endpoints

### List Plans

```bash
curl http://localhost:8000/billing/plans
```

### Get Current Subscription

```bash
curl http://localhost:8000/billing/subscription \
  -H "Authorization: Bearer TOKEN"
```

### Create Checkout Session

```bash
curl -X POST http://localhost:8000/billing/checkout \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "starter"}'
```

Returns a Stripe Checkout URL to redirect the user to.

### Customer Portal

```bash
curl -X POST http://localhost:8000/billing/portal \
  -H "Authorization: Bearer TOKEN"
```

Returns a Stripe Customer Portal URL for managing subscriptions.

### Usage Stats

```bash
curl http://localhost:8000/billing/usage \
  -H "Authorization: Bearer TOKEN"
```

Response:

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

## Stripe Webhook

Configure your Stripe webhook endpoint to point to:

```
https://your-domain.com/billing/webhook
```

Events handled:

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Activate subscription |
| `invoice.paid` | Extend subscription period |
| `invoice.payment_failed` | Mark as past due |
| `customer.subscription.deleted` | Cancel subscription |
| `customer.subscription.updated` | Update subscription status |

## Configuration

Set these environment variables:

```bash
COGNIX_BILLING__STRIPE_SECRET_KEY=sk_...
COGNIX_BILLING__STRIPE_WEBHOOK_SECRET=whsec_...
COGNIX_BILLING__STRIPE_PRICE_STARTER=price_...
COGNIX_BILLING__STRIPE_PRICE_PRO=price_...
```
