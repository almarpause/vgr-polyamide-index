"""Polyamide Index — Layer 2: build the dashboard.

Reads output/latest.json (or a given run's data.json) and writes a single,
fully self-contained interactive dashboard.html in The Economist's chart grammar:
Econ Red as the only structural accent, a navy/blue-family data palette, Georgia
+ Arial type. No external assets or network — opens by double-click and travels
as an email attachment.

    python build_dashboard.py                    # from output/latest.json
    python build_dashboard.py --run-date 2026-08-10
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import common

TEMPLATE = common.ROOT / "dashboard_template.html"


def build(data: dict) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    m = data["meta"]
    cur_word = {"EUR": "euros", "USD": "US dollars", "GBP": "pounds"}.get(m["currency"], m["currency"])
    subtitle = (f"What one identical Zara t-shirt costs in {m['n_countries']} countries, "
                f"priced in {cur_word} at market spot rates — anchored to {m['base_name']}")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    repl = {
        "%%DATA%%": payload,
        "%%TITLE%%": "Zara Polyamide Index",
        "%%SUBTITLE%%": subtitle,
        "%%SYM%%": m["symbol"],
        "%%BASE%%": m["base_name"],
        "%%REF%%": m["ref_name"],
        "%%RUNDATE%%": m["run_date"],
        "%%FXASOF%%": m["fx_asof"],
        "%%GENERATED%%": m["generated_on"],
    }
    for k, v in repl.items():
        html = html.replace(k, v)
    return html


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_dashboard")
    ap.add_argument("--run-date", default=None)
    a = ap.parse_args(argv)

    src = (common.OUTPUT_DIR / a.run_date / "data.json") if a.run_date else (common.OUTPUT_DIR / "latest.json")
    if not src.exists():
        raise SystemExit(f"[dashboard] no data at {src} — run build_index.py first")
    data = json.loads(src.read_text(encoding="utf-8"))

    html = build(data)
    run_date = data["meta"]["run_date"]
    out_dir = common.OUTPUT_DIR / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dashboard.html").write_text(html, encoding="utf-8")
    (common.OUTPUT_DIR / "dashboard.html").write_text(html, encoding="utf-8")
    print(f"[dashboard] wrote {out_dir / 'dashboard.html'}  ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
