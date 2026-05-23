from fastapi import APIRouter, HTTPException
from app.database import supabase
from app.config import STRIPE_SECRET_KEY
from pydantic import BaseModel
from typing import Optional
import stripe
import uuid

stripe.api_key = STRIPE_SECRET_KEY

router = APIRouter()

PAYMENT_TYPES = {
    "municipal_tax":  {"label": "Δημοτικά Τέλη",              "icon": "🏠"},
    "parking_fine":   {"label": "Πρόστιμο Στάθμευσης",        "icon": "🚗"},
    "nursery":        {"label": "Παιδικός Σταθμός",            "icon": "🧒"},
    "sports":         {"label": "Αθλητικές Εγκαταστάσεις",    "icon": "🏊"},
    "cemetery":       {"label": "Δημοτικό Νεκροταφείο",       "icon": "🪦"},
    "permit":         {"label": "Αδειοδότηση",                 "icon": "📋"},
}

class PaymentCreate(BaseModel):
    user_id: Optional[str] = None
    amount: float
    payment_type: str
    description: Optional[str] = None

class PaymentIntent(BaseModel):
    amount: float
    payment_type: str
    description: Optional[str] = None
    user_id: Optional[str] = None

@router.get("/types")
def get_payment_types():
    return [
        {"key": k, "label": v["label"], "icon": v["icon"]}
        for k, v in PAYMENT_TYPES.items()
    ]

@router.post("/create-intent")
def create_payment_intent(payment: PaymentIntent):
    try:
        # Δημιούργησε Stripe Payment Intent
        intent = stripe.PaymentIntent.create(
            amount=int(payment.amount * 100),  # cents
            currency="eur",
            metadata={
                "payment_type": payment.payment_type,
                "user_id": payment.user_id or "anonymous",
                "description": payment.description or "",
            }
        )

        # Αποθήκευσε στη βάση
        supabase.table("payments").insert({
            "id": str(uuid.uuid4()),
            "user_id": payment.user_id,
            "amount": payment.amount,
            "type": payment.payment_type,
            "status": "pending",
        }).execute()

        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "amount": payment.amount,
        }

    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/confirm/{payment_intent_id}")
def confirm_payment(payment_intent_id: str):
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)

        status = "completed" if intent.status == "succeeded" else "failed"

        # Ενημέρωσε τη βάση
        supabase.table("payments")\
            .update({"status": status})\
            .eq("type", intent.metadata.get("payment_type", ""))\
            .execute()

        return {
            "status": status,
            "amount": intent.amount / 100,
            "payment_type": intent.metadata.get("payment_type"),
        }

    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/history/{user_id}")
def get_payment_history(user_id: str):
    result = supabase.table("payments")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()
    return result.data

@router.get("/stats")
def get_payment_stats():
    result = supabase.table("payments")\
        .select("*")\
        .execute()

    payments = result.data or []
    total = sum(p["amount"] for p in payments if p["status"] == "completed")
    count = len([p for p in payments if p["status"] == "completed"])
    pending = len([p for p in payments if p["status"] == "pending"])

    return {
        "total_revenue": round(total, 2),
        "completed_payments": count,
        "pending_payments": pending,
        "by_type": {
            ptype: {
                "count": len([p for p in payments if p["type"] == ptype]),
                "total": round(sum(p["amount"] for p in payments if p["type"] == ptype and p["status"] == "completed"), 2)
            }
            for ptype in PAYMENT_TYPES.keys()
        }
    }