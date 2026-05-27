import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import supabase

logger = logging.getLogger(__name__)
router = APIRouter()

# --- MODELS ---
class PollCreate(BaseModel):
    title: str
    description: Optional[str] = None
    options: list
    ends_at: Optional[str] = None
    created_by: Optional[str] = None

class VoteCreate(BaseModel):
    poll_id: str
    user_id: str
    option_index: int

class ProposalCreate(BaseModel):
    user_id: Optional[str] = None
    title: str
    description: Optional[str] = None

# --- POLLS ---
@router.get("/polls")
def get_polls():
    try:
        result = supabase.table("polls").select("*").order("created_at", desc=True).execute()
        return result.data
    except Exception as e:
        logger.error(f"get_polls error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/polls")
def create_poll(poll: PollCreate):
    try:
        data = {
            "id":          str(uuid.uuid4()),
            "title":       poll.title,
            "description": poll.description,
            "options":     poll.options,
            "ends_at":     poll.ends_at,
            "created_by":  poll.created_by,
            "status":      "active",
        }
        result = supabase.table("polls").insert(data).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Αποτυχία εισαγωγής — ο πίνακας polls πιθανώς δεν υπάρχει")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"create_poll error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Σφάλμα δημιουργίας poll: {e}. Βεβαιωθείτε ότι υπάρχει ο πίνακας polls στη Supabase.",
        )

@router.get("/polls/{poll_id}/results")
def get_poll_results(poll_id: str):
    # Πάρε votes
    votes = supabase.table("poll_votes")\
        .select("option_index")\
        .eq("poll_id", poll_id)\
        .execute()

    # Πάρε poll
    poll = supabase.table("polls")\
        .select("*")\
        .eq("id", poll_id)\
        .execute()

    if not poll.data:
        raise HTTPException(status_code=404, detail="Poll not found")

    poll_data = poll.data[0]
    options = poll_data["options"]

    # Μέτρησε votes ανά option
    results = []
    total_votes = len(votes.data)

    for i, option in enumerate(options):
        count = len([v for v in votes.data if v["option_index"] == i])
        percentage = round((count / total_votes * 100) if total_votes > 0 else 0)
        results.append({
            "option": option,
            "votes": count,
            "percentage": percentage
        })

    return {
        "poll": poll_data,
        "results": results,
        "total_votes": total_votes
    }

@router.post("/polls/vote")
def vote_poll(vote: VoteCreate):
    # Έλεγξε αν έχει ήδη ψηφίσει
    existing = supabase.table("poll_votes")\
        .select("id")\
        .eq("poll_id", vote.poll_id)\
        .eq("user_id", vote.user_id)\
        .execute()

    if existing.data:
        raise HTTPException(status_code=400, detail="Έχετε ήδη ψηφίσει")

    data = {
        "id": str(uuid.uuid4()),
        "poll_id": vote.poll_id,
        "user_id": vote.user_id,
        "option_index": vote.option_index,
    }
    result = supabase.table("poll_votes").insert(data).execute()
    return {"message": "Η ψήφος καταχωρήθηκε!", "vote": result.data[0]}

# --- PROPOSALS ---
@router.get("/proposals")
def get_proposals():
    result = supabase.table("proposals")\
        .select("*")\
        .order("votes", desc=True)\
        .execute()
    return result.data

@router.post("/proposals")
def create_proposal(proposal: ProposalCreate):
    data = {
        "id": str(uuid.uuid4()),
        "user_id": proposal.user_id,
        "title": proposal.title,
        "description": proposal.description,
        "votes": 0,
        "status": "open"
    }
    result = supabase.table("proposals").insert(data).execute()
    return result.data[0]

@router.post("/proposals/{proposal_id}/vote")
def vote_proposal(proposal_id: str):
    # Αύξησε votes κατά 1
    proposal = supabase.table("proposals")\
        .select("votes")\
        .eq("id", proposal_id)\
        .execute()

    if not proposal.data:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε")

    current_votes = proposal.data[0]["votes"]
    result = supabase.table("proposals")\
        .update({"votes": current_votes + 1})\
        .eq("id", proposal_id)\
        .execute()

    return {"message": "Ψήφος καταχωρήθηκε!", "votes": current_votes + 1}