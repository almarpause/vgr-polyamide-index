"""Polyamide Index — monthly executive report (.docx).

Renders a short Economist-Word-style report per monthly run: a VGR cover, an
executive summary in VGR's voice (who wins and how it grew; who moved in the top
and the middle vs last month), and Economist ledger tables of the movers and any
cost/tariff changes. The prose comes from the Anthropic API when ANTHROPIC_API_KEY
is set (full VGR voice); otherwise from an override file or a factual fallback.

    python monthly_report.py                 # from output/latest.json + history/
    python monthly_report.py --run-date 2026-08-10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import common
import history
import month_diff

sys.path.insert(0, str(common.ROOT / "report"))
import economist_navy as en  # noqa: E402

LOGO = common.ROOT / "web" / "vgr-logo-black.png"
REPORT_MODEL = os.environ.get("PI_REPORT_MODEL", "claude-sonnet-5")


def money(x):
    return f"€{x:.2f}" if isinstance(x, (int, float)) else "—"


def signed(x, unit=""):
    if x is None:
        return "—"
    return f"{'+' if x >= 0 else '−'}{abs(x):.2f}{unit}"


def month_label(run_date: str) -> str:
    from datetime import date
    y, m, d = (int(v) for v in run_date.split("-"))
    return date(y, m, d).strftime("%B %Y")


# --------------------------------------------------------------- exec summary
VGR_SYSTEM = """You write the executive summary of a monthly retail-price index for VGR — Pau Almar's
fashion advisory. Voice: an operator who ran Zara's commercial machine, reading the inside from the
outside. Lead with the finding (pyramid). Specific facts, named markets, exact figures. Peer-to-peer,
never salesy. Compression: one line the reader could repeat in a board meeting.
FORBIDDEN (AI markers): fragmented sentences punched for effect; triple parallel lists; "what makes
this different" pivots; ending on "the question is…"; abstract nouns (structural/architectural/systemic)
standing in for a specific mechanism; "this is not X, it's Y" contrastive declarations; exclamation
marks; the words best-practices, leverage, synergies, holistic, robust, landscape, comprehensive.
Sentence case. 2–3 short paragraphs, ~140 words total. No heading, no bullet list, prose only."""


def exec_summary(d: dict) -> list[str]:
    override = history.HISTORY_DIR / f"summary_{d['cur_date']}.txt"
    if override.exists():
        return [p.strip() for p in override.read_text(encoding="utf-8").split("\n\n") if p.strip()]
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _summary_via_api(d)
        except Exception as e:  # noqa: BLE001
            print(f"[report] API summary failed ({type(e).__name__}: {e}); using fallback")
    return _summary_fallback(d)


def _summary_via_api(d: dict) -> list[str]:
    import anthropic
    facts = {k: d.get(k) for k in ("baseline", "cur_date", "prior_date", "winner", "cheapest",
                                   "d_avg", "d_spread", "biggest_gain", "biggest_drop",
                                   "top_movers", "mid_movers", "cost_changes", "new_below_cost", "recovered")}
    facts["product"] = "Zara fine-strap polyamide t-shirt (made in Turkey), priced across 65 markets in EUR, anchored to Spain."
    prompt = ("Write the executive summary for the Zara Polyamide Index, month "
              f"{month_label(d['cur_date'])}. Cover: who wins (the dearest / highest-margin market) and how it "
              "grew versus last month; who moved in the TOP of the ranking and who moved in the MIDDLE; and any "
              "duty/tariff or price change worth flagging. Facts as JSON:\n\n" + json.dumps(facts, ensure_ascii=False))
    client = anthropic.Anthropic()
    msg = client.messages.create(model=REPORT_MODEL, max_tokens=600, system=VGR_SYSTEM,
                                 messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _summary_fallback(d: dict) -> list[str]:
    m = d["meta"]; w = d["winner"]
    if d["baseline"]:
        return [
            f"This is the first reading of the Zara Polyamide Index. One identical t-shirt, made in Turkey, "
            f"priced across {m['n_countries']} markets in euros and anchored to Spain at {money(m['base_value'])}.",
            f"{w['name']} tops the table at {money(w['usd'] if 'usd' in w else w['value'])}, against a world average of "
            f"{money(m['avg'])} and a floor of {money(m['cheapest']['value'])} in {m['cheapest']['name']} — a "
            f"{m['max']/m['min']:.1f}× spread on the same garment. Next month begins the comparison.",
        ]
    paras = []
    grow = f", {signed(d['d_avg'],' €')} on the world average" if d.get("d_avg") is not None else ""
    paras.append(f"{w['name']} again leads the index at {money(w['value'])}{grow}. The spread across "
                 f"{m['n_countries']} markets is {m['max']/m['min']:.1f}×{(' (' + signed(d['d_spread']) + ' vs last month)') if d.get('d_spread') is not None else ''}.")
    if d.get("top_movers"):
        tm = "; ".join(f"{r['name']} {signed(r['d_rank'])[0]}{abs(r['d_rank'])}" for r in d["top_movers"][:3])
        paras.append(f"In the top of the table, {tm} moved on rank versus last month.")
    if d.get("mid_movers"):
        mm = "; ".join(f"{r['name']} {signed(r['d_rank'])[0]}{abs(r['d_rank'])}" for r in d["mid_movers"][:3])
        paras.append(f"In the middle, {mm}.")
    if d.get("cost_changes"):
        cc = "; ".join(f"{r['name']} duty {signed(r['d_duty_pct'],'pp')}" for r in d["cost_changes"][:3] if r.get("d_duty_pct"))
        if cc:
            paras.append(f"Tariff changes fed through in {cc}.")
    return paras or ["No material change versus last month."]


# ------------------------------------------------------------------- render
def build(data: dict, d: dict) -> str:
    doc = en.new_document(short_title="VGR · Zara Polyamide Index")
    m = data["meta"]

    if LOGO.exists():
        en.figure(doc, str(LOGO), width_in=0.55)
    en.cover_masthead(doc, "VGR INDEX")
    en.h1(doc, "The Zara Polyamide Index", deck=f"One t-shirt, {m['n_countries']} markets — {month_label(d['cur_date'])}")
    en.source_line(doc, f"Made in Turkey · HS 6109.90 · anchored to Spain {money(m['base_value'])} · "
                        f"snapshot {m['run_date']} · spot FX {m['fx_asof']}")
    en.stripe_band(doc)

    w = d["winner"]
    ruling = (f"{w['name']} is the dearest market on earth for this garment, at {money(w['value'])} — "
              f"{m['max']/m['min']:.1f} times the {money(m['cheapest']['value'])} it costs in {m['cheapest']['name']}.")
    en.h2(doc, "This month")
    en.body(doc, ruling, drop=True)
    en.callout(doc, "Basis", [
        "List price (RRP), VAT-inclusive where local law includes it; current discounts ignored.",
        "Duties are origin-based (Turkey): EU entry duty-free via the customs union; MFN elsewhere.",
        "Disclaimer: the cost breakdown (COGS, freight, duties, VAT, local opex, margin) is estimated from "
        "industry standards, not actual Zara/Inditex data.",
    ])
    en.page_break(doc)

    # executive summary
    en.kicker(doc, "Executive summary")
    en.h2(doc, f"Where the price went in {month_label(d['cur_date'])}")
    for para in exec_summary(d):
        en.body(doc, para)

    # the index this month
    en.kicker(doc, "The index")
    en.h2(doc, "Dearest markets this month")
    top = data["countries"][:8]
    rows = [[str(c["rank"]), c["name"], money(c["value"]),
             (f"+{c['vs_base_pct']:.0f}%" if (c.get('vs_base_pct') or 0) >= 0 else f"{c['vs_base_pct']:.0f}%"),
             money((c.get("stack") or {}).get("margin"))] for c in top]
    en.ledger_table(doc, ["#", "Market", "Price €", "vs Spain", "Margin €"], rows,
                    widths=[900, 3060, 1500, 1800, 1800], right_cols=(2, 3, 4),
                    source=f"VGR Zara Polyamide Index, {m['run_date']}. Spot FX {m['fx_asof']}.")

    # movers
    if not d["baseline"] and (d["movers_up"] or d["movers_down"]):
        en.kicker(doc, "Movers")
        en.h2(doc, f"Biggest rank moves vs {d['prior_date']}")
        mv = (d["movers_up"] + d["movers_down"])
        mrows = [[r["name"], money(r["value"]), signed(r["d_value"], " €"),
                  (f"▲{r['d_rank']}" if r["d_rank"] > 0 else f"[[r]]▼{abs(r['d_rank'])}[[/r]]")] for r in mv]
        en.ledger_table(doc, ["Market", "Price €", "Δ price", "Δ rank"], mrows,
                        widths=[3000, 1620, 1620, 2820], right_cols=(1, 2, 3),
                        source="Rank 1 = dearest. ▲ = moved up (dearer) since last month.")

    # cost / tariff changes
    if not d["baseline"] and d["cost_changes"]:
        en.kicker(doc, "Cost changes")
        en.h2(doc, "Where duty, VAT or freight moved")
        crows = []
        for r in d["cost_changes"][:10]:
            bits = []
            if r.get("d_duty_pct"): bits.append(f"duty {signed(r['d_duty_pct'],'pp')}")
            if r.get("d_vat_pct"): bits.append(f"VAT {signed(r['d_vat_pct'],'pp')}")
            if r.get("d_freight_in"): bits.append(f"freight {signed(r['d_freight_in'],' €')}")
            crows.append([r["name"], ", ".join(bits), signed(r["d_value"], " €")])
        en.ledger_table(doc, ["Market", "Change", "Δ shelf €"], crows,
                        widths=[3000, 3000, 3060], right_cols=(2,),
                        source="Assumption changes in landed.json flow straight through to the shelf-price stack.")

    watch = []
    if d.get("new_below_cost"):
        watch.append(f"Now below landed cost: {', '.join(d['new_below_cost'])}.")
    watch.append("Verify 6109.90 Turkish-origin duty per market (WITS/MacMap) and confirm direct-from-Turkey shipping.")
    en.callout(doc, "What to watch", watch)

    en.colophon(doc, [
        ("Very Good Retail", "label"),
        ("Zara Polyamide Index — a Big Mac index for one identical garment. Sources: Parser Zara scrape; "
         "market spot FX (open.er-api.com); landed-cost assumptions in landed.json.", "body"),
    ])

    out_dir = common.OUTPUT_DIR / m["run_date"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"polyamide_report_{m['run_date']}.docx"
    doc.save(str(path))
    doc.save(str(common.OUTPUT_DIR / "polyamide_report_latest.docx"))
    return str(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="monthly_report")
    ap.add_argument("--run-date", default=None)
    a = ap.parse_args(argv)

    src = (common.OUTPUT_DIR / a.run_date / "data.json") if a.run_date else (common.OUTPUT_DIR / "latest.json")
    if not src.exists():
        print(f"[report] NOOK — no data at {src}; run build_index first"); return 2
    data = json.loads(src.read_text(encoding="utf-8"))

    cur, prior = history.latest_two()
    # ensure the current run is the archived 'cur'; if archiving hasn't run, use `data` vs latest prior
    if not cur or cur["meta"]["run_date"] != data["meta"]["run_date"]:
        prior = cur if (cur and cur["meta"]["run_date"] != data["meta"]["run_date"]) else prior
        cur = data
    d = month_diff.diff(cur, prior)
    path = build(data, d)
    kind = "baseline" if d["baseline"] else f"vs {d['prior_date']}"
    print(f"[report] wrote {path}  ({kind})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
