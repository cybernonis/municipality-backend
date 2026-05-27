import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import supabase

logger = logging.getLogger(__name__)
router = APIRouter()

# kg CO2 αποτραπέντων εκπομπών ανά κατηγορία αναφοράς
CARBON_MAP: dict[str, float] = {
    "pothole":                 2.3,
    "road_damage":             2.3,
    "traffic_light":           1.5,
    "lighting":                3.2,
    "waste":                   4.5,
    "water_leak":              6.8,
    "flooding":                5.1,
    "vandalism":               0.5,
    "fallen_tree":             1.8,
    "pest_control":            2.0,
    "abandoned_building":      3.5,
    "illegal_parking":         1.2,
    "noise_pollution":         0.8,
    "environmental_pollution": 7.5,
    "dangerous_construction":  4.0,
    "irrigation_damage":       3.8,
    "other":                   1.0,
}

CARBON_REASONS: dict[str, str] = {
    "pothole":                 "Αποφυγή καταστροφής ελαστικών και αυξημένης κατανάλωσης καυσίμου",
    "road_damage":             "Βελτίωση ροής κυκλοφορίας, μείωση καυσαερίων",
    "traffic_light":           "Αποφυγή κυκλοφοριακού χάους και αυξημένων εκπομπών CO₂",
    "lighting":                "Βελτιστοποίηση ενεργειακής κατανάλωσης δημόσιου φωτισμού",
    "waste":                   "Πρόληψη μεθανίου από αποσύνθεση σκουπιδιών",
    "water_leak":              "Εξοικονόμηση ενέργειας άντλησης και επεξεργασίας νερού",
    "flooding":                "Αποφυγή αποσύνθεσης οργανικής ύλης και εκπομπών μεθανίου",
    "vandalism":               "Αποφυγή παραγωγής νέων υλικών αντικατάστασης",
    "fallen_tree":             "Διατήρηση ικανότητας CO₂ απορρόφησης δέντρου",
    "pest_control":            "Αποφυγή χημικής επέμβασης μεγάλης κλίμακας",
    "abandoned_building":      "Αποφυγή εκπομπών από αποσύνθεση δομικών υλικών",
    "illegal_parking":         "Βελτίωση κυκλοφοριακής ροής, μείωση καυσαερίων",
    "noise_pollution":         "Μείωση ενεργειακής κατανάλωσης από δονήσεις υποδομής",
    "environmental_pollution": "Πρόληψη περαιτέρω μόλυνσης εδάφους και υπόγειων υδάτων",
    "dangerous_construction":  "Πρόληψη ατυχήματος και επακόλουθων έκτακτων επεμβάσεων",
    "irrigation_damage":       "Εξοικονόμηση νερού και ενέργειας υδρευτικής άντλησης",
    "other":                   "Γενική βελτίωση αστικού περιβάλλοντος",
}


def _car_km_equivalent(kg: float) -> str:
    km = round(kg / 0.12, 1)   # ~0.12 kg CO2/km μέσο αυτοκίνητο
    return f"≈ {km} km οδήγηση βενζινοκίνητου αυτοκινήτου"


class CarbonRequest(BaseModel):
    report_category: str
    user_id: Optional[str] = None


@router.post("/calculate")
def calculate_carbon(payload: CarbonRequest):
    try:
        kg_saved = CARBON_MAP.get(payload.report_category, CARBON_MAP["other"])
        reason   = CARBON_REASONS.get(payload.report_category, CARBON_REASONS["other"])

        updated_total: Optional[float] = None

        if payload.user_id:
            existing = (
                supabase.table("user_points")
                .select("carbon_saved")
                .eq("user_id", payload.user_id)
                .execute()
            )
            if existing.data:
                prev   = existing.data[0]["carbon_saved"] or 0.0
                new_total = round(prev + kg_saved, 2)
                supabase.table("user_points").update({
                    "carbon_saved": new_total,
                    "updated_at":   datetime.now(timezone.utc).isoformat(),
                }).eq("user_id", payload.user_id).execute()
            else:
                new_total = round(kg_saved, 2)
                supabase.table("user_points").insert({
                    "user_id":      payload.user_id,
                    "points":       0,
                    "badges":       [],
                    "level":        1,
                    "carbon_saved": new_total,
                }).execute()
            updated_total = new_total

        return {
            "report_category":             payload.report_category,
            "carbon_saved_kg":             kg_saved,
            "reason":                      reason,
            "equivalent":                  _car_km_equivalent(kg_saved),
            "user_total_carbon_saved_kg":  updated_total,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
