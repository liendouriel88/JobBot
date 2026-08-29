# Job Seeker Bot

Checks Google Jobs once a day for new postings in 4 categories, and sends
you a single Telegram message with anything new. Same pattern as your
flight bot, but a separate repo and a separate Telegram bot.

## What it searches for

1. Junior QA Tester (video games)
2. Customer Service (non-voice — voice/call-center roles are filtered out)
3. Junior Data Entry
4. QA Internship

For each, it keeps jobs that are either **remote** (anywhere) or **based in
Córdoba / Alta Gracia**. Everything else is discarded before you ever see it.

---

## Step 1 — Create a new Telegram bot

1. Open Telegram, search for **@BotFather**, and start a chat with it.
2. Send the message: `/newbot`
3. It'll ask for a name (anything, e.g. "My Job Alerts") and a username
   (must end in "bot", e.g. `mydailyjobs_bot`).
4. BotFather will reply with a **token** — a long string like
   `123456789:AAExampleTokenGoesHere`. Copy it, you'll need it in Step 4.
5. Now send your new bot **any message** (e.g. "hi") — just open a chat with
   it and type something. This is required so Telegram knows to talk to you.

## Step 2 — Get your chat ID

1. In your browser, go to this URL, replacing `<TOKEN>` with the token from
   Step 1:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
2. You'll see some JSON text. Look for `"chat":{"id":` — the number right
   after `id` is your **chat ID**. Copy it.

   (If you see an empty result, go back to Step 1.5 and make sure you sent
   the bot a message first, then reload the URL.)

## Step 3 — Create the GitHub repo

1. Go to [github.com/new](https://github.com/new) and create a new empty
   repository (e.g. `job-seeker-bot`). Don't add a README, .gitignore, or
   license — leave it empty.
2. On your Mac, open **Terminal** and navigate to wherever you keep your
   projects, e.g.:
   ```
   cd ~/Documents
   ```
3. Clone the empty repo (replace `YOUR-USERNAME`):
   ```
   git clone https://github.com/YOUR-USERNAME/job-seeker-bot.git
   cd job-seeker-bot
   ```
4. Copy all the files I gave you (`job_bot.py`, `requirements.txt`,
   `seen_jobs.json`, `.github/` folder, this `README.md`) into that folder.

5. Push them up:
   ```
   git add .
   git commit -m "Initial job bot setup"
   git push
   ```

## Step 4 — Add your secrets to GitHub

GitHub Actions needs your API key and Telegram details, but stored securely
(never put these directly in the code).

1. On GitHub, go to your new repo → **Settings** → **Secrets and variables**
   → **Actions**.
2. Click **New repository secret** and add each of these one at a time:
   - `SERPAPI_KEY` → the same key you use for the flight bot
   - `TELEGRAM_BOT_TOKEN` → the token from Step 1
   - `TELEGRAM_CHAT_ID` → the chat ID from Step 2

## Step 5 — Test it

1. On GitHub, go to the **Actions** tab of your repo.
2. Click on **Daily Job Check** in the left sidebar.
3. Click **Run workflow** → **Run workflow** (this triggers it manually
   without waiting for the schedule).
4. After ~30 seconds, refresh the page — you should see a run appear. Click
   it to see the logs. If it succeeded (green checkmark), check Telegram —
   you should get a digest (or a "no new jobs" line in the logs if nothing
   matched yet).

## How it runs afterward

Once set up, it runs automatically every day at 09:00 Argentina time (no
need for your Mac to be on — it runs on GitHub's servers, same as the
flight bot). Each run remembers which jobs it already told you about
(stored in `seen_jobs.json`, auto-updated and committed back to the repo),
so you'll only ever be notified about genuinely new postings.

## Adjusting later

- **Change the search terms**: edit the `SEARCHES` list near the top of
  `job_bot.py`.
- **Change the cities**: edit `ALLOWED_LOCAL_CITIES` in `job_bot.py`.
- **Change the time it runs**: edit the `cron` line in
  `.github/workflows/daily_check.yml`.
