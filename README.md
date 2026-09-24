# VA-BC Study App

A mobile-first tap-to-answer quiz app for VA-BC (vascular access)
certification prep. One question per screen, big touch targets, no
typing question numbers.

## How it works

- **Start quiz session** — 3 questions (goal: 5 sessions/day). Unseen
  questions come first, then missed ones cycle back (spaced repetition).
- **Review test** — drills every question marked needs-review.
- **Wrong answers** — you see the correct answer plus its reasoning,
  then you must type the reasoning in your own words before continuing
  (active recall — this is what makes it stick).
- **Short answers** — you type your answer, compare it against the
  correct one, and honestly tap "I got it" or "I missed it".

Progress is saved in `data/progress.json`: per-question status
(unseen / seen / mastered / needs-review), your own-words reasoning,
and session history with dates.

## Run it

```bash
cd ~/workspace/va-bc-study-app
python app.py
```

Then open **http://localhost:8000** in your browser.

No dependencies — stdlib Python 3 only.

## Run it on Android (Termux)

1. Install Termux from F-Droid and open it.
2. `pkg install python`
3. Copy this folder to your phone (or `git clone` it if you push it to
   GitHub), then:
   ```bash
   cd va-bc-study-app
   python app.py
   ```
4. Open **http://localhost:8000** in your phone's browser (Chrome/Samsung
   Internet). The server runs on the phone itself, so it works offline.

Tip: run it in a Termux session you keep alive, or use
`termux-wake-lock` so Android doesn't kill it mid-session.

## Files

- `app.py` — HTTP server + quiz API (port 8000, `PORT` env overrides)
- `static/index.html` — the whole UI (one page, vanilla JS)
- `data/questions.json` — question bank (seeded with Day-1 fundamentals)
- `data/progress.json` — your progress (created/seeded on first run)

## API (for debugging)

- `GET  /api/progress` — counts, sessions today, review backlog
- `POST /api/session` `{"mode":"quiz"|"review"}` — start session
- `POST /api/check` `{"question_id","selected"}` — grade an MC tap
- `POST /api/reveal` `{"question_id"}` — answer+reasoning for self-grade
- `POST /api/record` `{"session_id","question_id","correct","user_answer","own_words"}` — save result
- `POST /api/session/finish` `{"session_id"}` — close session, log history
