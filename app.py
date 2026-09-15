"""
ArbiterX — cloud app

A single web service that:
  - runs the Trends + YouTube fetch on a schedule, in the background,
    by itself (no external scheduler needed)
  - serves the live dashboard at "/"
  - has a "Refresh now" button that forces an immediate re-fetch

This is designed to run continuously on a host like Render, Railway, or
Fly.io — one process does everything.
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, redirect

app = Flask(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

STATE = {"rows": [], "last_run": None, "running": False}
STATE_LOCK = threading.Lock()


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def fetch_trends(watchlist: dict, region: str) -> dict:
    from pytrends.request import TrendReq
    pytrends = TrendReq(hl="en-AU", tz=600)
    results = {}
    for ticker, term in watchlist.items():
        try:
            pytrends.build_payload([term], timeframe="now 7-d", geo=region)
            df = pytrends.interest_over_time()
            series = df[term].tolist() if not df.empty else []
            score = int(series[-1]) if series else 0
            results[ticker] = {"score": score, "series": series}
        except Exception:
            results[ticker] = {"score": 0, "series": []}
        time.sleep(1.5)
    return results


def fetch_youtube(watchlist: dict, api_key: str, lookback_days: int) -> dict:
    if not api_key:
        return {t: {"mentions": 0, "total_views": 0} for t in watchlist}

    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    youtube = build("youtube", "v3", developerKey=api_key)
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    results = {}
    for ticker, term in watchlist.items():
        try:
            search_resp = youtube.search().list(
                q=f"{term} ASX", part="id", type="video",
                order="date", publishedAfter=published_after, maxResults=25,
            ).execute()
            video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
            total_views = 0
            if video_ids:
                stats_resp = youtube.videos().list(id=",".join(video_ids), part="statistics").execute()
                total_views = sum(int(it.get("statistics", {}).get("viewCount", 0)) for it in stats_resp.get("items", []))
            results[ticker] = {"mentions": len(video_ids), "total_views": total_views}
        except HttpError:
            results[ticker] = {"mentions": 0, "total_views": 0}
        time.sleep(0.3)
    return results


def normalize(values):
    clean = [v for v in values if v is not None]
    if not clean or max(clean) == min(clean):
        return [0 for _ in values]
    lo, hi = min(clean), max(clean)
    return [int(((v - lo) / (hi - lo)) * 100) for v in values]


def build_rows(watchlist, trends, youtube):
    tickers = list(watchlist.keys())
    trend_scores = [trends[t]["score"] for t in tickers]
    views = [youtube[t]["total_views"] for t in tickers]
    norm_views = normalize(views)

    rows = []
    for i, t in enumerate(tickers):
        buzz = round(0.5 * trend_scores[i] + 0.5 * norm_views[i])
        signal = "hot" if buzz >= 75 else "watch" if buzz >= 45 else "quiet"
        rows.append({
            "ticker": t, "name": watchlist[t], "buzz": buzz,
            "trend_score": trend_scores[i], "mentions": youtube[t]["mentions"],
            "views": youtube[t]["total_views"], "series": trends[t]["series"][-14:],
            "signal": signal,
        })
    return rows


def run_pipeline():
    with STATE_LOCK:
        if STATE["running"]:
            return
        STATE["running"] = True
    try:
        config = load_config()
        watchlist = config.get("watchlist", {})
        api_key = os.environ.get("YOUTUBE_API_KEY", "")
        trends = fetch_trends(watchlist, config.get("google_trends_region", "AU"))
        youtube = fetch_youtube(watchlist, api_key, config.get("lookback_days", 14))
        rows = build_rows(watchlist, trends, youtube)
        with STATE_LOCK:
            STATE["rows"] = rows
            STATE["last_run"] = datetime.now(timezone.utc)
    finally:
        with STATE_LOCK:
            STATE["running"] = False


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(timezone="Australia/Sydney")
    scheduler.add_job(run_pipeline, "cron", day_of_week="mon-fri", hour=7, minute=30)
    scheduler.start()
    threading.Thread(target=run_pipeline, daemon=True).start()  # run once on boot


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ArbiterX</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #0D1117; color: #EAEDF1; font-family: 'IBM Plex Sans', sans-serif; font-size: 14px; }}
  .mono {{ font-family: 'IBM Plex Mono', monospace; }}
  header {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid #262E38; }}
  header .title {{ font-size: 16px; font-weight: 600; }}
  header .meta {{ font-size: 12px; color: #7D8590; }}
  .btn {{ background: #151B23; border: 1px solid #262E38; border-radius: 4px; padding: 7px 14px; color: #EAEDF1; font-size: 12.5px; cursor: pointer; text-decoration: none; font-family: 'IBM Plex Mono', monospace; }}
  .btn:hover {{ border-color: #2DD4BF55; }}
  .search {{ background: #151B23; border: 1px solid #262E38; border-radius: 4px; padding: 6px 10px; color: #EAEDF1; font-size: 12.5px; width: 200px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 10px 14px; font-size: 11px; color: #7D8590; cursor: pointer; user-select: none; border-bottom: 1px solid #262E38; }}
  th.num, td.num {{ text-align: right; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid #1A2029; font-size: 12.5px; }}
  tr.row:hover {{ background: #10151C; }}
  .name {{ color: #7D8590; font-size: 11px; }}
  .badge {{ font-size: 11px; border-radius: 3px; padding: 2px 7px; font-family: 'IBM Plex Mono', monospace; }}
  .badge.hot {{ color: #2DD4BF; border: 1px solid #2DD4BF55; }}
  .badge.watch {{ color: #E3B341; border: 1px solid #E3B34155; }}
  .badge.quiet {{ color: #7D8590; border: 1px solid #3B4551; }}
  .bars {{ display: flex; align-items: flex-end; gap: 2px; height: 20px; }}
  .bar {{ width: 3px; background: #3B4551; border-radius: 1px; }}
  footer {{ padding: 16px 24px; color: #7D8590; font-size: 11.5px; border-top: 1px solid #262E38; }}
</style>
</head>
<body>
  <header>
    <div>
      <div class="title mono">ArbiterX</div>
      <div class="meta">{status_line}</div>
    </div>
    <div style="display:flex; gap:10px; align-items:center;">
      <input class="search mono" id="search" placeholder="Search ticker or name" oninput="filterRows()">
      <a class="btn" href="/refresh">Refresh now</a>
    </div>
  </header>

  <table>
    <thead>
      <tr>
        <th onclick="sortBy('ticker')">Ticker</th>
        <th class="num" onclick="sortBy('trend_score')">Trend</th>
        <th>Mentions (14d)</th>
        <th class="num" onclick="sortBy('mentions')">Videos</th>
        <th class="num" onclick="sortBy('buzz')">Buzz</th>
        <th>Signal</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>

  <footer>
    Buzz blends Google Trends search interest with YouTube mention volume.
    Sentiment (bullish/bearish polarity) isn't wired in yet. Auto-refreshes
    weekdays at 7:30am Sydney time, or click "Refresh now" any time.
  </footer>

<script>
  const DATA = {data_json};
  let sortKey = 'buzz', sortDir = -1;

  function sparkbars(series) {{
    if (!series.length) return '<span style="color:#3B4551">—</span>';
    const max = Math.max(...series, 1);
    return '<div class="bars">' + series.slice(-8).map((v,i,arr) =>
      `<div class="bar" style="height:${{Math.max(2, (v/max)*20)}}px; background:${{i===arr.length-1?'#2DD4BF':'#3B4551'}}"></div>`
    ).join('') + '</div>';
  }}

  function render() {{
    const q = document.getElementById('search').value.toLowerCase();
    let rows = DATA.filter(r => r.ticker.toLowerCase().includes(q) || r.name.toLowerCase().includes(q));
    rows.sort((a,b) => (a[sortKey] - b[sortKey]) * sortDir);
    document.getElementById('rows').innerHTML = rows.map(r => `
      <tr class="row">
        <td><span class="mono" style="font-weight:600">${{r.ticker}}</span><br><span class="name">${{r.name}}</span></td>
        <td class="num mono">${{r.trend_score}}</td>
        <td>${{sparkbars(r.series)}}</td>
        <td class="num mono">${{r.mentions}}</td>
        <td class="num mono">${{r.buzz}}</td>
        <td><span class="badge ${{r.signal}}">${{r.signal}}</span></td>
      </tr>`).join('');
  }}
  function sortBy(key) {{ sortDir = (sortKey === key) ? -sortDir : -1; sortKey = key; render(); }}
  function filterRows() {{ render(); }}
  render();
</script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    with STATE_LOCK:
        rows = STATE["rows"]
        last_run = STATE["last_run"]
        running = STATE["running"]

    if running and not rows:
        status = "First data pull in progress — refresh this page in a minute."
    elif running:
        status = f"Refreshing now... (last complete run: {last_run.strftime('%Y-%m-%d %H:%M UTC') if last_run else 'never'})"
    elif last_run:
        status = f"Last updated {last_run.strftime('%Y-%m-%d %H:%M UTC')}"
    else:
        status = "No data yet."

    return HTML_TEMPLATE.format(status_line=status, data_json=json.dumps(rows))


@app.route("/refresh")
def refresh():
    threading.Thread(target=run_pipeline, daemon=True).start()
    return redirect("/")


@app.route("/healthz")
def healthz():
    return {"ok": True}


start_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
