import anthropic
import base64
import json
from app.config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CATEGORIES = {
    "road_damage":  "technical_services",
    "lighting":     "lighting",
    "waste":        "waste_management",
    "water_leak":   "water_services",
    "vandalism":    "technical_services",
    "fallen_tree":  "environment",
    "other":        "technical_services"
}

async def classify_image(image_bytes: bytes, description: str = None) -> dict:
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    prompt = f"""
Είσαι σύστημα κατηγοριοποίησης προβλημάτων για τον Δήμο Ηρακλείου.
Ανάλυσε την εικόνα και κατηγοριοποίησε το πρόβλημα.
{"Περιγραφή πολίτη: " + description if description else ""}

Απάντησε ΜΟΝΟ με JSON, χωρίς άλλο κείμενο:
{{
  "category": "road_damage | lighting | waste | water_leak | vandalism | fallen_tree | other",
  "severity": "low | medium | high",
  "confidence": 0.0-1.0,
  "reasoning": "σύντομη εξήγηση στα ελληνικά"
}}

Κανόνες severity:
- high: κίνδυνος δημόσιας ασφάλειας
- medium: υποδομή που χρειάζεται επισκευή
- low: αισθητικό πρόβλημα
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ],
            }
        ],
    )

    # Debug - βλέπουμε τι επιστρέφει το Claude
    raw_text = message.content[0].text
    print(f"🤖 Claude response: {raw_text}")

    # Καθαρισμός του JSON
    import re
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if json_match:
        json_str = json_match.group()
        result = json.loads(json_str)
    else:
        # Fallback αν δεν βρει JSON
        result = {
            "category": "other",
            "severity": "medium",
            "confidence": 0.5,
            "reasoning": "Δεν ήταν δυνατή η αυτόματη κατηγοριοποίηση"
        }

    result["department"] = CATEGORIES.get(result["category"], "technical_services")
    return result