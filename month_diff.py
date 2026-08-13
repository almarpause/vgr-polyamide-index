"""Polyamide Index — month-over-month change detection.

Compares this month's snapshot against the previous month across every input:
retail price, FX-driven EUR value, rank, margin, and each cost component (duty,
freight, VAT). Separates real market moves (price/FX) from assumption changes
(duty/freight/VAT config). Feeds the executive report.
"""
from __future__ import annotations


def _round(x, n=2):
    return round(x, n) if isinstance(x, (int, float)) else x


def diff(current: dict, prior: dict | None) -> dict:
    """Structured month diff. If prior is None, returns a baseline marker."""
    cur_c = {c["cc"]: c for c in current["countries"]}
    if not prior:
        dearest = current["meta"]["dearest"]; cheapest = current["meta"]["cheapest"]
        return {
            "baseline": True,
            "cur_date": current["meta"]["run_date"], "prior_date": None,
            "meta": current["meta"], "winner": dearest, "cheapest": cheapest,
            "movers_up": [], "movers_down": [], "cost_changes": [],
            "new_below_cost": [c["name"] for c in current["countries"] if (c.get("stack") or {}).get("below_cost")],
        }

    pri_c = {c["cc"]: c for c in prior["countries"]}
    both = [cc for cc in cur_c if cc in pri_c]

    rows = []
    for cc in both:
        a, b = cur_c[cc], pri_c[cc]
        sa, sb = a.get("stack") or {}, b.get("stack") or {}
        rows.append({
            "cc": cc, "name": a["name"], "region": a["region"],
            "value": a["value"], "d_value": _round(a["value"] - b["value"]),
            "d_value_pct": _round((a["value"] / b["value"] - 1) * 100, 1) if b["value"] else None,
            "d_price_local": _round(a["price_local"] - b["price_local"]),
            "rank": a["rank"], "prior_rank": b["rank"], "d_rank": b["rank"] - a["rank"],  # +ve = moved up (dearer)
            "margin": sa.get("margin"), "d_margin": _round((sa.get("margin") or 0) - (sb.get("margin") or 0)),
            "d_duty": _round((sa.get("duty") or 0) - (sb.get("duty") or 0)),
            "d_freight": _round((sa.get("freight") or 0) - (sb.get("freight") or 0)),
            "d_vat": _round((sa.get("vat") or 0) - (sb.get("vat") or 0)),
            "d_duty_pct": _round((sa.get("duty_pct") or 0) - (sb.get("duty_pct") or 0), 1),
            "d_vat_pct": _round((sa.get("vat_pct") or 0) - (sb.get("vat_pct") or 0), 1),
            "d_freight_in": _round((sa.get("freight") or 0) - (sb.get("freight") or 0), 3),
            "below_cost": bool(sa.get("below_cost")),
            "was_below_cost": bool(sb.get("below_cost")),
        })

    by_gain = sorted(rows, key=lambda r: (r["d_value"] if r["d_value"] is not None else 0), reverse=True)
    movers_up = [r for r in sorted(rows, key=lambda r: r["d_rank"], reverse=True) if r["d_rank"] > 0][:6]
    movers_down = [r for r in sorted(rows, key=lambda r: r["d_rank"]) if r["d_rank"] < 0][:6]

    top_band = [r for r in rows if r["rank"] <= 15 or r["prior_rank"] <= 15]
    mid_band = [r for r in rows if 15 < r["rank"] <= 45]
    top_movers = sorted([r for r in top_band if r["d_rank"] != 0], key=lambda r: abs(r["d_rank"]), reverse=True)[:5]
    mid_movers = sorted([r for r in mid_band if r["d_rank"] != 0], key=lambda r: abs(r["d_rank"]), reverse=True)[:5]

    cost_changes = [r for r in rows if abs(r["d_duty_pct"] or 0) > 0.01 or abs(r["d_vat_pct"] or 0) > 0.01
                    or abs(r["d_freight_in"] or 0) > 0.005]

    cm, pm = current["meta"], prior["meta"]
    return {
        "baseline": False,
        "cur_date": cm["run_date"], "prior_date": pm["run_date"],
        "meta": cm, "prior_meta": pm,
        "winner": cm["dearest"], "cheapest": cm["cheapest"],
        "d_avg": _round(cm["avg"] - pm["avg"]),
        "d_spread": _round((cm["max"] / cm["min"]) - (pm["max"] / pm["min"]), 2),
        "biggest_gain": by_gain[0] if by_gain else None,
        "biggest_drop": by_gain[-1] if by_gain else None,
        "movers_up": movers_up, "movers_down": movers_down,
        "top_movers": top_movers, "mid_movers": mid_movers,
        "cost_changes": cost_changes,
        "new_below_cost": [r["name"] for r in rows if r["below_cost"] and not r["was_below_cost"]],
        "recovered": [r["name"] for r in rows if r["was_below_cost"] and not r["below_cost"]],
        "n_common": len(both),
    }
