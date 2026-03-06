#!/usr/bin/env python3
"""MietCheck AI-Advisor — Intelligente Mieterhöhungs-Empfehlungen.

Perspektive: Erfahrener Portfolio-Manager, 500+ Deals, Cash-Flow-First.
Berücksichtigt: Mietrecht (§§ 558ff BGB), Kappungsgrenze, Mietspiegel,
Wohnungszustand, Mieter-Kontext, optimales Timing.
"""
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import math

# ─── Konfiguration ───

# Angespannte Wohnungsmärkte (§ 558 Abs. 3 BGB) — Kappungsgrenze 15% statt 20%
TIGHT_MARKETS = {
    "berlin", "hamburg", "münchen", "köln", "frankfurt", "stuttgart",
    "düsseldorf", "dortmund", "essen", "bremen", "leipzig", "dresden",
    "hannover", "nürnberg", "freiburg", "heidelberg", "münster",
    "augsburg", "bonn", "karlsruhe", "mannheim", "wiesbaden", "potsdam",
    "rostock", "regensburg", "tübingen", "konstanz", "darmstadt",
}

# Mietvertrag-Typen
CONTRACT_TYPES = {
    "standard": "Standard-Mietvertrag (§ 558 BGB)",
    "index": "Indexmietvertrag (§ 557b BGB)",
    "staffel": "Staffelmietvertrag (§ 557a BGB)",
    "frei": "Freie Vereinbarung (Gewerbe/möbliert)",
    "sozial": "Sozialbindung / Fördermittel",
}

# Wohnungszustand → Aufschlag/Abschlag auf Mietspiegel
CONDITION_FACTORS = {
    "luxus": 1.20,       # +20% auf Mietspiegel
    "top": 1.10,         # +10%
    "gut": 1.00,         # Mietspiegel-Niveau
    "normal": 0.95,      # -5%
    "einfach": 0.85,     # -15%
    "renovierungsbedürftig": 0.70,  # -30%
}

CONDITION_LABELS = {
    "luxus": "Luxus / Hochwertig saniert",
    "top": "Top-Zustand / Modernisiert",
    "gut": "Guter Zustand",
    "normal": "Normaler Zustand",
    "einfach": "Einfache Ausstattung",
    "renovierungsbedürftig": "Renovierungsbedürftig",
}

# Ausstattungsmerkmale → Zuschläge auf €/m²
FEATURES_PREMIUM = {
    "balkon": 0.30,
    "terrasse": 0.50,
    "garten": 0.40,
    "einbaukueche": 0.40,
    "fussbodenheizung": 0.35,
    "aufzug": 0.25,
    "gaeste_wc": 0.20,
    "keller": 0.10,
    "dachgeschoss": 0.15,
    "parkett": 0.25,
    "badewanne_und_dusche": 0.20,
}


def estimate_market_rent(unit):
    """Schätzt die ortsübliche Vergleichsmiete wenn kein Mietspiegel-Wert vorliegt.

    Basiert auf: Standort, Baujahr, Zustand, Ausstattung, Wohnfläche.
    """
    # Wenn manueller Mietspiegel-Wert vorhanden
    if unit.get("market_rent_sqm") and float(unit.get("market_rent_sqm", 0)) > 0:
        return float(unit["market_rent_sqm"])

    # Basis-Schätzung nach Region
    address = (unit.get("address") or "").lower()
    city = extract_city(address)

    # Regionale Basis-Mieten (grobe Schätzung, sollte durch echte Mietspiegel ersetzt werden)
    base_rents = {
        "bremen": 8.50,
        "magdeburg": 6.20, "md": 6.20,
        "eilsleben": 5.00,
        "seehausen": 4.80,
    }

    base = 6.00  # Default
    for key, rent in base_rents.items():
        if key in city or key in address:
            base = rent
            break

    # Baujahr-Anpassung
    year = int(unit.get("year") or 1970)
    if year >= 2010:
        base *= 1.15
    elif year >= 2000:
        base *= 1.05
    elif year >= 1990:
        base *= 1.00
    elif year >= 1970:
        base *= 0.92
    elif year >= 1950:
        base *= 0.88
    else:
        base *= 0.85  # Altbau (kann auch Premium sein)

    # Zustand
    condition = unit.get("condition") or "normal"
    base *= CONDITION_FACTORS.get(condition, 1.0)

    # Ausstattung
    features = unit.get("features") or []
    for f in features:
        base += FEATURES_PREMIUM.get(f, 0)

    # Wohnfläche (kleine Wohnungen haben höheren m²-Preis)
    sqm = float(unit.get("sqm") or 60)
    if sqm < 40:
        base *= 1.10
    elif sqm > 100:
        base *= 0.95

    return round(base, 2)


