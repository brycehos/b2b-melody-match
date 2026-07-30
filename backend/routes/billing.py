"""
Billing routes: Stripe checkout session creation and customer portal.
"""

import asyncio
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import database
import stripe_client
import auth_middleware

router = APIRouter(prefix="/api/billing", tags=["billing"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


class CheckoutRequest(BaseModel):
    plan: Literal["explorer", "unlimited"]


class PortalRequest(BaseModel):
    pass  # return_url derived from env


def _require_user(request: Request) -> dict:
    """Extract and verify the Clerk JWT, return the DB user row."""
    auth = request.headers.get("Authorization", "")
    clerk_user_id = auth_middleware.get_clerk_user_id(auth)
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = database.get_or_create_user(clerk_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, request: Request):
    user = await asyncio.get_event_loop().run_in_executor(None, _require_user, request)

    # Get or create a Stripe customer
    email = user.get("email", "")
    stripe_customer_id = user.get("stripe_customer_id")
    if not stripe_customer_id:
        stripe_customer_id = await asyncio.get_event_loop().run_in_executor(
            None,
            stripe_client.get_or_create_customer,
            user["clerk_user_id"],
            email,
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            database.set_stripe_customer,
            user["clerk_user_id"],
            stripe_customer_id,
        )

    checkout_url = await asyncio.get_event_loop().run_in_executor(
        None,
        stripe_client.create_checkout_session,
        body.plan,
        stripe_customer_id,
        f"{FRONTEND_URL}/?upgraded=true",
        f"{FRONTEND_URL}/?upgraded=false",
    )

    return {"url": checkout_url}


@router.post("/portal")
async def billing_portal(request: Request):
    user = await asyncio.get_event_loop().run_in_executor(None, _require_user, request)

    stripe_customer_id = user.get("stripe_customer_id")
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active subscription found")

    portal_url = await asyncio.get_event_loop().run_in_executor(
        None,
        stripe_client.create_billing_portal_session,
        stripe_customer_id,
        FRONTEND_URL,
    )
    return {"url": portal_url}


@router.get("/me")
async def get_subscription_info(request: Request):
    """Return the current user's plan and usage for the frontend."""
    auth = request.headers.get("Authorization", "")
    clerk_user_id = auth_middleware.get_clerk_user_id(auth)
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = await asyncio.get_event_loop().run_in_executor(
        None, database.get_or_create_user, clerk_user_id
    )
    # Reset monthly count if window has passed
    user = await asyncio.get_event_loop().run_in_executor(
        None, database.maybe_reset_monthly_count, user
    )

    plan = user.get("plan", "free")
    used = user.get("searches_used_this_month", 0)
    limit = database.SEARCH_LIMITS.get(plan, 10)

    return {
        "plan": plan,
        "searches_used": used,
        "searches_limit": limit,
        "searches_remaining": max(0, limit - used),
        "has_stripe_customer": bool(user.get("stripe_customer_id")),
    }
