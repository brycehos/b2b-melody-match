"""
Webhook handlers for Clerk (user lifecycle) and Stripe (subscription lifecycle).
"""

import asyncio
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from svix.webhooks import Webhook as SvixWebhook, WebhookVerificationError

import database
import stripe_client

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# ── Clerk webhook ────────────────────────────────────────────────────────────

@router.post("/clerk")
async def clerk_webhook(request: Request):
    """
    Syncs Clerk user creation/deletion to Supabase.

    In Clerk dashboard: Webhooks → Add Endpoint
      URL: https://your-backend.railway.app/api/webhooks/clerk
      Events: user.created, user.deleted
    Copy the signing secret → CLERK_WEBHOOK_SECRET in .env
    """
    secret = os.getenv("CLERK_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=500, detail="Clerk webhook secret not configured")

    payload = await request.body()
    headers = dict(request.headers)

    try:
        wh = SvixWebhook(secret)
        event = wh.verify(payload, headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Clerk webhook signature")

    event_type = event.get("type")
    data = event.get("data", {})

    if event_type == "user.created":
        clerk_user_id = data.get("id")
        emails = data.get("email_addresses", [])
        email = emails[0].get("email_address") if emails else None
        if clerk_user_id:
            await asyncio.get_event_loop().run_in_executor(
                None, database.get_or_create_user, clerk_user_id, email
            )

    elif event_type == "user.deleted":
        # We leave DB rows in place for audit purposes.
        pass

    return {"status": "ok"}


# ── Stripe webhook ────────────────────────────────────────────────────────────

@router.post("/stripe")
async def stripe_webhook(request: Request):
    """
    Keeps Supabase subscription state in sync with Stripe.

    In Stripe dashboard: Developers → Webhooks → Add endpoint
      URL: https://your-backend.railway.app/api/webhooks/stripe
      Events: checkout.session.completed
              customer.subscription.updated
              customer.subscription.deleted
    Copy the signing secret → STRIPE_WEBHOOK_SECRET in .env
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_client.construct_webhook_event(payload, sig_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stripe webhook error: {e}")

    loop = asyncio.get_event_loop()

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        plan = session.get("metadata", {}).get("plan", "explorer")

        user = await loop.run_in_executor(
            None, database.get_user_by_stripe_customer, customer_id
        )
        if user:
            await loop.run_in_executor(None, database.update_plan, user["clerk_user_id"], plan)

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        status = sub.get("status")  # active, canceled, past_due, trialing
        price_id = sub["items"]["data"][0]["price"]["id"] if sub.get("items", {}).get("data") else ""
        plan = stripe_client.price_to_plan(price_id) if price_id else "free"
        period_end_ts = sub.get("current_period_end")
        period_end = (
            datetime.fromtimestamp(period_end_ts, tz=timezone.utc).isoformat()
            if period_end_ts else None
        )

        user = await loop.run_in_executor(
            None, database.get_user_by_stripe_customer, customer_id
        )
        if user:
            effective_plan = plan if status == "active" else "free"
            await loop.run_in_executor(
                None, database.update_plan, user["clerk_user_id"], effective_plan
            )
            await loop.run_in_executor(
                None,
                database.upsert_subscription,
                user["id"],
                sub["id"],
                price_id,
                plan,
                status,
                period_end,
            )

    return {"status": "ok"}
