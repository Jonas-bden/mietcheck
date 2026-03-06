#!/usr/bin/env python3
"""MietCheck — Mieterhöhungs-Erinnerungssystem mit AI-Advisor.

Production-ready Version mit Login-Schutz und Environment-Config.
"""
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from functools import wraps
import json
import os
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from advisor import (
    generate_recommendation, generate_portfolio_summary, estimate_market_rent,
    calculate_legal_max, CONTRACT_TYPES, CONDITION_LABELS, FEATURES_PREMIUM,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mietcheck-dev-key-change-me")

# ─── Config ───
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(DATA_DIR, "data.json")
INCREASE_INTERVAL_MONTHS = 15

# Login-Schutz (einfach aber effektiv)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "mietcheck2026")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username", "")
        pw = request.form.get("password", "")
        if user == ADMIN_USER and pw == ADMIN_PASS:
            session["logged_in"] = True
            session.permanent = True
            next_url = request.args.get("next", url_for("dashboard"))
            return redirect(next_url)
        flash("Falsches Passwort.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Data ───

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"units": [], "settings": {"reminder_months": 3, "increase_interval": 15}}


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def calculate_status(unit):
    today = date.today()
    ref_date = None
    ref_type = None

    if unit.get("last_increase"):
        try:
            ref_date = datetime.strptime(unit["last_increase"], "%Y-%m-%d").date()
            ref_type = "increase"
        except (ValueError, TypeError):
            pass

    if unit.get("rented_since"):
        try:
            rent_date = datetime.strptime(unit["rented_since"], "%Y-%m-%d").date()
            if ref_date is None or rent_date > ref_date:
                ref_date = rent_date
                ref_type = "rental"
        except (ValueError, TypeError):
            pass

    if unit.get("increase_from"):
        try:
            inc_from = datetime.strptime(unit["increase_from"], "%Y-%m-%d").date()
            return {
                "next_possible": inc_from.isoformat(),
                "next_possible_formatted": inc_from.strftime("%d.%m.%Y"),
                "days_until": (inc_from - today).days,
                "status": _status_label(inc_from, today),
                "status_color": _status_color(inc_from, today),
                "ref_type": "planned",
            }
        except (ValueError, TypeError):
            pass

    if ref_date is None:
        return {"next_possible": None, "status": "Kein Datum", "status_color": "gray", "days_until": None, "ref_type": None}

    interval = int(unit.get("custom_interval") or INCREASE_INTERVAL_MONTHS)
    next_possible = ref_date + relativedelta(months=interval)
    days_until = (next_possible - today).days

    return {
        "next_possible": next_possible.isoformat(),
        "next_possible_formatted": next_possible.strftime("%d.%m.%Y"),
        "days_until": days_until,
        "status": _status_label(next_possible, today),
        "status_color": _status_color(next_possible, today),
        "ref_type": ref_type,
    }


def _status_label(next_date, today):
    d = (next_date - today).days
    if d < 0: return "Überfällig"
    elif d <= 30: return "Jetzt erhöhen"
    elif d <= 90: return "Bald fällig"
    elif d <= 180: return "Vormerken"
    return "OK"


def _status_color(next_date, today):
    d = (next_date - today).days
    if d < 0: return "red"
    elif d <= 30: return "orange"
    elif d <= 90: return "yellow"
    elif d <= 180: return "blue"
    return "green"


# ─── Routes ───

@app.route("/")
@login_required
def dashboard():
    data = load_data()
    units = data.get("units", [])

    for unit in units:
        unit["calc"] = calculate_status(unit)
        unit["advisor"] = generate_recommendation(unit)

    summary = generate_portfolio_summary(units)

    def sort_key(u):
        d = u["calc"].get("days_until")
        return d if d is not None else 99999

    units.sort(key=sort_key)

    total_rent = sum(u.get("rent", 0) for u in units)
    overdue = sum(1 for u in units if u["calc"]["status_color"] == "red")
    upcoming = sum(1 for u in units if u["calc"]["status_color"] in ("orange", "yellow"))
    ok_count = sum(1 for u in units if u["calc"]["status_color"] in ("green", "blue"))

    return render_template(
        "dashboard.html",
        units=units,
        summary=summary,
        total_rent=total_rent,
        overdue=overdue,
        upcoming=upcoming,
        ok_count=ok_count,
        today=date.today().strftime("%d.%m.%Y"),
    )


@app.route("/unit/<int:idx>")
@login_required
def unit_detail(idx):
    data = load_data()
    units = data.get("units", [])
    if idx < 0 or idx >= len(units):
        return redirect(url_for("dashboard"))
    unit = units[idx]
    unit["calc"] = calculate_status(unit)

    rec = generate_recommendation(unit)
    legal = calculate_legal_max(unit)
    market_sqm = estimate_market_rent(unit)

    return render_template(
        "detail.html", unit=unit, idx=idx,
        history=unit.get("history", []),
        rec=rec, legal=legal, market_sqm=market_sqm,
        contract_types=CONTRACT_TYPES,
        condition_labels=CONDITION_LABELS,
    )


@app.route("/unit/<int:idx>/edit", methods=["GET", "POST"])
@login_required
def unit_edit(idx):
    data = load_data()
    units = data.get("units", [])
    if idx < 0 or idx >= len(units):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        unit = units[idx]
        unit["address"] = request.form.get("address", unit.get("address", ""))
        unit["tenant"] = request.form.get("tenant", unit.get("tenant", ""))
        unit["sqm"] = float(request.form.get("sqm", 0) or 0)
        unit["rent"] = float(request.form.get("rent", 0) or 0)
        unit["parking"] = request.form.get("parking", "")
        unit["year"] = request.form.get("year", "")
        unit["mea"] = request.form.get("mea", "")
        unit["last_increase"] = request.form.get("last_increase", "") or None
        unit["rented_since"] = request.form.get("rented_since", "") or None
        unit["increase_from"] = request.form.get("increase_from", "") or None
        unit["increase_note"] = request.form.get("increase_note", "")
        unit["notes"] = request.form.get("notes", "")
        unit["contract_type"] = request.form.get("contract_type", "standard")
        unit["condition"] = request.form.get("condition", "normal")
        unit["custom_interval"] = int(request.form.get("custom_interval", 15) or 15)
        unit["market_rent_sqm"] = float(request.form.get("market_rent_sqm", 0) or 0)
        unit["tenant_quality"] = request.form.get("tenant_quality", "normal")
        unit["tenant_notes"] = request.form.get("tenant_notes", "")
        unit["features"] = request.form.getlist("features")
        unit["renovation_year"] = request.form.get("renovation_year", "")
        unit["special_rules"] = request.form.get("special_rules", "")
        save_data(data)
        flash("Wohnung aktualisiert.", "success")
        return redirect(url_for("unit_detail", idx=idx))

    unit = units[idx]
    return render_template(
        "edit.html", unit=unit, idx=idx,
        contract_types=CONTRACT_TYPES,
        condition_labels=CONDITION_LABELS,
        features_list=FEATURES_PREMIUM,
    )


@app.route("/unit/<int:idx>/increase", methods=["POST"])
@login_required
def record_increase(idx):
    data = load_data()
    units = data.get("units", [])
    if idx < 0 or idx >= len(units):
        return redirect(url_for("dashboard"))

    unit = units[idx]
    new_rent = float(request.form.get("new_rent", 0) or 0)
    increase_date = request.form.get("increase_date", date.today().isoformat())
    note = request.form.get("note", "")

    if "history" not in unit:
        unit["history"] = []
    unit["history"].append({
        "date": increase_date,
        "old_rent": unit.get("rent", 0),
        "new_rent": new_rent,
        "note": note,
    })

    unit["rent"] = new_rent
    unit["last_increase"] = increase_date
    unit["increase_from"] = None
    unit["increase_note"] = ""
    save_data(data)
    flash(f"Mieterhöhung auf {new_rent:.2f}€ eingetragen.", "success")
    return redirect(url_for("unit_detail", idx=idx))


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_unit():
    if request.method == "POST":
        data = load_data()
        unit = {
            "address": request.form.get("address", ""),
            "tenant": request.form.get("tenant", ""),
            "sqm": float(request.form.get("sqm", 0) or 0),
            "rent": float(request.form.get("rent", 0) or 0),
            "parking": request.form.get("parking", ""),
            "year": request.form.get("year", ""),
            "mea": request.form.get("mea", ""),
            "last_increase": request.form.get("last_increase", "") or None,
            "rented_since": request.form.get("rented_since", "") or None,
            "increase_from": request.form.get("increase_from", "") or None,
            "increase_note": request.form.get("increase_note", ""),
            "contract_type": request.form.get("contract_type", "standard"),
            "condition": request.form.get("condition", "normal"),
            "custom_interval": int(request.form.get("custom_interval", 15) or 15),
            "market_rent_sqm": float(request.form.get("market_rent_sqm", 0) or 0),
            "tenant_quality": request.form.get("tenant_quality", "normal"),
            "tenant_notes": "",
            "features": request.form.getlist("features"),
            "renovation_year": request.form.get("renovation_year", ""),
            "special_rules": "",
            "notes": "",
            "history": [],
        }
        data["units"].append(unit)
        save_data(data)
        flash("Wohnung hinzugefügt.", "success")
        return redirect(url_for("dashboard"))
    return render_template(
        "edit.html", unit={}, idx=None,
        contract_types=CONTRACT_TYPES,
        condition_labels=CONDITION_LABELS,
        features_list=FEATURES_PREMIUM,
    )


@app.route("/unit/<int:idx>/delete", methods=["POST"])
@login_required
def delete_unit(idx):
    data = load_data()
    units = data.get("units", [])
    if 0 <= idx < len(units):
        removed = units.pop(idx)
        save_data(data)
        flash(f"'{removed.get('address', 'Wohnung')}' gelöscht.", "info")
    return redirect(url_for("dashboard"))


@app.route("/api/calendar")
@login_required
def api_calendar():
    data = load_data()
    events = []
    colors = {"red": "#ef4444", "orange": "#f97316", "yellow": "#eab308", "blue": "#3b82f6", "green": "#22c55e", "gray": "#9ca3af"}
    for unit in data.get("units", []):
        calc = calculate_status(unit)
        if calc.get("next_possible"):
            events.append({
                "title": f"{unit.get('address', '?').split(' - ')[-1]} — {unit.get('tenant', '?')}",
                "start": calc["next_possible"],
                "color": colors.get(calc["status_color"], "#6b7280"),
                "extendedProps": {"status": calc["status"], "rent": unit.get("rent", 0), "address": unit.get("address", "")},
            })
    return jsonify(events)


@app.route("/advisor")
@login_required
def advisor_overview():
    data = load_data()
    units = data.get("units", [])
    summary = generate_portfolio_summary(units)
    return render_template("advisor.html", summary=summary, today=date.today().strftime("%d.%m.%Y"))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "units": len(load_data().get("units", []))})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("DEBUG", "false").lower() == "true")
