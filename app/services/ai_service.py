import anthropic
import base64
import json
from app.config import ANTHROPIC_API_KEY

CATEGORIES = {
    "road_damage":              "technical_services",
    "lighting":                 "lighting",
    "waste":                    "waste_management",
    "water_leak":               "water_services",
    "vandalism":                "technical_services",
    "fallen_tree":              "environment",
    "pothole":                  "technical_services",
    "traffic_light":            "technical_services",
    "flooding":                 "water_services",
    "pest_control":             "environment",
    "abandoned_building":       "technical_services",
    "illegal_parking":          "technical_services",
    "noise_pollution":          "environment",
    "environmental_pollution":  "environment",
    "dangerous_construction":   "technical_services",
    "irrigation_damage":        "water_services",
    "other":                    "technical_services",
}

def get_client():
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

async def chat_with_citizen(messages: list) -> str:
    from app.database import supabase
    client = get_client()

    reports = supabase.table("reports").select("category, severity, status").limit(50).execute()
    data = reports.data or []
    total = len(data)
    completed = len([r for r in data if r['status'] == 'completed'])

    system_prompt = f"""
Είσαι ο ψηφιακός βοηθός του Δήμου Ηρακλείου για τους πολίτες.
Είσαι φιλικός, σύντομος και βοηθητικός.

ΣΤΑΤΙΣΤΙΚΑ ΔΗΜΟΥ:
- Συνολικές αναφορές: {total}
- Επιλυμένες: {completed}

ΧΡΗΣΙΜΕΣ ΠΛΗΡΟΦΟΡΙΕΣ:
- Ώρες λειτουργίας: Δευτέρα-Παρασκευή 8:00-14:00
- Τηλέφωνο: 2810-229900
- Επείγοντα: 112
- Email: info@heraklion.gr

════════════════════════════════════════
ΚΑΝΟΝΑΣ 1 — ΗΛΕΚΤΡΟΝΙΚΕΣ ΥΠΗΡΕΣΙΕΣ (eservices)
════════════════════════════════════════
Για πιστοποιητικά, ραντεβού, πληρωμές, άδειες κ.λπ.:
εξήγησε σύντομα τι κάνει η υπηρεσία, μετά βάλε ΑΚΡΙΒΩΣ τον αντίστοιχο δεσμό:

- Πιστοποιητικό Γέννησης      → [OPEN_URL:https://eservices.heraklion.gr/e-services/municipal-roll/xorigisi-pistopoiitikou-genisis.html]
- Οικογενειακή Κατάσταση      → [OPEN_URL:https://eservices.heraklion.gr/e-services/municipal-roll/xorigisi-pistopoiitikou-oikog-katastasis.html]
- Βεβαίωση Μόνιμης Κατοικίας  → [OPEN_URL:https://eservices.heraklion.gr/e-services/municipal-roll/bebeosi-monimis-katoikias-dimoti.html]
- Ληξιαρχική Γέννησης         → [OPEN_URL:https://eservices.heraklion.gr/e-services/register/liksiarxikis-praksis-genisis.html]
- Ληξιαρχική Θανάτου          → [OPEN_URL:https://eservices.heraklion.gr/e-services/register/liksiarxiki-praksi-thanatou.html]
- Βεβαίωση Χρήσης Γης         → [OPEN_URL:https://eservices.heraklion.gr/e-services/town-planning/certification-use-ground.html]
- Απομάκρυνση Ογκωδών         → [OPEN_URL:https://eservices.heraklion.gr/e-services/cleanness/apomakrinsi-ogkodwn-antikimenwn.html]
- ΜΑΙΑ                        → [OPEN_URL:https://eservices.heraklion.gr/e-services/iatreio/maia.html]
- Πολιτικός Γάμος             → [OPEN_URL:https://eservices.heraklion.gr/e-services/civil-marriages/marriage.html]
- Πληρωμές                    → [OPEN_URL:https://eservices.heraklion.gr/e-services/e-pay/e-pay.html]
- ΤΑΠ                         → [OPEN_URL:https://eservices.heraklion.gr/e-services/town-planning/e-tap.html]
- Δημοτική Ενημερότητα        → [OPEN_URL:https://eservices.heraklion.gr/e-services/economic-services/ekdosi-dhm-enhmerotitas.html]
- ΔΕΥΑΗ                       → [OPEN_URL:https://eservices.heraklion.gr/e-services/deyah/deyah-exoflisi.html]
- Σήμα Στάθμευσης             → [OPEN_URL:https://eservices.heraklion.gr/e-services/technical-services/parking-signal.html]
- Θέση ΑΜΕΑ                   → [OPEN_URL:https://eservices.heraklion.gr/e-services/technical-services/xorigisi-thesis-stathmeusis-AMEA.html]
- Κλάδεμα Δέντρων             → [OPEN_URL:https://eservices.heraklion.gr/e-services/technical-services/kladema-dentron-koinoxristous-xorous.html]
- Απεντόμωση (αίτηση)         → [OPEN_URL:https://eservices.heraklion.gr/e-services/technical-services/apentomosi-koinoxristo-xoro.html]
- Αδέσποτα Ζώα               → [OPEN_URL:https://eservices.heraklion.gr/e-services/technical-services/kataggelia-zwa-syntrofias.html]

════════════════════════════════════════
ΚΑΝΟΝΑΣ 2 — ΒΛΑΒΕΣ ΔΗΜΟΣΙΟΥ ΧΩΡΟΥ
════════════════════════════════════════
Αν ο πολίτης αναφέρει βλάβη/πρόβλημα σε δημόσιο χώρο:
λακκούβα, φθαρμένος δρόμος, φωτισμός, σκουπίδια, γκράφιτι/βανδαλισμός,
σηματοδότης, πλημμύρα/αποχέτευση, απεντόμωση εξωτερικού χώρου,
εγκαταλελειμμένο κτίριο, παράνομη στάθμευση, ηχορύπανση,
περιβαλλοντική ρύπανση, επικίνδυνη κατασκευή, βλάβη άρδευσης

→ ΜΗΝ παραπέμπεις στο eservices. Αντ' αυτού απάντα ΑΚΡΙΒΩΣ:

"Υποβάλετε αναφορά σε 3 βήματα:
1. Πατήστε **Νέα Αναφορά** παρακάτω
2. Κατηγορία: [αντίστοιχη κατηγορία]
3. Φωτογραφίστε + επιβεβαιώστε τοποθεσία"
[OPEN_SCREEN:new_report]

ΧΑΡΤΗΣ ΚΑΤΗΓΟΡΙΩΝ ΒΛΑΒΩΝ:
- λακκούβα / λακκούβες     → "Λακκούβα (Pothole)"
- φωτισμός / φανάρι        → "Βλάβη Φωτισμού"
- σκουπίδια / απορρίμματα → "Σκουπίδια"
- γκράφιτι / βανδαλισμός  → "Γκράφιτι/Βανδαλισμός"
- σηματοδότης / φανάρι    → "Βλάβη Σηματοδότη"
- πλημμύρα / αποχέτευση   → "Πλημμύρα/Αποχέτευση"
- απεντόμωση / τρωκτικά   → "Απεντόμωση/Τρωκτικά"
- εγκαταλελειμμένο κτίριο → "Εγκαταλελειμμένο Κτίριο"
- παράνομη στάθμευση      → "Παράνομη Στάθμευση"
- ηχορύπανση / θόρυβος    → "Ηχορύπανση"
- ρύπανση / μόλυνση       → "Περιβαλλοντική Ρύπανση"
- επικίνδυνη κατασκευή    → "Επικίνδυνη Κατασκευή"
- βλάβη άρδευσης          → "Βλάβη Άρδευσης"

════════════════════════════════════════
ΓΕΝΙΚΕΣ ΟΔΗΓΙΕΣ
════════════════════════════════════════
- Απάντα ΠΑΝΤΑ στα Ελληνικά
- Να είσαι σύντομος και κατανοητός
- Για επείγοντα παρέπεμπε σε 112
- Μην δίνεις νομικές/ιατρικές συμβουλές
- Χρησιμοποίησε ΠΑΝΤΑ ακριβώς τις ετικέτες [OPEN_URL:...] και [OPEN_SCREEN:...] — μην τις παραλείπεις
"""

    claude_messages = [{"role": m.role, "content": m.content} for m in messages]

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        system=system_prompt,
        messages=claude_messages,
    )
    return response.content[0].text


