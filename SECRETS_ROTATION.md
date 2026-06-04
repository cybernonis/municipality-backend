# Secrets Rotation Guide — Municipality Backend

**Rotation cadence:** every 90 days (or immediately on suspected leak).
**`.env` is listed in `.gitignore` and must never be committed.**

---

## Secrets inventory

### SUPABASE_URL
| Field | Value |
|---|---|
| **Location** | Supabase dashboard → Project Settings → API → Project URL |
| **Used by** | Railway backend (env var), all supabase-py clients |
| **Rotation** | URLs don't rotate; if the project is deleted/recreated update all consumers below |
| **Blast radius** | Low on its own — useless without a key |
| **Update in** | Railway → Variables; `.env` locally |

---

### SUPABASE_ANON_KEY
| Field | Value |
|---|---|
| **Location** | Supabase dashboard → Project Settings → API → `anon` / `public` key |
| **Used by** | Railway backend (`get_auth_client()`), Flutter app, React dashboard |
| **Rotation** | Supabase dashboard → API → "Regenerate" anon key |
| **Blast radius** | Medium — allows public sign-in and RLS-gated reads; cannot bypass RLS |
| **Update in** | Railway → Variables; Vercel → Environment Variables; Flutter `lib/config.dart`; `.env` locally |

---

### SUPABASE_SERVICE_KEY
| Field | Value |
|---|---|
| **Location** | Supabase dashboard → Project Settings → API → `service_role` key |
| **Used by** | Railway backend only (`get_supabase()` — DB operations, admin auth API) |
| **Rotation** | Supabase dashboard → API → "Regenerate" service_role key |
| **Blast radius** | **CRITICAL** — bypasses all RLS; full read/write/delete on every table |
| **Update in** | Railway → Variables; `.env` locally; redeploy immediately |
| **Never expose** | Must never appear in frontend code, logs, or git history |

---

### SECRET_KEY
| Field | Value |
|---|---|
| **Location** | Railway backend environment variable |
| **Used by** | JWT signing / internal session tokens (if applicable) |
| **Rotation** | Generate new: `python -c "import secrets; print(secrets.token_hex(32))"` |
| **Blast radius** | High — allows forging internal tokens if leaked |
| **Update in** | Railway → Variables; `.env` locally; all active sessions are invalidated |

---

### ANTHROPIC_API_KEY
| Field | Value |
|---|---|
| **Location** | Anthropic console → API Keys |
| **Used by** | Railway backend — Claude API calls (AI chat, report classification, AI actions) |
| **Rotation** | Anthropic console → revoke old key → create new key |
| **Blast radius** | High — incurs API costs; could be used to consume quota |
| **Update in** | Railway → Variables; `.env` locally |

---

### BREVO_API_KEY
| Field | Value |
|---|---|
| **Location** | Brevo dashboard → Account → SMTP & API → API Keys |
| **Used by** | Railway backend — all transactional email (verification, new-device alerts, high-severity) |
| **Rotation** | Brevo dashboard → revoke → create new key |
| **Blast radius** | Medium — allows sending email from the project's sender domain; reputational risk |
| **Update in** | Railway → Variables; `.env` locally |

---

### STRIPE_SECRET_KEY
| Field | Value |
|---|---|
| **Location** | Stripe dashboard → Developers → API Keys → Secret key |
| **Used by** | Railway backend — payment processing |
| **Rotation** | Stripe dashboard → "Roll key" (Stripe supports rolling without downtime) |
| **Blast radius** | **CRITICAL** — can create charges, issue refunds, access payment data |
| **Update in** | Railway → Variables; `.env` locally; roll before revoking old key |

---

### STRIPE_PUBLISHABLE_KEY
| Field | Value |
|---|---|
| **Location** | Stripe dashboard → Developers → API Keys → Publishable key |
| **Used by** | Railway backend and React dashboard (client-side Stripe.js) |
| **Rotation** | Rolls automatically when secret key is rolled |
| **Blast radius** | Low — public by design; cannot perform server-side operations |
| **Update in** | Railway → Variables; Vercel → Environment Variables; `.env` locally |

---

