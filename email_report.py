"""Polyamide Index — Layer 3: email the report.

Sends an Economist-styled HTML summary (email-safe: tables + inline styles, no JS)
with the full interactive dashboard.html attached. SMTP credentials are reused
from the Zara parser's config/email.ini (git-ignored) or ZARA_SMTP_* / PI_SMTP_*
env vars — never hard-coded. Recipients come from config/settings.json.

    python email_report.py --dry-run     # print, send nothing, no creds needed
    python email_report.py               # send to the configured recipients
    python email_report.py --to a@b.com  # override recipients
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import sys
from configparser import ConfigParser
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import common

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


# --------------------------------------------------------------------- config
def load_smtp(cfg: dict) -> dict:
    """SMTP settings from the Zara email.ini, overridable by env vars."""
    s = {"host": "", "port": "587", "user": "", "password": "", "from": ""}
    ini = Path(cfg["zara_email_ini"])
    if ini.exists():
        cp = ConfigParser()
        cp.read(ini, encoding="utf-8")
        for k in ("host", "port", "user", "password", "from"):
            if cp.has_option("smtp", k):
                s[k] = cp.get("smtp", k)
    env = os.environ
    for k, ev in (("host", "SMTP_HOST"), ("port", "SMTP_PORT"), ("user", "SMTP_USER"),
                  ("password", "SMTP_PASSWORD"), ("from", "SMTP_FROM")):
        s[k] = env.get(f"PI_{ev}", env.get(f"ZARA_{ev}", s[k]))
    s["from"] = s["from"] or s["user"]
    s["password"] = s["password"].replace(" ", "")
    return s


# ---------------------------------------------------------------- email body
def render(data: dict) -> tuple[str, str, str]:
    m, C = data["meta"], data["countries"]
    s = m["symbol"]
    base, ref = m["base_name"], m["ref_name"]
    cur_word = {"EUR": "euros", "USD": "US dollars", "GBP": "pounds"}.get(m["currency"], m["currency"])
    subject = (f"Zara Polyamide Index — {m['run_date']}: "
               f"{m['dearest']['name']} dearest {s}{m['dearest']['value']:.2f}, "
               f"{m['cheapest']['name']} cheapest {s}{m['cheapest']['value']:.2f} "
               f"({m['max']/m['min']:.1f}× spread, {base} anchor {s}{m['base_value']:.2f})")

    def pct(x):
        return ("+" if x >= 0 else "") + f"{x:.0f}%"

    top = C[:8]
    bottom = C[-5:]

    def rows_html(rows):
        out = []
        for c in rows:
            vb = c["vs_base_pct"]
            col = "#B0432B" if vb >= 0 else "#2E7EA6"
            url = c.get("zara_url", "")
            name_cell = (f"<a href='{url}' style='color:#111;text-decoration:none'>{c['flag']} {c['name']} "
                         f"<span style='color:#E3120B;font-size:11px'>&#8599;</span></a>") if url else f"{c['flag']} {c['name']}"
            out.append(
                f"<tr>"
                f"<td style='padding:4px 10px;border-bottom:1px solid #eee'>{c['rank']}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid #eee'>{name_cell}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid #eee;text-align:right;font-weight:bold'>{s}{c['value']:.2f}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid #eee;text-align:right;color:#777'>{c['price_local_label']}</td>"
                f"<td style='padding:4px 10px;border-bottom:1px solid #eee;text-align:right;color:{col};font-weight:bold'>{pct(vb)}</td>"
                f"</tr>")
        return "".join(out)

    def kpi(lab, val, sub):
        return (f"<td style='padding:10px 12px;border:1px solid #e2ddd2;background:#fff'>"
                f"<div style='font:11px Arial;color:#666;text-transform:uppercase;letter-spacing:.5px'>{lab}</div>"
                f"<div style='font:bold 22px Georgia;margin-top:2px'>{val}</div>"
                f"<div style='font:11px Arial;color:#888'>{sub}</div></td>")

    kpis = ("<table cellspacing='0' cellpadding='0' style='width:100%;border-collapse:separate;border-spacing:6px'><tr>"
            + kpi("World avg", f"{s}{m['avg']:.2f}", f"{m['n_countries']} markets")
            + kpi("Cheapest", f"{s}{m['cheapest']['value']:.2f}", m['cheapest']['name'])
            + kpi("Dearest", f"{s}{m['dearest']['value']:.2f}", m['dearest']['name'])
            + kpi(f"{base} anchor", f"{s}{m['base_value']:.2f}", "the 0% benchmark")
            + "</tr></table>")

    html = f"""<div style="font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;max-width:680px">
  <div style="border-top:3px solid #E3120B;padding-top:10px">
    <span style="background:#E3120B;color:#fff;font:bold 10px Arial;letter-spacing:1px;padding:2px 7px">VERY GOOD RETAIL · FIGURE</span>
  </div>
  <h1 style="font:bold 30px Georgia;margin:10px 0 4px">Zara Polyamide Index</h1>
  <div style="font:16px Arial;color:#333;margin-bottom:8px">
    What one identical Zara t-shirt costs in {m['n_countries']} countries, priced in {cur_word},
    anchored to {base} ({s}{m['base_value']:.2f}).
  </div>
  <div style="font:12px Arial;color:#777;margin-bottom:14px">
    Reference {m['reference']} · {m['colour_name']} · snapshot {m['run_date']} · spot FX {m['fx_asof']}
  </div>

  <div style="background:#fff;border:1px solid #e2ddd2;border-left:3px solid #E3120B;padding:12px 14px;font:13px Arial;color:#333;margin-bottom:16px">
    <b>Read it like the Big Mac index.</b> One identical garment, priced worldwide. The gap between the
    cheapest and dearest market isn't the product — it's local operating cost, global logistics,
    import duties &amp; tariffs, VAT and local margin.
  </div>

  {kpis}

  <h3 style="font:bold 15px Georgia;margin:18px 0 6px">Dearest markets</h3>
  <table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;font:13px Arial">
    <tr style="text-align:left;color:#666;font-size:11px;text-transform:uppercase">
      <td style="padding:3px 10px">#</td><td style="padding:3px 10px">Market</td>
      <td style="padding:3px 10px;text-align:right">{m['currency']}</td>
      <td style="padding:3px 10px;text-align:right">Local</td>
      <td style="padding:3px 10px;text-align:right">vs {base}</td></tr>
    {rows_html(top)}
  </table>

  <h3 style="font:bold 15px Georgia;margin:18px 0 6px">Cheapest markets</h3>
  <table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;font:13px Arial">
    {rows_html(bottom)}
  </table>

  <div style="margin:18px 0 6px;font:13px Arial;color:#333">
    Attached: the month's <b>executive report</b> (Word) — who wins, how it grew, and who moved in the top and
    middle vs last month — plus the full interactive <b>dashboard.html</b> (all {m['n_countries']} markets, sortable
    by price / vs&nbsp;{base} / vs&nbsp;{ref}, every country clickable through to zara.com).
  </div>

  <div style="border-top:2px solid #1a1a1a;margin-top:20px;padding-top:8px;font:11px Arial;color:#888">
    Sources: Zara storefront scrape (Parser Zara), run {m['run_date']}; market FX from {m['fx_source']}, {m['fx_asof']}.
    RRP, VAT-inclusive where local law includes it. Generated {m['generated_on']} · Very Good Retail.
  </div>
