"""Polyamide Index — monthly orchestrator.

One shared run: build the dataset from the latest Zara snapshot, render the
dashboard, then email it to the configured recipients. This is what the Windows
scheduled task fires on the 20th of every month.

    python run_monthly.py               # full run, sends the email
    python run_monthly.py --dry-run     # build everything, print the email, send nothing
    python run_monthly.py --no-email    # build only

Exit code is 0 only if every step reports OK, so the scheduler can flag failures.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

import build_dashboard
import build_index
import common
import email_report

LOG_DIR = common.ROOT / "logs"


def _push_web() -> None:
    """Commit + push the new monthly post + snapshot so GitHub Pages (and the VGR
    site's archive) update. Non-fatal; needs the PC's cached git credentials."""
    import subprocess
    r = common.ROOT
    subprocess.run(["git", "-C", str(r), "add", "web/posts", "history"], check=False)
    staged = subprocess.run(["git", "-C", str(r), "diff", "--cached", "--quiet"]).returncode
    if staged == 0:
        log("web push — nothing new to publish"); return
    from datetime import datetime as _dt
    subprocess.run(["git", "-C", str(r), "commit", "-m", f"post: monthly analysis {_dt.now():%Y-%m}"], check=False)
    rc = subprocess.run(["git", "-C", str(r), "push"]).returncode
    log("web push OK — post published" if rc == 0 else f"web push failed (git rc={rc})")


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / f"run_{datetime.now():%Y-%m}.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_monthly")
    ap.add_argument("--run-date", default=None)
    ap.add_argument("--dry-run", action="store_true", help="build all, print email, send nothing")
    ap.add_argument("--no-email", action="store_true", help="build only, skip the email step")
    ap.add_argument("--offline", action="store_true", help="reuse cached FX")
    a = ap.parse_args(argv)

    log("===== Polyamide Index monthly run =====")
    rc = 0

    idx_args = []
    if a.run_date:
        idx_args += ["--run-date", a.run_date]
    if a.offline:
        idx_args.append("--offline")
    log("Layer 1 — build_index")
    r1 = build_index.main(idx_args)
    if r1 != 0:
        log("build_index FAILED — aborting"); return 2

    log("Layer 2 — build_dashboard")
    r2 = build_dashboard.main(["--run-date", a.run_date] if a.run_date else [])
    if r2 != 0:
        log("build_dashboard FAILED — aborting"); return 2

    # Layer 2b — archive this month's shot, build the executive report + web post,
    # and push the post so the site's monthly archive updates. All non-fatal: a
    # failure here must never block the email of the dashboard.
    log("Layer 2b — historise + monthly report + web post")
    try:
        import json as _json
        import history
        import monthly_report
        import build_post
        rd = ["--run-date", a.run_date] if a.run_date else []
        src = (common.OUTPUT_DIR / a.run_date / "data.json") if a.run_date else (common.OUTPUT_DIR / "latest.json")
        data = _json.loads(src.read_text(encoding="utf-8"))
        history.record(data)
        log("monthly report OK" if monthly_report.main(rd) == 0 else "monthly report NOOK")
        log("web post OK" if build_post.main(rd) == 0 else "web post NOOK")
        if not a.dry_run:
            _push_web()
    except Exception as e:  # noqa: BLE001
        log(f"historise/report/post step failed ({type(e).__name__}: {e}); continuing to email")

    if a.no_email:
        log("Layer 3 — email SKIPPED (--no-email)")
        log("DONE (build only)")
        return 0

    log("Layer 3 — email_report" + (" (dry-run)" if a.dry_run else ""))
    e_args = []
    if a.run_date:
        e_args += ["--run-date", a.run_date]
    if a.dry_run:
        e_args.append("--dry-run")
    r3 = email_report.main(e_args)
    if r3 != 0:
        log("email_report reported NOOK"); rc = 2

    log("DONE" if rc == 0 else "DONE with errors")
    return rc


if __name__ == "__main__":
    sys.exit(main())