### FIREBASE_SERVICE_ACCOUNT
| Field | Value |
|---|---|
| **Location** | Firebase console → Project Settings → Service Accounts → Generate new private key (JSON) |
| **Used by** | Railway backend — FCM push notifications |
| **Rotation** | Firebase console → generate new key → update env → delete old key from Firebase |
| **Blast radius** | High — full Firebase Admin SDK access (FCM, Firestore, Auth if enabled) |
| **Update in** | Railway → Variables (store as JSON string); `.env` locally |

---

### GOOGLE_PLACES_KEY
| Field | Value |
|---|---|
| **Location** | Google Cloud Console → APIs & Services → Credentials |
| **Used by** | Railway backend — Places API calls |
| **Rotation** | Google Cloud Console → delete old key → create restricted new key |
| **Blast radius** | Medium — incurs GCP costs; restrict to specific APIs and IPs in console |
| **Update in** | Railway → Variables; `.env` locally |

---

### OPENWEATHER_API_KEY
| Field | Value |
|---|---|
| **Location** | OpenWeatherMap account → API keys |
| **Used by** | Railway backend — weather external data monitoring |
| **Rotation** | OpenWeatherMap dashboard → generate new key → delete old |
| **Blast radius** | Low — read-only weather data; quota abuse risk |
| **Update in** | Railway → Variables; `.env` locally |

---

### TOMTOM_API_KEY
| Field | Value |
|---|---|
| **Location** | TomTom Developer Portal → My Apps |
| **Used by** | Railway backend — traffic data |
| **Rotation** | TomTom portal → regenerate key |
| **Blast radius** | Low — read-only traffic data; quota abuse risk |
| **Update in** | Railway → Variables; `.env` locally |

---

### HERE_API_KEY
| Field | Value |
|---|---|
| **Location** | HERE Developer Portal → Projects → API Keys |
| **Used by** | Railway backend — mapping / geocoding |
| **Rotation** | HERE portal → revoke → create new key |
| **Blast radius** | Low — read-only geo data; quota abuse risk |
| **Update in** | Railway → Variables; `.env` locally |

---

## 90-day rotation checklist

Run this checklist every 90 days (or immediately after a suspected leak):

- [ ] **Supabase anon key** — regenerate in dashboard; update Railway, Vercel, Flutter, `.env`
- [ ] **Supabase service key** — regenerate; update Railway, `.env`; redeploy immediately
- [ ] **SECRET_KEY** — generate new hex token; update Railway, `.env`
- [ ] **ANTHROPIC_API_KEY** — revoke old key; create new; update Railway, `.env`
- [ ] **BREVO_API_KEY** — revoke old; create new; update Railway, `.env`
- [ ] **STRIPE_SECRET_KEY** — roll via Stripe dashboard; update Railway, `.env`
- [ ] **FIREBASE_SERVICE_ACCOUNT** — generate new JSON; update Railway; revoke old in Firebase console
- [ ] **GOOGLE_PLACES_KEY** — rotate in GCP console; update Railway, `.env`
- [ ] **OPENWEATHER_API_KEY** — rotate in dashboard; update Railway, `.env`
- [ ] **TOMTOM_API_KEY** — rotate in portal; update Railway, `.env`
- [ ] **HERE_API_KEY** — rotate in portal; update Railway, `.env`
- [ ] Verify `.env` is still listed in `.gitignore` and has no staged changes (`git status`)
- [ ] Run `git log --all --full-history -- .env` — confirm no `.env` commits exist
- [ ] Run the retention purge: `POST /admin/retention/purge?dry_run=false`
- [ ] Check Railway deploy logs for any `[RETENTION]` errors

## Emergency: leaked secret

1. **Revoke immediately** in the issuing console — don't wait.
2. Issue replacement secret and update Railway variables.
3. Trigger a Railway redeploy.
4. For `SUPABASE_SERVICE_KEY`: check Supabase logs for unexpected queries.
5. For `STRIPE_SECRET_KEY`: check Stripe dashboard for unauthorized charges.
6. For `ANTHROPIC_API_KEY`: check usage dashboard for anomalous spend.
7. Document the incident (what leaked, when discovered, actions taken).