</div>"""

    # plain-text fallback
    tl = [f"ZARA POLYAMIDE INDEX — {m['run_date']}",
          f"One identical Zara t-shirt ({m['reference']}, {m['colour_name']}) priced in {m['n_countries']} countries, in {m['currency']}.",
          f"Anchor: {base} = {s}{m['base_value']:.2f} (the 0% line).",
          "", f"World avg {s}{m['avg']:.2f} · median {s}{m['median']:.2f} · "
              f"cheapest {m['cheapest']['name']} {s}{m['cheapest']['value']:.2f} · "
              f"dearest {m['dearest']['name']} {s}{m['dearest']['value']:.2f} · "
              f"spread {m['max']/m['min']:.1f}x", "",
          "DEAREST:"]
    for c in top:
        tl.append(f"  {c['rank']:>2} {c['name']:<18} {s}{c['value']:>6.2f}  {c['price_local_label']:<10} vs{base} {pct(c['vs_base_pct'])}")
    tl += ["", "CHEAPEST:"]
    for c in bottom:
        tl.append(f"  {c['rank']:>2} {c['name']:<18} {s}{c['value']:>6.2f}  {c['price_local_label']:<10} vs{base} {pct(c['vs_base_pct'])}")
    tl += ["", "Full interactive dashboard attached (dashboard.html).",
           f"Sources: Parser Zara run {m['run_date']}; spot FX {m['fx_source']} {m['fx_asof']}."]
    return subject, "\n".join(tl), html


# ------------------------------------------------------------------- send
def send(smtp: dict, subject: str, text: str, html: str, attachments: list[Path], recipients: list[str]) -> None:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = smtp["from"]
    msg["To"] = ", ".join(recipients)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)
    _SUBTYPE = {".html": "html", ".docx": "vnd.openxmlformats-officedocument.wordprocessingml.document"}
    for att in attachments:
        if att and att.exists():
            part = MIMEApplication(att.read_bytes(), _subtype=_SUBTYPE.get(att.suffix, "octet-stream"))
            part.add_header("Content-Disposition", "attachment", filename=att.name)
            msg.attach(part)

    host, port = smtp["host"], int(smtp["port"])
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(smtp["user"], smtp["password"])
            s.sendmail(smtp["from"], recipients, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.ehlo(); s.starttls(context=ctx); s.ehlo()
            s.login(smtp["user"], smtp["password"])
            s.sendmail(smtp["from"], recipients, msg.as_string())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="email_report")
    ap.add_argument("--run-date", default=None)
    ap.add_argument("--to", default=None, help="override recipients, comma-separated")
    ap.add_argument("--dry-run", action="store_true", help="print, send nothing (no creds needed)")
    a = ap.parse_args(argv)

    cfg = common.load_settings()
    src = (common.OUTPUT_DIR / a.run_date / "data.json") if a.run_date else (common.OUTPUT_DIR / "latest.json")
    if not src.exists():
        print(f"[email] NOOK — no data at {src}; run build_index.py first", flush=True)
        return 2
    data = json.loads(src.read_text(encoding="utf-8"))
    run_date = data["meta"]["run_date"]
    dash = common.OUTPUT_DIR / run_date / "dashboard.html"
    report = common.OUTPUT_DIR / run_date / f"polyamide_report_{run_date}.docx"
    attachments = [p for p in (dash, report) if p.exists()]

    recipients = [x.strip() for x in (a.to.split(",") if a.to else cfg["recipients"]) if x and x.strip()]
    subject, text, html = render(data)

    print(f"\n########## ZARA POLYAMIDE INDEX EMAIL  run_date={run_date} ##########")
    print(f"  to      : {', '.join(recipients)}")
    print(f"  subject : {subject}")
    print(f"  attach  : {', '.join(p.name for p in attachments) or '(none — build dashboard/report first)'}")
    if a.dry_run:
        print("  --dry-run (not sending) --\n")
        print(text)
        return 0

    smtp = load_smtp(cfg)
    missing = [k for k in ("host", "user", "password", "from") if not smtp.get(k)]
    if missing:
        print(f"[email] NOOK — SMTP not configured (missing: {', '.join(missing)}). "
              f"Fill {cfg['zara_email_ini']} or set PI_SMTP_*/ZARA_SMTP_* env vars.", flush=True)
        return 2
    try:
        send(smtp, subject, text, html, attachments, recipients)
    except Exception as e:  # noqa: BLE001
        print(f"[email] NOOK — send failed: {type(e).__name__}: {e}", flush=True)
        return 2
    print(f"[email] OK — sent to {', '.join(recipients)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