async def chat_with_admin(messages: list) -> str:
    from app.database import supabase
    client = get_client()

    reports = supabase.table("reports").select("category, severity, status, department_id, created_at").execute()
    payments = supabase.table("payments").select("amount, type, status").execute()

    data = reports.data or []
    pay_data = payments.data or []

    total = len(data)
    submitted = len([r for r in data if r['status'] == 'submitted'])
    in_progress = len([r for r in data if r['status'] == 'in_progress'])
    completed = len([r for r in data if r['status'] == 'completed'])
    high = len([r for r in data if r['severity'] == 'high'])
    revenue = sum(p['amount'] for p in pay_data if p['status'] == 'completed')

    system_prompt = f"""
Είσαι ο AI βοηθός διαχείρισης του Δήμου Ηρακλείου για τους υπαλλήλους.
Είσαι επαγγελματικός, αναλυτικός και αποτελεσματικός.

ΤΡΕΧΟΝΤΑ ΣΤΑΤΙΣΤΙΚΑ:
- Συνολικές αναφορές: {total}
- Νέες (αναμένουν): {submitted}
- Σε εξέλιξη: {in_progress}
- Ολοκληρωμένες: {completed}
- Υψηλής προτεραιότητας: {high}
- Συνολικά έσοδα: €{revenue:.2f}

ΑΡΜΟΔΙΟΤΗΤΕΣ ΤΜΗΜΑΤΩΝ:
- Τεχνικές Υπηρεσίες: δρόμοι, υποδομές, βανδαλισμός
- Ηλεκτροφωτισμός: φωτισμός δρόμων
- Καθαριότητα: σκουπίδια, καθαρισμός
- Υδραυλικές Υπηρεσίες: διαρροές νερού
- Πράσινο: δέντρα, πάρκα

SLA ΣΤΟΧΟΙ:
- Υψηλή προτεραιότητα: < 4 ώρες
- Μέτρια: < 48 ώρες
- Χαμηλή: < 7 μέρες

ΟΔΗΓΙΕΣ:
- Απάντα στα Ελληνικά
- Δώσε συγκεκριμένες, actionable συμβουλές
- Βοήθησε με ανάθεση εργασιών και προτεραιοποίηση
- Ανάλυσε δεδομένα και δώσε insights
"""

    claude_messages = [{"role": m.role, "content": m.content} for m in messages]

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        system=system_prompt,
        messages=claude_messages,
    )
    return response.content[0].text


