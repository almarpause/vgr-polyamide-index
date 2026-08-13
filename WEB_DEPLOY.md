# Putting the Zara Polyamide Index on the VGR site (auto-updating daily)

Same model as the **VGR 50 Index**: a free **GitHub Action** rebuilds the dashboard
in the cloud and publishes it to **GitHub Pages**, and your Lovable site shows it.
No computer of yours needs to be on for the daily refresh.

```
https://<user>.github.io/<repo>/                     <- the ready-made dashboard
https://<user>.github.io/<repo>/polyamide_data.json  <- the data feed (CORS-open)
```

**What updates when.** The per-country Zara *prices* change only weekly (the parser
scrapes on Mondays), so they travel in a small committed file, `web/snapshot_local.json`.
The *FX* changes every day, and the cloud Action fetches **live spot rates** on each
run — so the euro-denominated index (and the ranking) refreshes **daily**, exactly
like the Fashion 50. Prices are the list price / **RRP** (current discounts ignored).

---

## Step 1 — put the project on GitHub (one time)

I've already run `git init` and committed everything here. Create an **empty** repo
on github.com named **`vgr-polyamide-index`** (no README/licence), then:

```bash
cd C:\Users\aresi\Claude\code\polyamide-index
git remote add origin https://github.com/almarpause/vgr-polyamide-index.git
git branch -M main
git push -u origin main
```

(Your GitHub credentials are already cached from the Fashion 50 repo, so the push
should just work.)

## Step 2 — turn on Pages + let the Action run

- On GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
- **Actions** tab → run **"Refresh Zara Polyamide Index"** once (`Run workflow`) to
  publish immediately; after that it runs itself **every day at 06:00 UTC**.
- Live at `https://almarpause.github.io/vgr-polyamide-index/`, refreshing daily.
  Change the cadence via the `cron:` line in `.github/workflows/refresh-polyamide.yml`.

## Step 3 — keep the prices fresh (weekly, from your PC)

The cloud handles FX daily; the prices come from the committed snapshot. After the
weekly Zara scrape, refresh + push it:

```bat
web_update.bat
```

It runs `export_snapshot.py` (reads the local parser DB) and pushes
`web/snapshot_local.json`; the push triggers a rebuild. It is idempotent — it only
commits/pushes when the prices actually changed, so running it often is safe.

**Already automated:** a per-user Windows task **`PolyamideWebUpdate`** runs
`web_update.bat` **daily at 09:00**. It no-ops on days with no new scrape, and pushes
the day the weekly Zara scrape lands — so new prices reach the site within a day, hands-free.
```powershell
schtasks /Query /TN PolyamideWebUpdate /V /FO LIST     # inspect
schtasks /Run   /TN PolyamideWebUpdate                 # run now
schtasks /Delete /TN PolyamideWebUpdate /F             # remove
```

---

## Step 4 — show it in the VGR "Intelligence" section

### Option A — fastest: embed the ready-made dashboard (iframe)
Drop this into your Intelligence page in Lovable. It always shows the latest
published version; nothing else to maintain:

```html
<iframe
  src="https://almarpause.github.io/vgr-polyamide-index/?embed=1"
  title="Zara Polyamide Index"
  style="width:100%;height:2020px;border:0;border-radius:16px;"
  loading="lazy">
</iframe>
```

`?embed=1` serves a **compact** layout (condensed header, KPIs, the 65-market ranked
chart, region averages, and a link out to the full dashboard) — ~2020px, a tighter
in-page fit. Drop `?embed=1` for the full standalone dashboard (~3300px). This is the
exact embed used on the VGR site's Intelligence → Zara Polyamide Index page.

### Option B — native VGR styling: read the JSON and render it yourself
Reads the live feed and renders in your own fonts/colours. Paste this component
into your Lovable project and use `<PolyamideIndex />` on the Intelligence page.
Swap `DATA_URL` for your Pages JSON URL — that's the only edit; it re-fetches on
load, so every daily refresh shows up automatically.

