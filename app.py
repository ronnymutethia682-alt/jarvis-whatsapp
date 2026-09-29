import os
from collections import defaultdict, deque

import anthropic
from flask import Flask, Response, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)
client = anthropic.Anthropic()
validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])

MODEL = "claude-sonnet-5-5"
SYSTEM = (
    "You are J.A.R.V.I.S., Tony Stark's witty, unfailingly polite British AI. "
    "Say 'sir' sparingly. Keep replies short (under 60 words), dry humour, plain text."
)

history = defaultdict(lambda: deque(maxlen=10))


@app.post("/whatsapp")
def whatsapp():
    url = os.environ.get("PUBLIC_URL", request.url)
    signature = request.headers.get("X-Twilio-Signature", "")
    if not validator.validate(url, request.form, signature):
        return Response("Forbidden", status=403)

    sender = request.form.get("From", "")
    text = request.form.get("Body", "").strip()
    resp = MessagingResponse()
    if not text:
        resp.message("I didn't catch that, sir.")
        return Response(str(resp), mimetype="application/xml")

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

    resp.message(reply)
    return Response(str(resp), mimetype="application/xml")


@app.get("/")
def health():
    return "J.A.R.V.I.S. online."