def extract_city(address):
    """Extrahiert den Stadtnamen aus der Adresse."""
    address = address.lower().strip()
    # Format: "PLZ Stadt, Straße..." oder "PLZ Stadt Straße..."
    parts = address.replace(",", " ").split()
    for i, p in enumerate(parts):
        if p.isdigit() and len(p) == 5 and i + 1 < len(parts):
            return parts[i + 1]
    return address.split(",")[0] if "," in address else address.split()[0] if address else ""


def calculate_kappungsgrenze(unit, current_rent, years=3):
    """Berechnet die maximale Erhöhung nach Kappungsgrenze (§ 558 Abs. 3 BGB).

    - Normalerweise max. 20% in 3 Jahren
    - In angespannten Märkten max. 15% in 3 Jahren
    """
    address = (unit.get("address") or "").lower()
    city = extract_city(address)

    is_tight = any(t in city or t in address for t in TIGHT_MARKETS)
    cap_percent = 15 if is_tight else 20

    # Alle Erhöhungen der letzten 3 Jahre berechnen
    history = unit.get("history") or []
    three_years_ago = date.today() - relativedelta(years=3)
    increases_3y = []

    for h in history:
        try:
            h_date = datetime.strptime(h["date"], "%Y-%m-%d").date()
            if h_date >= three_years_ago:
                increases_3y.append(h)
        except (ValueError, KeyError):
            pass

    # Basis: Miete vor 3 Jahren (oder älteste bekannte Miete)
    if increases_3y:
        base_rent_3y = increases_3y[0].get("old_rent", current_rent)
    else:
        base_rent_3y = current_rent

    max_increase_total = base_rent_3y * (cap_percent / 100)
    already_increased = current_rent - base_rent_3y
    remaining_cap = max(0, max_increase_total - already_increased)

    return {
        "cap_percent": cap_percent,
        "is_tight_market": is_tight,
        "base_rent_3y": base_rent_3y,
        "max_increase_total": round(max_increase_total, 2),
        "already_increased": round(already_increased, 2),
        "remaining_cap": round(remaining_cap, 2),
        "max_new_rent": round(current_rent + remaining_cap, 2),
    }


def calculate_legal_max(unit):
    """Berechnet die maximale rechtlich zulässige Miete.

    Berücksichtigt: Vertragstyp, Kappungsgrenze, Mietspiegel.
    """
    contract = unit.get("contract_type") or "standard"
    current_rent = float(unit.get("rent") or 0)
    sqm = float(unit.get("sqm") or 1)
    market_sqm = estimate_market_rent(unit)
    market_total = market_sqm * sqm

    if contract == "index":
        # Indexmiete: Erhöhung nach VPI, kein Mietspiegel-Limit
        return {
            "type": "index",
            "note": "Indexmiete — Erhöhung nach Verbraucherpreisindex. Kein Mietspiegel-Limit.",
            "market_sqm": market_sqm,
            "market_total": round(market_total, 2),
            "legal_max": None,  # Hängt vom VPI ab
        }

    if contract == "staffel":
        return {
            "type": "staffel",
            "note": "Staffelmiete — Erhöhungen sind im Vertrag festgelegt. Keine weitere Erhöhung möglich.",
            "market_sqm": market_sqm,
            "market_total": round(market_total, 2),
            "legal_max": None,
        }

    if contract == "sozial":
        return {
            "type": "sozial",
            "note": "Sozialbindung — Miete ist durch Förderbedingungen begrenzt.",
            "market_sqm": market_sqm,
            "market_total": round(market_total, 2),
            "legal_max": None,
        }

    if contract == "frei":
        return {
            "type": "frei",
            "note": "Freie Vereinbarung — keine gesetzlichen Grenzen (z.B. Gewerbe, möbliert).",
            "market_sqm": market_sqm,
            "market_total": round(market_total, 2),
            "legal_max": market_total,
        }

    # Standard-Mietvertrag
    kappung = calculate_kappungsgrenze(unit, current_rent)

    # Limit 1: Ortsübliche Vergleichsmiete
    limit_mietspiegel = market_total

    # Limit 2: Kappungsgrenze
    limit_kappung = kappung["max_new_rent"]

    # Das niedrigere Limit gilt
    legal_max = min(limit_mietspiegel, limit_kappung)

    # Kann nicht unter aktuelle Miete fallen
    legal_max = max(legal_max, current_rent)

    return {
        "type": "standard",
        "market_sqm": market_sqm,
        "market_total": round(market_total, 2),
        "legal_max": round(legal_max, 2),
        "kappung": kappung,
        "limit_mietspiegel": round(limit_mietspiegel, 2),
        "limit_kappung": round(limit_kappung, 2),
        "binding_limit": "mietspiegel" if limit_mietspiegel < limit_kappung else "kappungsgrenze",
    }


