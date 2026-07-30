"""
Supabase database client for user and subscription management.
All public functions are sync; FastAPI runs them in a thread pool via
asyncio.run_in_executor when called from async route handlers.
"""

import os
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        _client = create_client(url, key)
    return _client


# ── Search limits per plan ───────────────────────────────────────────────────

SEARCH_LIMITS: dict[str, int] = {
    "free":      10,
    "explorer":  75,
    "unlimited": 300,
}

PAID_PLANS = {"explorer", "unlimited"}


# ── User helpers ─────────────────────────────────────────────────────────────

def get_user(clerk_user_id: str) -> Optional[dict]:
    db = get_client()
    result = (
        db.table("users")
        .select("*")
        .eq("clerk_user_id", clerk_user_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def create_user(clerk_user_id: str, email: Optional[str] = None) -> dict:
    db = get_client()
    result = (
        db.table("users")
        .insert({"clerk_user_id": clerk_user_id, "email": email, "plan": "free"})
        .execute()
    )
    return result.data[0]


def get_or_create_user(clerk_user_id: str, email: Optional[str] = None) -> dict:
    user = get_user(clerk_user_id)
    if user:
        return user
    return create_user(clerk_user_id, email)


def maybe_reset_monthly_count(user: dict) -> dict:
    """Reset searches_used_this_month if the reset window has passed."""
    now = datetime.now(timezone.utc)
    reset_at_raw = user.get("searches_reset_at", "")
    try:
        reset_at = datetime.fromisoformat(reset_at_raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        reset_at = now  # assume reset is needed
    if now >= reset_at:
        from datetime import timedelta
        # Advance reset_at to the same day next month
        next_reset = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        db = get_client()
        result = (
            db.table("users")
            .update({
                "searches_used_this_month": 0,
                "searches_reset_at": next_reset.isoformat(),
            })
            .eq("id", user["id"])
            .execute()
        )
        return result.data[0] if result.data else user
    return user


def increment_search_count(user_id: str) -> None:
    db = get_client()
    db.rpc("increment_search_count", {"user_id_input": user_id}).execute()


def set_stripe_customer(clerk_user_id: str, stripe_customer_id: str) -> None:
    db = get_client()
    db.table("users").update(
        {"stripe_customer_id": stripe_customer_id}
    ).eq("clerk_user_id", clerk_user_id).execute()


def update_plan(clerk_user_id: str, plan: str) -> None:
    db = get_client()
    db.table("users").update({"plan": plan}).eq("clerk_user_id", clerk_user_id).execute()


def get_user_by_stripe_customer(stripe_customer_id: str) -> Optional[dict]:
    db = get_client()
    result = (
        db.table("users")
        .select("*")
        .eq("stripe_customer_id", stripe_customer_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ── Subscription helpers ─────────────────────────────────────────────────────

def upsert_subscription(
    user_id: str,
    stripe_subscription_id: str,
    stripe_price_id: str,
    plan: str,
    status: str,
    current_period_end: Optional[str],
) -> None:
    db = get_client()
    db.table("subscriptions").upsert(
        {
            "user_id": user_id,
            "stripe_subscription_id": stripe_subscription_id,
            "stripe_price_id": stripe_price_id,
            "plan": plan,
            "status": status,
            "current_period_end": current_period_end,
        },
        on_conflict="stripe_subscription_id",
    ).execute()
