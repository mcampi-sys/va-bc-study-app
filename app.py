#!/usr/bin/env python3
"""
VA-BC study quiz app (mobile-first tap-to-answer).

    python app.py              # serves http://localhost:8000

- Quiz sessions: 3 questions each (goal: 5/day). Unseen questions first,
  then missed ones (spaced repetition).
- Review test mode drills questions marked needs-review.
- Wrong answers: the app shows the correct answer + reasoning, then the
  user must type the reasoning in their own words before continuing
  (active recall).

Storage: data/questions.json (question bank), data/progress.json
(per-question status, own-words reasoning, session history).
Stdlib only.
"""

import json
import os
import random
import uuid
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
PROGRESS_FILE = os.path.join(DATA_DIR, "progress.json")
STATIC_DIR = os.path.join(BASE, "static")

SESSIONS = {}          # sid -> {"mode", "qids", "answers"}
QUIZ_SIZE = 3
SESSIONS_PER_DAY = 5


# ---------------------------------------------------------------- data

def load_questions():
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def blank_progress():
    return {"status": {}, "own_words": {}, "sessions": []}


def load_progress():
    p = blank_progress()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            disk = json.load(f)
        for k in p:  # tolerate state files from older versions
            if k in disk:
                p[k] = disk[k]
    return p


def save_progress(p):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PROGRESS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)
    os.replace(tmp, PROGRESS_FILE)


def public_question(q):
    """Question as sent to the browser: never includes answer/reasoning."""
    pub = {"id": q["id"], "topic": q.get("topic", ""),
           "type": q["type"], "question": q["question"]}
    if q["type"] == "mc":
        pub["options"] = q["options"]
    return pub


def pick_questions(questions, progress, mode):
    status = progress.get("status", {})
    if mode == "review":
        pool = [q for q in questions if status.get(q["id"]) == "needs-review"]
        random.shuffle(pool)
        return pool[:20]
    picked, seen_ids = [], set()
    for s in ("unseen", "needs-review", "seen"):  # unseen first, then missed
        pool = [q["id"] for q in questions
                if status.get(q["id"], "unseen") == s]
        random.shuffle(pool)
        for qid in pool:
            if len(picked) >= QUIZ_SIZE:
                break
            if qid not in seen_ids:
                picked.append(qid)
                seen_ids.add(qid)
        if len(picked) >= QUIZ_SIZE:
            break
    by_id = {q["id"]: q for q in questions}
    return [by_id[qid] for qid in picked]


def progress_summary(progress, questions):
    status = progress.get("status", {})
    counts = {"unseen": 0, "seen": 0, "mastered": 0, "needs-review": 0}
    for q in questions:
        counts[status.get(q["id"], "unseen")] += 1
    today = date.today().isoformat()
    sessions_today = sum(1 for s in progress.get("sessions", [])
                         if s.get("date") == today
                         and s.get("mode") in ("quiz", "review"))
    return {
        "total": len(questions),
        "counts": counts,
        "needs_review": counts["needs-review"],
        "sessions_today": sessions_today,
        "sessions_goal": SESSIONS_PER_DAY,
    }


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "VABCStudy/0.1"

    def _send(self, code, obj=None, ctype="application/json"):
        body = json.dumps(obj, ensure_ascii=False).encode() if obj is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def log_message(self, *a):
        pass

    # -- routes --
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html")
        if path == "/api/progress":
            return self._send(200,
                              progress_summary(load_progress(), load_questions()))
        if path.startswith("/static/"):
            return self._serve_file(unquote(path[len("/static/"):]))
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        questions = load_questions()
        by_id = {q["id"]: q for q in questions}

        if path == "/api/session":
            body = self._read_json()
            mode = body.get("mode", "quiz")
            if mode not in ("quiz", "review"):
                return self._send(400, {"error": "mode must be quiz or review"})
            picked = pick_questions(questions, load_progress(), mode)
            if not picked:
                return self._send(200, {"session_id": None, "questions": []})
            sid = uuid.uuid4().hex[:8]
            SESSIONS[sid] = {"mode": mode,
                             "qids": [q["id"] for q in picked],
                             "answers": {}}
            return self._send(200, {
                "session_id": sid,
                "questions": [public_question(q) for q in picked],
            })

        if path == "/api/check":
            # grade a multiple-choice tap; never trust the client on answers
            body = self._read_json()
            q = by_id.get(body.get("question_id"))
            if q is None or q.get("type") != "mc":
                return self._send(400, {"error": "mc question_id required"})
            selected = (body.get("selected") or "").strip()
            return self._send(200, {"correct": selected == q["answer"],
                                    "answer": q["answer"],
                                    "reasoning": q["reasoning"]})

        if path == "/api/reveal":
            # correct answer + reasoning for a short-answer self-grade step
            body = self._read_json()
            q = by_id.get(body.get("question_id"))
            if q is None:
                return self._send(400, {"error": "unknown question"})
            return self._send(200, {"answer": q["answer"],
                                    "reasoning": q["reasoning"]})

        if path == "/api/record":
            body = self._read_json()
            sid, qid = body.get("session_id"), body.get("question_id")
            if sid not in SESSIONS or qid not in by_id:
                return self._send(400, {"error": "unknown session or question"})
            correct = bool(body.get("correct"))
            progress = load_progress()
            progress["status"][qid] = "mastered" if correct else "needs-review"
            own = (body.get("own_words") or "").strip()
            if not correct and own:
                progress["own_words"][qid] = own  # their words, for later review
            SESSIONS[sid]["answers"][qid] = {
                "correct": correct,
                "user_answer": body.get("user_answer", ""),
            }
            save_progress(progress)
            return self._send(200, {"ok": True,
                                    "status": progress["status"][qid]})

        if path == "/api/session/finish":
            body = self._read_json()
            sess = SESSIONS.pop(body.get("session_id"), None)
            if sess is None:
                return self._send(400, {"error": "unknown session"})
            correct_n = sum(1 for a in sess["answers"].values()
                            if a["correct"])
            progress = load_progress()
            progress["sessions"].append({
                "date": date.today().isoformat(),
                "mode": sess["mode"],
                "total": len(sess["qids"]),
                "correct": correct_n,
            })
            save_progress(progress)
            return self._send(200, {
                "total": len(sess["qids"]),
                "correct": correct_n,
                "summary": progress_summary(progress, questions),
            })

        return self._send(404, {"error": "not found"})

    def _serve_file(self, name, ctype=None):
        safe = os.path.normpath(name).lstrip("/")
        fpath = os.path.join(STATIC_DIR, safe)
        if not fpath.startswith(STATIC_DIR) or not os.path.isfile(fpath):
            return self._send(404, {"error": "not found"})
        if ctype is None:
            ctype = {"html": "text/html", "js": "text/javascript",
                     "css": "text/css"}.get(safe.rsplit(".", 1)[-1], "text/plain")
        with open(fpath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", "8000"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"VA-BC study app running at http://localhost:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
