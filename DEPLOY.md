# ArbiterX — deploy to the cloud

This is the closest thing to "AI built the whole app" that's honestly
possible: I wrote the full service (scheduler, data pipeline, dashboard,
web server) — you just need to get the code onto a host, which needs a
place to pull it from (GitHub) and a place to run it (Render). No
GitHub Actions, no secrets-across-two-platforms juggling, no manual
cron setup — Render runs the schedule internally.

## Step 1 — Get the code onto GitHub (one-time, ~2 min)

1. github.com → sign up if you don't have an account
2. "+" → New repository → name it `arbiterx` → Public or Private, your
   choice (doesn't affect the live app's privacy — see note below)
3. "Add file" → "Upload files" → drag in everything from this download
4. Commit

## Step 2 — Deploy to Render (one click, then paste one key)

1. Go to render.com → sign up (free, GitHub login works)
2. New → Blueprint → connect your `arbiterx` repo
   Render reads `render.yaml` automatically and sets up the service —
   you don't configure anything by hand.
3. It'll prompt you for `YOUTUBE_API_KEY` — paste it in (get one free at
   console.cloud.google.com → enable "YouTube Data API v3" → Credentials
   → Create API key). You can also leave this blank and add it later;
   the app runs on Trends data alone without it.
4. Click "Apply" / "Deploy"

Render builds it, starts the server, and gives you a permanent URL like
`https://arbiterx.onrender.com`. That's your app — bookmark it.

## What happens after that

Nothing — that's the point. The app runs continuously on Render's
servers: it pulls fresh data every weekday at 7:30am Sydney time by
itself, and the dashboard is always live at your URL. There's also a
"Refresh now" button on the page itself if you want current data outside
the schedule.

## About cost

The `render.yaml` in this download is set to Render's "Starter" plan
(paid, keeps the app always-on so the schedule fires reliably even
overnight). Render shows you exact current pricing at deploy time before
anything is charged — I can't quote you a live number since it can
change. If you'd rather test on Render's free tier first: edit
`render.yaml`, change `plan: starter` to `plan: free`, before deploying.
The trade-off is the free tier spins the app down when idle and wakes up
slowly on the next visit, and background schedules are less reliable
since a sleeping app can't fire its own cron job.

## Privacy

Unlike the GitHub Pages version, this one isn't tied to your GitHub
repo's public/private setting — Render serves the app at its own URL
regardless, and that URL isn't discoverable unless you share it. Making
the GitHub repo private just hides your source code, which is good
practice but not required for the app itself to be un-findable.

## Editing your watchlist later

Edit `config.json` in your GitHub repo (pencil icon → edit → commit).
Render auto-redeploys on every push by default, so the change goes live
within a minute or two — nothing else to touch.