def generate_recommendation(unit):
    """Generiert eine konkrete Empfehlung für eine Wohneinheit.

    Returns dict mit:
    - priority: 1-5 (1 = sofort handeln)
    - action: "increase" | "wait" | "hold" | "review"
    - recommended_rent: vorgeschlagene neue Miete
    - recommended_sqm: vorgeschlagene €/m²
    - reasoning: Begründung
    - timing: Wann handeln
    - risk_level: "low" | "medium" | "high"
    - potential_annual: jährliches Mehreinkommen
    """
    today = date.today()
    current_rent = float(unit.get("rent") or 0)
    sqm = float(unit.get("sqm") or 1)
    current_sqm = current_rent / sqm if sqm > 0 else 0
    contract = unit.get("contract_type") or "standard"

    # Sonderfälle
    if contract == "staffel":
        ms = estimate_market_rent(unit)
        return {
            "priority": 5,
            "action": "hold",
            "recommended_rent": current_rent,
            "recommended_sqm": current_sqm,
            "reasoning": "Staffelmietvertrag — Erhöhungen sind vertraglich festgelegt. Nächste Stufe prüfen.",
            "timing": "Automatisch laut Vertrag",
            "risk_level": "low",
            "potential_annual": 0,
            "market_sqm": ms,
            "market_total": round(ms * sqm, 2),
        }

    if contract == "sozial":
        ms = estimate_market_rent(unit)
        return {
            "priority": 5,
            "action": "hold",
            "recommended_rent": current_rent,
            "recommended_sqm": current_sqm,
            "reasoning": "Sozialbindung — keine freie Mieterhöhung möglich.",
            "timing": "Nach Auslaufen der Bindung prüfen",
            "risk_level": "low",
            "potential_annual": 0,
            "market_sqm": ms,
            "market_total": round(ms * sqm, 2),
        }

    if current_rent == 0:
        ms = estimate_market_rent(unit)
        return {
            "priority": 3,
            "action": "review",
            "recommended_rent": 0,
            "recommended_sqm": 0,
            "reasoning": "Keine Miete hinterlegt — bitte Daten vervollständigen.",
            "timing": "Jetzt",
            "risk_level": "low",
            "potential_annual": 0,
            "market_sqm": ms,
            "market_total": round(ms * sqm, 2),
        }

    legal = calculate_legal_max(unit)
    market_sqm = legal["market_sqm"]
    market_total = legal["market_total"]

    # Differenz zur Marktmiete
    gap_percent = ((market_total - current_rent) / current_rent * 100) if current_rent > 0 else 0
    gap_absolute = market_total - current_rent

    # Timing prüfen
    ref_date = None
    if unit.get("last_increase"):
        try:
            ref_date = datetime.strptime(unit["last_increase"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    if unit.get("rented_since"):
        try:
            rd = datetime.strptime(unit["rented_since"], "%Y-%m-%d").date()
            if ref_date is None or rd > ref_date:
                ref_date = rd
        except (ValueError, TypeError):
            pass

    # Individuelle Sperrfrist
    interval = int(unit.get("custom_interval") or 15)
    can_increase_from = ref_date + relativedelta(months=interval) if ref_date else today

    months_until = (can_increase_from.year - today.year) * 12 + (can_increase_from.month - today.month)
    can_increase_now = can_increase_from <= today

    # Mieter-Kontext
    tenant_quality = unit.get("tenant_quality") or "normal"
    tenant_factor = {
        "top": 0.7,       # Top-Mieter: vorsichtiger erhöhen
        "gut": 0.85,
        "normal": 1.0,
        "schwierig": 1.0,  # Schwierige Mieter: trotzdem Markt anpassen
        "kuendigung_erwaegen": 1.0,
    }.get(tenant_quality, 1.0)

    # ─── Empfehlung berechnen ───

    if gap_percent <= 2:
        # Miete ist nahe am Markt
        return {
            "priority": 5,
            "action": "hold",
            "recommended_rent": current_rent,
            "recommended_sqm": current_sqm,
            "reasoning": f"Miete ist mit {current_sqm:.2f}€/m² nah am Marktniveau ({market_sqm:.2f}€/m²). Keine Erhöhung nötig.",
            "timing": f"Nächste Prüfung in 12 Monaten",
            "risk_level": "low",
            "potential_annual": 0,
            "market_sqm": market_sqm,
            "market_total": market_total,
        }

    # Es gibt Erhöhungspotenzial
    if contract == "frei":
        # Keine gesetzlichen Grenzen
        target_rent = market_total
        target_sqm = market_sqm
    else:
        # Standard: Limit durch Mietspiegel + Kappungsgrenze
        legal_max = legal.get("legal_max") or market_total

        # Empfohlene Erhöhung: Nicht volle Ausschöpfung, sondern strategisch
        if gap_percent > 30:
            # Große Lücke: In Schritten erhöhen
            step_factor = 0.6 * tenant_factor  # 60% der Lücke schließen
            target_rent = current_rent + (gap_absolute * step_factor)
        elif gap_percent > 15:
            step_factor = 0.75 * tenant_factor
            target_rent = current_rent + (gap_absolute * step_factor)
        else:
            step_factor = 0.9 * tenant_factor
            target_rent = current_rent + (gap_absolute * step_factor)

        # Legal-Limit beachten
        target_rent = min(target_rent, legal_max)
        target_sqm = target_rent / sqm if sqm > 0 else 0

    # Auf volle Euro runden (praxisnah)
    target_rent = math.ceil(target_rent)
    target_sqm = target_rent / sqm if sqm > 0 else 0

    increase_amount = target_rent - current_rent
    increase_percent = (increase_amount / current_rent * 100) if current_rent > 0 else 0
    potential_annual = increase_amount * 12

    # Priority & Timing
    if can_increase_now and gap_percent > 15:
        priority = 1
        timing = "Jetzt — Mieterhöhungsverlangen vorbereiten"
    elif can_increase_now and gap_percent > 5:
        priority = 2
        timing = "Zeitnah — innerhalb der nächsten 4 Wochen"
    elif months_until <= 3:
        priority = 2
        timing = f"Vorbereiten — Erhöhung ab {can_increase_from.strftime('%d.%m.%Y')} möglich"
    elif months_until <= 6:
        priority = 3
        timing = f"Vormerken — ab {can_increase_from.strftime('%d.%m.%Y')} möglich"
    else:
        priority = 4
        timing = f"Warten — frühestens ab {can_increase_from.strftime('%d.%m.%Y')}"

    # Risk Level
    if increase_percent > 15:
        risk_level = "high"
    elif increase_percent > 8:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Reasoning
    reasons = []
    reasons.append(f"Aktuelle Miete: {current_rent:.0f}€ ({current_sqm:.2f}€/m²)")
    reasons.append(f"Marktmiete geschätzt: {market_total:.0f}€ ({market_sqm:.2f}€/m²)")
    reasons.append(f"Potenzial: +{gap_percent:.0f}% / +{gap_absolute:.0f}€ pro Monat")

    if legal.get("type") == "standard" and legal.get("kappung"):
        k = legal["kappung"]
        reasons.append(f"Kappungsgrenze ({k['cap_percent']}% in 3J): max. {k['max_new_rent']:.0f}€")
        if k["remaining_cap"] < increase_amount:
            reasons.append(f"⚠️ Kappungsgrenze limitiert auf +{k['remaining_cap']:.0f}€")

    if tenant_quality == "top":
        reasons.append("Moderat erhöht wegen Top-Mieter (Fluktuation vermeiden)")
    elif tenant_quality == "schwierig":
        reasons.append("Volle Erhöhung empfohlen — Mieter-Situation berücksichtigen")

    return {
        "priority": priority,
        "action": "increase" if can_increase_now else "wait",
        "recommended_rent": target_rent,
        "recommended_sqm": round(target_sqm, 2),
        "increase_amount": round(increase_amount, 2),
        "increase_percent": round(increase_percent, 1),
        "reasoning": "\n".join(reasons),
        "timing": timing,
        "risk_level": risk_level,
        "potential_annual": round(potential_annual, 2),
        "market_sqm": market_sqm,
        "market_total": round(market_total, 2),
        "legal": legal,
        "can_increase_now": can_increase_now,
        "can_increase_from": can_increase_from.isoformat() if can_increase_from else None,
    }


def generate_portfolio_summary(units):
    """Generiert eine Portfolio-Gesamtanalyse."""
    recommendations = []
    for unit in units:
        rec = generate_recommendation(unit)
        rec["unit"] = unit
        recommendations.append(rec)

    total_current = sum(float(u.get("rent") or 0) for u in units)
    total_potential = sum(r["recommended_rent"] for r in recommendations if r["action"] == "increase")
    total_current_actionable = sum(float(r["unit"].get("rent") or 0) for r in recommendations if r["action"] == "increase")

    annual_potential = sum(r["potential_annual"] for r in recommendations)
    actionable_now = [r for r in recommendations if r["action"] == "increase"]
    priority_1 = [r for r in recommendations if r["priority"] == 1]

    return {
        "recommendations": sorted(recommendations, key=lambda r: r["priority"]),
        "total_current_rent": round(total_current, 2),
        "total_potential_increase": round(total_potential - total_current_actionable, 2),
        "annual_potential": round(annual_potential, 2),
        "actionable_now": len(actionable_now),
        "priority_1_count": len(priority_1),
        "total_units": len(units),
    }
