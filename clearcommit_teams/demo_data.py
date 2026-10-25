"""Clearly labelled sample conversations for the offline demonstration.

These are fictional examples, not customer data. They exist so the product can
be evaluated end to end without accounts, credentials, or a paid provider.
"""

from __future__ import annotations

from .db import Database
from .models import now_utc

SAMPLES = [
    {
        "id": "s_sample_helio",
        "title": "Helio Logistics — Renewal call",
        "customer_name": "Marisol Vega",
        "company": "Helio Logistics",
        "rep_name": "You",
        "customer_language": "es",
        "rep_language": "en",
        "occurred_on": "2026-10-21",
        "created_at": "2026-10-21T09:00:00Z",
        "utterances": [
            ("customer", "es", "00:04",
             "Antes que nada, gracias por el tiempo. Queremos renovar, pero el precio del plan anual nos preocupa bastante.",
             "First of all, thank you for the time. We want to renew, but the price of the annual plan concerns us quite a bit."),
            ("rep", "en", "00:23",
             "Totally understand. It's a big number, but once you see the new dashboard you'll agree it's worth it.",
             None),
            ("customer", "es", "00:41",
             "No estoy segura de que el equipo lo use. La última vez casi nadie entró a la plataforma.",
             "I'm not sure the team will use it. Last time almost nobody logged into the platform."),
            ("rep", "en", "01:02",
             "We can definitely help with adoption. I'll send over some materials soon.",
             None),
            ("customer", "en", "01:24",
             "And what happens to our current contract if we switch to the annual plan mid-cycle? We have an invoice coming next month.",
             None),
            ("rep", "en", "01:43",
             "That's a great question. The team is looking at it and we'll figure something out.",
             None),
            ("customer", "es", "02:08",
             "También necesitamos saber si la integración con nuestro sistema de facturación sigue incluida. En la propuesta anterior no quedaba claro.",
             "We also need to know whether the integration with our billing system is still included. It wasn't clear in the previous proposal."),
            ("rep", "en", "02:31",
             "Yes, I believe that's included. I'd have to check the SOW, but I'm pretty sure.",
             None),
            ("customer", "en", "03:04",
             "If we can get clarity on those two points, I can take it to finance this week. But I can't promise approval.",
             None),
            ("rep", "en", "03:19",
             "Perfect, so we're aligned. I'll get you something by end of week.",
             None),
        ],
    },
    {
        "id": "s_sample_northwind",
        "title": "Northwind Health — Security review",
        "customer_name": "Ayesha Khan",
        "company": "Northwind Health",
        "rep_name": "You",
        "customer_language": "ur",
        "rep_language": "en",
        "occurred_on": "2026-10-19",
        "created_at": "2026-10-19T14:30:00Z",
        "utterances": [
            ("customer", "ur", "00:06",
             "ہمیں اپنے سیکیورٹی جائزے کے لیے ڈیٹا رہنے کی جگہ اور SSO کی تفصیل چاہیے۔",
             "We need details on data residency and SSO for our security review."),
            ("rep", "en", "00:27",
             "I believe we support that. Our security team handles those questions, so I'd have to ask around.",
             None),
            ("customer", "ur", "00:49",
             "کیا آپ ہمیں SOC 2 رپورٹ اور ڈیٹا پروسیسنگ ایگریمنٹ بھیج سکتے ہیں؟",
             "Can you send us the SOC 2 report and the data processing agreement?"),
            ("rep", "en", "01:12",
             "Probably, yes. Let me check and get back to you soon.",
             None),
            ("customer", "en", "01:38",
             "The review is blocked until we have those documents. Can you confirm a date?",
             None),
            ("rep", "en", "02:01",
             "I'll try to get something over this week.",
             None),
            ("customer", "en", "02:22",
             "Who should I list as the security contact on our side? We need a named owner.",
             None),
            ("rep", "en", "02:46",
             "Good question. I'm not sure yet — I'll ask.",
             None),
        ],
    },
    {
        "id": "s_sample_atlas",
        "title": "Atlas Retail — Pilot debrief",
        "customer_name": "Camille Laurent",
        "company": "Atlas Retail",
        "rep_name": "You",
        "customer_language": "fr",
        "rep_language": "en",
        "occurred_on": "2026-10-16",
        "created_at": "2026-10-16T11:15:00Z",
        "utterances": [
            ("customer", "fr", "00:08",
             "Le pilote a aidé les équipes, mais l'onboarding était confus pour les responsables de magasin.",
             "The pilot helped the teams, but onboarding was confusing for store managers."),
            ("rep", "en", "00:38",
             "That's great feedback. For 40 stores, I can probably get you a better price.",
             None),
            ("customer", "fr", "00:58",
             "Avant de parler du prix, nous devons comprendre le temps de déploiement et la formation.",
             "Before we talk about price, we need to understand deployment time and training."),
            ("rep", "en", "01:21",
             "Sure. It usually takes a few weeks, depending on stuff.",
             None),
            ("customer", "fr", "01:44",
             "Pouvez-vous partager un plan de déploiement pour 40 magasins ?",
             "Can you share a deployment plan for 40 stores?"),
            ("rep", "en", "02:05",
             "I'll send something soon.",
             None),
            ("customer", "en", "02:26",
             "We also need our operations lead to see the admin view. Could we book a working session next week?",
             None),
            ("rep", "en", "02:47",
             "Perfect, I'll set it up. We're aligned on the value.",
             None),
        ],
    },
]


def seed_samples(db: Database) -> int:
    """Insert the fictional sample conversations once. Returns rows added."""
    added = 0
    with db.connection() as conn:
        for sample in SAMPLES:
            exists = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (sample["id"],)
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO sessions(id, title, customer_name, company, rep_name, "
                "customer_language, rep_language, occurred_on, source, is_sample, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'sample', 1, ?, ?)",
                (
                    sample["id"], sample["title"], sample["customer_name"],
                    sample["company"], sample["rep_name"],
                    sample["customer_language"], sample["rep_language"],
                    sample["occurred_on"], sample["created_at"], sample["created_at"],
                ),
            )
            for seq, (speaker, language, display_time, original, translation) in enumerate(
                sample["utterances"], start=1
            ):
                conn.execute(
                    "INSERT INTO utterances(id, session_id, seq, speaker, original_text, "
                    "translation, language, display_time, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"u_{sample['id'][2:]}_{seq:02d}", sample["id"], seq, speaker,
                        original, translation, language, display_time, sample["created_at"],
                    ),
                )
            added += 1
    if added:
        db.set_meta("samples_seeded_at", now_utc())
    return added
