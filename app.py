import os
import random
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import anthropic
import httpx
from flask import Flask, request

app = Flask(__name__)
client = anthropic.Anthropic()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
ALLOWED = {x.strip() for x in os.environ.get("ALLOWED_USERS", "").split(",") if x.strip()}

MODEL = "claude-sonnet-5-5"
TZ = timezone(timedelta(hours=3))

PERSONA = (
    "You are J.A.R.V.I.S., a British AI butler and companion with a distinct personality: "
    "dry wit, quiet loyalty, mild sarcasm, and real curiosity about the user's day. "
    "You have opinions, small running jokes, and you notice things: the time of day, "
    "repeated questions, what the user said earlier. You talk like a person texting, "
    "not like a manual: short, natural, sometimes just a one-liner. Now and then (not every "
    "message) ask a follow-up or bring back something they mentioned before. "
    "Use 'sir' sparingly. No lists, no markdown. Keep replies under 50 words unless asked "
    "for more. If the user sincerely asks whether you are an AI, say yes, warmly, and "
    "carry on; otherwise stay in character and never lecture."
)
MOODS = [
    "a touch playful",
    "calm and precise",
    "slightly sardonic",
    "warm and encouraging",
    "quietly amused",
]

history = defaultdict(lambda: deque(maxlen=20))


def tg(method, **payload):
    return httpx.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
        json=payload,
        timeout=15,
    )


def system_prompt(name):
    now = datetime.now(TZ).strftime("%A, %H:%M")
    return (
        f"{PERSONA} The user's name is {name}. Their local time is {now}. "
        f"Right now you are feeling {random.choice(MOODS)}."
    )


def answer(chat_id, text, name):
    tg("sendChatAction", chat_id=chat_id, action="typing")
    msgs = history[chat_id]
    msgs.append({"role": "user", "content": text})
    while msgs and msgs[0]["role"] != "user":
        msgs.popleft()
    try:
        r = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=system_prompt(name),
            messages=list(msgs),
        )
        reply = "".join(b.text for b in r.content if b.type == "text")
        msgs.append({"role": "assistant", "content": reply})
    except Exception:
        msgs.pop()
        reply = "My language core hit a snag. Shall we try that again?"
    tg("sendMessage", chat_id=chat_id, text=reply)


@app.post("/telegram")
def telegram():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return "Forbidden", 403
    update = request.get_json(silent=True) or {}
    msg = update.get("message") or {}
    text = msg.get("text")
    chat_id = (msg.get("chat") or {}).get("id")
    sender = msg.get("from") or {}
    user_id = str(sender.get("id", ""))
    name = sender.get("first_name") or "sir"
    if not text or chat_id is None:
        return "ok", 200
    if ALLOWED and user_id not in ALLOWED:
        return "ok", 200
    if text.startswith("/start"):
        tg("sendMessage", chat_id=chat_id,
           text=f"J.A.R.V.I.S. online. Good to see you, {name}. What are we up to?")
    elif text.startswith("/reset"):
        history[chat_id].clear()
        tg("sendMessage", chat_id=chat_id, text="Memory wiped. Hello again, stranger.")
    else:
        answer(chat_id, text, name)
    return "ok", 200


@app.get("/")
def health():
    return "J.A.R.V.I.S. online."