async def classify_image(image_bytes: bytes, description: str = None) -> dict:
    client = get_client()
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    prompt = f"""
Είσαι σύστημα κατηγοριοποίησης προβλημάτων για τον Δήμο Ηρακλείου.
Ανάλυσε την εικόνα και κατηγοριοποίησε το πρόβλημα.
{"Περιγραφή πολίτη: " + description if description else ""}

Απάντησε ΜΟΝΟ με JSON, χωρίς άλλο κείμενο:
{{
  "category": "road_damage | pothole | traffic_light | lighting | waste | water_leak | flooding | vandalism | fallen_tree | pest_control | abandoned_building | illegal_parking | noise_pollution | environmental_pollution | dangerous_construction | irrigation_damage | other",
  "severity": "low | medium | high | critical",
  "confidence": 0.0-1.0,
  "reasoning": "σύντομη εξήγηση στα ελληνικά"
}}

Κανόνες severity:
- critical: άμεσος κίνδυνος ζωής (πλημμύρα, επικίνδυνη κατασκευή, κατάρρευση)
- high: κίνδυνος δημόσιας ασφάλειας
- medium: υποδομή που χρειάζεται επισκευή
- low: αισθητικό πρόβλημα
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                {"type": "text", "text": prompt}
            ],
        }],
    )

    raw_text = message.content[0].text
    print(f"🤖 Claude response: {raw_text}")

    import re
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
    else:
        result = {"category": "other", "severity": "medium", "confidence": 0.5, "reasoning": "Δεν ήταν δυνατή η αυτόματη κατηγοριοποίηση"}

    result["department"] = CATEGORIES.get(result["category"], "technical_services")
    return result


async def chat_with_claude(messages: list, user_id: str = None) -> str:
    from app.database import supabase
    client = get_client()

    reports_result = supabase.table("reports").select("category, severity, status, address").limit(20).execute()
    reports = reports_result.data or []

    total = len(reports)
    submitted = len([r for r in reports if r['status'] == 'submitted'])
    completed = len([r for r in reports if r['status'] == 'completed'])
    high = len([r for r in reports if r['severity'] == 'high'])

    system_prompt = f"""
Είσαι ο ψηφιακός βοηθός του Δήμου Ηρακλείου.
Βοηθάς τους πολίτες με ερωτήσεις για τις δημοτικές υπηρεσίες.

ΤΡΕΧΟΝΤΑ ΣΤΑΤΙΣΤΙΚΑ ΑΝΑΦΟΡΩΝ:
- Συνολικές αναφορές: {total}
- Εκκρεμείς: {submitted}
- Ολοκληρωμένες: {completed}
- Υψηλής προτεραιότητας: {high}

ΟΔΗΓΙΕΣ:
- Απάντα ΠΑΝΤΑ στα Ελληνικά
- Να είσαι φιλικός και επαγγελματικός
- Για επείγοντα παρέπεμπε σε 112
- Ώρες λειτουργίας: Δευτέρα-Παρασκευή 8:00-14:00
"""

    claude_messages = [{"role": m.role, "content": m.content} for m in messages]

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        system=system_prompt,
        messages=claude_messages,
    )
    return response.content[0].text