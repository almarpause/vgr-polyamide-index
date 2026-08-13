"""Polyamide Index — monthly historisation.

Each monthly run archives the full snapshot to history/<run_date>.json and appends
the per-country rows to history/monthly.csv, so month-over-month change detection
and the trend report have a persistent, append-only record. Idempotent per date.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import common

HISTORY_DIR = common.ROOT / "history"

CSV_COLS = ["run_date", "cc", "name", "region", "currency", "price_local", "value_eur",
            "rank", "vs_base_pct", "vs_ref_pct", "dc", "freight", "duty", "other",
            "margin", "vat", "duty_pct", "vat_pct", "below_cost"]


def record(data: dict) -> str:
    """Archive one run. Returns the snapshot path."""
    HISTORY_DIR.mkdir(exist_ok=True)
    run_date = data["meta"]["run_date"]
    snap = HISTORY_DIR / f"{run_date}.json"
    snap.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_csv(data)
    return str(snap)


def _append_csv(data: dict) -> None:
    run_date = data["meta"]["run_date"]
    csv_path = HISTORY_DIR / "monthly.csv"
    existing = []
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", newline="") as f:
            existing = [r for r in csv.DictReader(f) if r.get("run_date") != run_date]
    rows = existing
    for c in data["countries"]:
        s = c.get("stack") or {}
        rows.append({
            "run_date": run_date, "cc": c["cc"], "name": c["name"], "region": c["region"],
            "currency": c["currency"], "price_local": c["price_local"], "value_eur": c["value"],
            "rank": c["rank"], "vs_base_pct": c.get("vs_base_pct"), "vs_ref_pct": c.get("vs_ref_pct"),
            "dc": s.get("dc"), "freight": s.get("freight"), "duty": s.get("duty"),
            "other": s.get("other"), "margin": s.get("margin"), "vat": s.get("vat"),
            "duty_pct": s.get("duty_pct"), "vat_pct": s.get("vat_pct"),
            "below_cost": int(bool(s.get("below_cost"))),
        })
    rows.sort(key=lambda r: (r["run_date"], r["cc"]))
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader(); w.writerows(rows)


def snapshot_dates() -> list[str]:
    if not HISTORY_DIR.exists():
        return []
    return sorted(p.stem for p in HISTORY_DIR.glob("*.json"))


def load(run_date: str) -> dict:
    return json.loads((HISTORY_DIR / f"{run_date}.json").read_text(encoding="utf-8"))


def latest_two() -> tuple[dict | None, dict | None]:
    """(current, prior) full snapshots, or (current, None) / (None, None)."""
    dates = snapshot_dates()
    cur = load(dates[-1]) if dates else None
    prior = load(dates[-2]) if len(dates) >= 2 else None
    return cur, prior