```tsx
// PolyamideIndex.tsx — Zara Polyamide Index, reads the live data feed.
import { useEffect, useMemo, useState } from "react";

const DATA_URL = "https://almarpause.github.io/vgr-polyamide-index/polyamide_data.json";

type Country = {
  cc: string; name: string; flag: string; region: string;
  value: number; price_local_label: string;
  vs_base_pct: number | null; vs_ref_pct: number | null; zara_url: string;
};
type Feed = {
  meta: {
    product_name: string; reference: string; colour_name: string;
    currency: string; symbol: string; run_date: string; fx_asof: string;
    base_name: string; base_value: number; ref_name: string;
    n_countries: number; avg: number; median: number; max: number; min: number;
    cheapest: { name: string; value: number }; dearest: { name: string; value: number };
    generated_on: string;
  };
  countries: Country[];
};

export default function PolyamideIndex() {
  const [d, setD] = useState<Feed | null>(null);
  useEffect(() => { fetch(DATA_URL).then(r => r.json()).then(setD); }, []);
  const rows = useMemo(() => d ? [...d.countries].sort((a, b) => b.value - a.value) : [], [d]);
  if (!d) return <div className="p-6 text-sm opacity-60">Loading…</div>;

  const m = d.meta, sym = m.symbol, max = m.max;
  const money = (v: number) => `${sym}${v.toFixed(2)}`;
  const pct = (v: number | null) => v == null ? "" : `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`;

  return (
    <section className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Zara Polyamide Index</h2>
        <p className="text-sm opacity-60">
          One identical Zara t-shirt ({m.reference}) priced in {m.n_countries} countries, in {m.currency} —
          anchored to {m.base_name} = {money(m.base_value)}. RRP · spot FX {m.fx_asof} ·
          updated {new Date(m.generated_on).toLocaleDateString()}
        </p>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="World average" value={money(m.avg)} />
        <Kpi label="Cheapest" value={`${money(m.cheapest.value)} · ${m.cheapest.name}`} />
        <Kpi label="Dearest" value={`${money(m.dearest.value)} · ${m.dearest.name}`} />
        <Kpi label="Spread" value={`${(m.max / m.min).toFixed(1)}×`} />
      </div>

      <div className="rounded-2xl border p-4 overflow-x-auto">
        <h3 className="text-sm font-medium mb-3">All {m.n_countries} markets · click to open on zara.com</h3>
        <table className="w-full text-sm">
          <thead className="text-xs uppercase opacity-60">
            <tr>
              <th className="text-left py-1">#</th><th className="text-left">Market</th>
              <th className="text-right">{m.currency}</th><th className="text-right">Local</th>
              <th className="text-right">vs {m.base_name}</th><th className="w-1/3"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <tr key={c.cc} className="border-t">
                <td className="py-1 opacity-60">{i + 1}</td>
                <td>
                  <a href={c.zara_url} target="_blank" rel="noopener noreferrer"
                     className="hover:underline">{c.flag} {c.name}</a>
                </td>
                <td className="text-right tabular-nums font-medium">{money(c.value)}</td>
                <td className="text-right tabular-nums opacity-60">{c.price_local_label}</td>
                <td className={`text-right tabular-nums ${pos(c.vs_base_pct)}`}>{pct(c.vs_base_pct)}</td>
                <td>
                  <div className="h-2 rounded bg-gray-200">
                    <div className="h-2 rounded bg-[#B0432B]" style={{ width: `${(c.value / max) * 100}%` }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const pos = (v: number | null) => v == null ? "" : v >= 0 ? "text-rose-600" : "text-sky-600";
function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border p-4">
      <div className="text-xs uppercase opacity-60">{label}</div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}
```

---

## If you'd rather NOT use GitHub / the cloud
Keep it on your PC: schedule `python run_monthly.py --no-email` (or just
`build_index.py` + `build_dashboard.py`) and upload `output/dashboard.html` +
`output/latest.json` to wherever your site reads them. Same files — it just only
refreshes while your computer is on.

## Notes
- GitHub Pages serves the JSON with permissive CORS, so Lovable can `fetch()` it.
- The cloud build uses **only the Python standard library** (no `requirements`),
  so the Action is fast and has nothing to break on install.
- The monthly **email** on the 20th is separate and still runs from your PC — the
  website is the daily, always-on view; the email is the monthly push.
