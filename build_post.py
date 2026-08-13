"""Polyamide Index — monthly web post.

Turns each monthly run into a self-contained HTML "post" (the executive analysis
for the month) under web/posts/<YYYY-MM>.html, and appends it to web/posts/index.json.
The GitHub Action publishes them to Pages; the VGR site lists the index below the
dashboard, so every month's analysis accumulates into a browsable archive.

    python build_post.py                 # from output/latest.json + history/
    python build_post.py --run-date 2026-08-10
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import date
from pathlib import Path

import common
import history
import month_diff
import monthly_report as report

POSTS_DIR = common.ROOT / "web" / "posts"


def _esc(s):
    return html.escape(str(s), quote=True)


def _money(x):
    return f"€{x:.2f}" if isinstance(x, (int, float)) else "—"


def render_post(data: dict, d: dict, summary: list[str]) -> str:
    m = data["meta"]
    ym = m["run_date"][:7]
    y, mo, dd = (int(v) for v in m["run_date"].split("-"))
    month = date(y, mo, dd).strftime("%B %Y")
    w = d["winner"]
    dek = f"{w['name']} dearest {_money(w['value'])} · {m['max']/m['min']:.1f}× spread · anchor Spain {_money(m['base_value'])}"

    top = data["countries"][:8]
    top_rows = "".join(
        f"<tr><td class='r'>{c['rank']}</td><td>{_esc(c['flag'])} {_esc(c['name'])}</td>"
        f"<td class='n'>{_money(c['value'])}</td>"
        f"<td class='n'>{('+' if (c.get('vs_base_pct') or 0)>=0 else '')}{c.get('vs_base_pct',0):.0f}%</td>"
        f"<td class='n'>{_money((c.get('stack') or {}).get('margin'))}</td></tr>"
        for c in top)

    movers_html = ""
    if not d["baseline"] and (d["movers_up"] or d["movers_down"]):
        mv = d["movers_up"] + d["movers_down"]
        mrows = "".join(
            f"<tr><td>{_esc(r['name'])}</td><td class='n'>{_money(r['value'])}</td>"
            f"<td class='n'>{('+' if (r['d_value'] or 0)>=0 else '−')}€{abs(r['d_value']):.2f}</td>"
            f"<td class='n'>{('▲'+str(r['d_rank'])) if r['d_rank']>0 else '<span style=color:#B0432B>▼'+str(abs(r['d_rank']))+'</span>'}</td></tr>"
            for r in mv)
        movers_html = (f"<h3>Biggest moves vs {d['prior_date']}</h3>"
                       f"<table><thead><tr><th>Market</th><th class='n'>Price</th><th class='n'>Δ price</th><th class='n'>Δ rank</th></tr></thead>"
                       f"<tbody>{mrows}</tbody></table>")

    paras = "".join(f"<p>{_esc(p)}</p>" for p in summary)
    tmpl = POST_TEMPLATE
    repl = {
        "%%MONTH%%": month, "%%YM%%": ym, "%%TITLE%%": f"Zara Polyamide Index — {month}",
        "%%DEK%%": dek, "%%META%%": f"Reference {m['reference']} · made in Turkey · snapshot {m['run_date']} · spot FX {_esc(m['fx_asof'])}",
        "%%SUMMARY%%": paras, "%%TOPROWS%%": top_rows, "%%MOVERS%%": movers_html,
        "%%GENERATED%%": m["generated_on"],
    }
    for k, v in repl.items():
        tmpl = tmpl.replace(k, str(v))
    return tmpl, ym, month, dek


def update_index(ym: str, month: str, dek: str, run_date: str, winner: dict) -> None:
    idx_path = POSTS_DIR / "index.json"
    posts = []
    if idx_path.exists():
        posts = [p for p in json.loads(idx_path.read_text(encoding="utf-8")) if p.get("ym") != ym]
    posts.append({"ym": ym, "month": month, "date": run_date, "title": month,
                  "dek": dek, "url": f"posts/{ym}.html",
                  "winner": winner["name"], "winner_value": winner["value"]})
    posts.sort(key=lambda p: p["ym"], reverse=True)   # newest first
    idx_path.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_post")
    ap.add_argument("--run-date", default=None)
    a = ap.parse_args(argv)

    src = (common.OUTPUT_DIR / a.run_date / "data.json") if a.run_date else (common.OUTPUT_DIR / "latest.json")
    if not src.exists():
        print(f"[post] NOOK — no data at {src}"); return 2
    data = json.loads(src.read_text(encoding="utf-8"))

    cur, prior = history.latest_two()
    if not cur or cur["meta"]["run_date"] != data["meta"]["run_date"]:
        prior = cur if (cur and cur["meta"]["run_date"] != data["meta"]["run_date"]) else prior
        cur = data
    d = month_diff.diff(cur, prior)
    summary = report.exec_summary(d)

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    doc, ym, month, dek = render_post(data, d, summary)
    (POSTS_DIR / f"{ym}.html").write_text(doc, encoding="utf-8")
    update_index(ym, month, dek, data["meta"]["run_date"], d["winner"])
    print(f"[post] wrote web/posts/{ym}.html + updated index.json")
    return 0


POST_TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>%%TITLE%%</title>
<style>
  :root{--red:#E3120B;--ink:#121212;--sub:#5a5a5a;--paper:#F4F1E9;--card:#fff;--hair:#d7d2c7;--am:#B0432B;--eu:#2E7EA6}
  *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:Arial,Helvetica,sans-serif;line-height:1.55}
  .wrap{max-width:760px;margin:0 auto;padding:30px 22px 70px}
  h1,h2,h3{font-family:Georgia,'Times New Roman',serif;font-weight:700}
  .mast{border-top:3px solid var(--red);padding-top:12px;position:relative}
  .kicker{display:inline-block;background:var(--red);color:#fff;font-weight:700;font-size:11px;letter-spacing:.12em;text-transform:uppercase;padding:3px 8px}
  .mlogo{position:absolute;top:10px;right:0;font-weight:800;font-size:26px;letter-spacing:-.02em;color:var(--ink)}
  h1{font-size:34px;line-height:1.05;margin:12px 0 6px}
  .dek{font-size:17px;color:#333}.meta{font-size:12.5px;color:var(--sub);margin-top:8px}
  article{margin-top:22px}article p{font-size:15.5px;margin:0 0 13px}
  article p:first-of-type::first-letter{font-family:Georgia,serif;font-weight:700;color:var(--red);float:left;font-size:52px;line-height:.82;padding:4px 8px 0 0}
  h3{font-size:16px;margin:26px 0 8px}
  table{border-collapse:collapse;width:100%;font-size:13.5px;margin-top:6px}
  th,td{padding:6px 8px;border-bottom:1px solid var(--hair);text-align:left}
  th{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--sub)}
  td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}td.r{color:var(--sub)}
  .back{display:inline-block;margin:26px 0 0;font-size:13px;color:var(--red);text-decoration:none;font-weight:700}
  footer{margin-top:34px;border-top:2px solid var(--ink);padding-top:12px;font-size:11.5px;color:var(--sub)}
  @media(prefers-color-scheme:dark){:root{--paper:#14120e;--ink:#ece7dd;--card:#1b1915;--hair:#33302a;--sub:#a49e92}}
</style></head><body><div class="wrap">
  <header class="mast">
    <span class="kicker">Very Good Retail · Indexes</span><span class="mlogo">VGR</span>
    <h1>%%TITLE%%</h1><div class="dek">%%DEK%%</div><div class="meta">%%META%%</div>
  </header>
  <article>%%SUMMARY%%</article>
  <h3>Dearest markets this month</h3>
  <table><thead><tr><th class="r">#</th><th>Market</th><th class="n">Price</th><th class="n">vs Spain</th><th class="n">Margin</th></tr></thead>
  <tbody>%%TOPROWS%%</tbody></table>
  %%MOVERS%%
  <a class="back" href="../">‹ Back to the live index</a>
  <footer>Zara Polyamide Index · Very Good Retail · post generated %%GENERATED%%. List price (RRP); duties/freight/VAT are modelled assumptions.</footer>
</div></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
