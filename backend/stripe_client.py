"""
Stripe integration for MelodyMatch subscriptions.

Setup checklist (do this in the Stripe dashboard before deploying):
1. Create two Products under Products → Add product:
   - "MelodyMatch Explorer"  → recurring price $4.99/month → copy price_xxx ID
   - "MelodyMatch Unlimited" → recurring price $9.99/month → copy price_xxx ID
2. Add the price IDs to backend/.env as STRIPE_EXPLORER_PRICE_ID and STRIPE_UNLIMITED_PRICE_ID
3. In Webhooks → Add endpoint: https://your-backend.railway.app/api/webhooks/stripe
   Listen for: checkout.session.completed, customer.subscription.updated,
               customer.subscription.deleted
4. Copy the webhook signing secret → STRIPE_WEBHOOK_SECRET
"""

import os
import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

PRICE_IDS: dict[str, str] = {
    "explorer":  os.getenv("STRIPE_EXPLORER_PRICE_ID", ""),
    "unlimited": os.getenv("STRIPE_UNLIMITED_PRICE_ID", ""),
}

PLAN_LABELS: dict[str, str] = {
    "explorer":  "Explorer",
    "unlimited": "Unlimited",
}


def get_or_create_customer(clerk_user_id: str, email: str) -> str:
    """Return existing Stripe customer ID or create a new one."""
    existing = stripe.Customer.search(
        query=f'metadata["clerk_user_id"]:"{clerk_user_id}"'
    )
    if existing.data:
        return existing.data[0].id
    customer = stripe.Customer.create(
        email=email,
        metadata={"clerk_user_id": clerk_user_id},
    )
    return customer.id


def create_checkout_session(
    plan: str,
    stripe_customer_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout Session and return the hosted URL."""
    price_id = PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(f"Unknown plan: {plan}")

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"plan": plan},
        subscription_data={
            "metadata": {"plan": plan},
        },
    )
    return session.url


def create_billing_portal_session(stripe_customer_id: str, return_url: str) -> str:
    """Create a Stripe Customer Portal session and return the URL."""
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    """Verify and construct a Stripe webhook event."""
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def price_to_plan(price_id: str) -> str:
    """Map a Stripe price ID back to a plan name."""
    for plan, pid in PRICE_IDS.items():
        if pid == price_id:
            return plan
    return "free"
