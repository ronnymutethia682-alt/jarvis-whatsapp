import hashlib
import hmac
import os
from collections import defaultdict, deque

import anthropic
import httpx
from flask import Flask, request

app = Flask(__name__)
client = anthropic.Anthropic()

VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
WHATSAPP_TOKEN = os.environ["WHATSAPP_TOKEN"]
PHONE_NUMBER_ID = os.environ["PHONE_NUMBER_ID"]
APP_SECRET = os.environ.get("APP_SECRET", "")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v23.0")

MODEL = "claude-sonnet-5-5"
SYSTEM = (
    "You are J.A.R.V.I.S., Tony Stark's witty, unfailingly polite British AI. "
    "Say 'sir' sparingly. Keep replies short (under 60 words), dry humour, plain text."
)

history = defaultdict(lambda: deque(maxlen=10))


def send(to, body):
    httpx.post(
        f"https://graph.facebook.com/{GRAPH_VERSION}/{PHONE_NUMBER_ID}/messages",
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        },
        timeout=15,
    )


def answer(sender, text):
    msgs = history[sender]
    msgs.append({"role": "user", "content": text})
    while msgs and msgs[0]["role"] != "user":
        msgs.popleft()
    try:
        r = client.messages.create(
            model=MODEL, max_tokens=300, system=SYSTEM, messages=list(msgs)
        )
        reply = "".join(b.text for b in r.content if b.type == "text")
        msgs.append({"role": "assistant", "content": reply})
    except Exception:
        msgs.pop()
        reply = "My language core hit a snag, sir. Shall we try again?"
    send(sender, reply)


@app.get("/webhook")
def verify():
    if (
        request.args.get("hub.mode") == "subscribe"
        and request.args.get("hub.verify_token") == VERIFY_TOKEN
    ):
        return request.args.get("hub.challenge", ""), 200
    return "Forbidden", 403


@app.post("/webhook")
def incoming():
    if APP_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            APP_SECRET.encode(), request.get_data(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return "Forbidden", 403
    data = request.get_json(silent=True) or {}
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for m in change.get("value", {}).get("messages", []):
                if m.get("type") == "text":
                    answer(m["from"], m["text"]["body"])
    return "ok", 200


@app.get("/")
def health():
    return "J.A.R.V.I.S. online."
