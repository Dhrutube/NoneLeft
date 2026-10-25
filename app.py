#!/usr/bin/env python3
"""
NoneLeft — the evacuation census agent.

Every system tonight will tell you a fire started.
This is the only one that can tell you whether Maria made it out.

Stdlib-only server: no installs, no API keys required (simulator mode).
iMessage notifications are sent for real via the Mac's Messages app.

Run:  python3 app.py   ->  http://localhost:8000
"""
import json, os, re, threading, time, uuid, base64, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import send_imessage

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "config.json")
CFG = json.load(open(CFG_PATH))

# ---------------------------------------------------------------- Twilio (real calls)
from xml.sax.saxutils import escape as _xesc

def load_env():
    d = {}
    ep = os.path.join(BASE, ".env")
    if os.path.exists(ep):
        for line in open(ep):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d

ENV = load_env()
TW_SID   = ENV.get("TWILIO_ACCOUNT_SID", "")
TW_TOKEN = ENV.get("TWILIO_AUTH_TOKEN", "")
TW_FROM  = ENV.get("TWILIO_NUMBER", "")
PUBLIC_URL = ENV.get("PUBLIC_URL", "").rstrip("/")

PHONES_PATH = os.path.join(BASE, "resident_phones.json")
PHONES = json.load(open(PHONES_PATH)) if os.path.exists(PHONES_PATH) else {}

def twilio_ready():
    return bool(TW_SID and TW_TOKEN and TW_FROM and PUBLIC_URL)

def twilio_call(to, rid, attempt, cid):
    data = urllib.parse.urlencode({
        "To": to, "From": TW_FROM,
        "Url": PUBLIC_URL + "/twiml/start?rid=" + rid + "&cid=" + cid,
    }).encode()
    req = urllib.request.Request("https://api.twilio.com/2010-04-01/Accounts/" + TW_SID + "/Calls.json", data=data)
    req.add_header("Authorization", "Basic " + base64.b64encode((TW_SID + ":" + TW_TOKEN).encode()).decode())
    try:
        urllib.request.urlopen(req, timeout=25)
        return True, None
    except Exception as e:
        msg = str(e)
        try:
            msg = e.read().decode()[:300]
        except Exception:
            pass
        return False, msg.replace(TW_SID, "***").replace(TW_TOKEN, "***")

def record_real_status(rid, cat, text):
    with LOCK:
        r = S["residents"].get(rid)
        if not r:
            return
        r["status"] = cat
        r["last_change"] = time.time()
        log(f"{r['name']}: {cat.replace('_', ' ')} (REAL CALL)" + (f" — \"{text[:60]}\"" if text else ""))
        _notify_family(rid, ("is OUT and safe." if cat == "OUT" else
                             f"status: {cat.replace('_', ' ').lower()}. Responders have been notified."), cat == "OUT")

def call_real(rid):
    if not twilio_ready():
        return {"ok": False, "error": "Twilio not configured in .env"}
    phone = PHONES.get(rid, "")
    if not phone or "ENTER" in phone:
        return {"ok": False, "error": "no phone set for this resident in resident_phones.json"}
    with LOCK:
        cid = uuid.uuid4().hex[:10]
        S["calls"][cid] = {"id": cid, "resident_id": rid, "state": "RINGING", "attempt": 1,
                           "transcript": [], "created": time.time(), "real": True}
    ok, err = twilio_call(phone, rid, 1, cid)
    if not ok:
        with LOCK:
            S["calls"].pop(cid, None)
        return {"ok": False, "error": err}
    log(f"REAL CALL placed to {S['residents'][rid]['name']}")
    return {"ok": True}

def handle_twiml_start(q):
    rid = q.get("rid", ""); cid = q.get("cid", "")
    return ('<Response><Say voice="Polly.Joanna">' + _xesc(GREETING) + '</Say>'
            '<Gather input="speech dtmf" language="en-US" speechTimeout="auto" method="POST" '
            'action="' + PUBLIC_URL + '/twiml/reply?rid=' + rid + '&amp;attempt=1&amp;cid=' + cid + '">'
            '<Say>Press 1 if you are out. Press 2 if you need a ride. Press 3 for medical help. Or just say it.</Say>'
            '</Gather><Say>We could not hear you. Goodbye.</Say></Response>')

def handle_twiml_reply(q):
    rid = q.get("rid", "")
    try:
        attempt = int(q.get("attempt", "1"))
    except Exception:
        attempt = 1
    cid = q.get("cid", "")
    speech = q.get("SpeechResult", "")
    digits = q.get("Digits", "")
    cat = None
    if digits:
        cat = {"1": "OUT", "2": "NEEDS_RIDE", "3": "NEEDS_MEDICAL"}.get(digits.strip())
    if cat is None and speech:
        cat = classify(speech)
    if cat:
        record_real_status(rid, cat, speech or ("pressed " + digits))
        with LOCK:
            if cid in S["calls"]:
                S["calls"][cid]["state"] = "DONE"
        return '<Response><Say voice="Polly.Joanna">' + _xesc(CONFIRM[cat]) + '</Say><Hangup/></Response>'
    # silence / unclear: repeat the menu up to 3 attempts total
    if attempt >= 3:
        # resident could not respond -> welfare alert to the area
        record_real_status(rid, "WELFARE_CHECK", speech or "(no response)")
        with LOCK:
            if cid in S["calls"]:
                S["calls"][cid]["state"] = "DONE"
            r = S["residents"].get(rid)
            if r:
                r["attempts"] = max(r.get("attempts") or 0, 3)
        log(f"WELFARE ALERT issued for {S['residents'].get(rid, {}).get('name', rid)} — no response after 3 menu attempts")
        return ('<Response><Say voice="Polly.Joanna">We could not hear you. '
                'A responder has been dispatched to check on you. Please stay near your phone.</Say>'
                '<Hangup/></Response>')
    tries_left = 3 - attempt
    return ('<Response><Say voice="Polly.Joanna">Sorry, we could not hear you. '
            'Press 1 if you are out. Press 2 if you need a ride. Press 3 for medical help. '
            'You have ' + str(tries_left) + (' more try.' if tries_left == 1 else ' more tries.') + '</Say>'
            '<Gather input="speech dtmf" language="en-US" speechTimeout="auto" method="POST" '
            'action="' + PUBLIC_URL + '/twiml/reply?rid=' + rid + '&amp;attempt=' + str(attempt + 1) + '&amp;cid=' + cid + '">'
            '<Say>Press 1 if you are out. Press 2 for a ride. Press 3 for medical help.</Say>'
            '</Gather><Say>We could not hear you. A responder has been dispatched to check on you.</Say></Response>')

def handle_twiml_status(q):
    status = q.get("CallStatus", "")
    rid = q.get("rid", "")
    if status in ("no-answer", "busy", "failed") and rid:
        with LOCK:
            r = S["residents"].get(rid)
            if r:
                r["attempts"] = (r.get("attempts") or 0) + 1
                log(f"REAL CALL to {r['name']}: no answer (attempt {r['attempts']})")
                if r["attempts"] >= 3:
                    r["status"] = "WELFARE_CHECK"
                    r["last_change"] = time.time()
                    log(f"{r['name']} flagged for WELFARE CHECK (3 missed real calls)")
                    _notify_family(rid, "did not answer after 3 real calls. A responder welfare check has been dispatched.")
    return "<Response/>"


# ---------------------------------------------------------------- seed data
SEED = [
    {"id": "r1",  "name": "Maria Gonzalez",  "age": 81, "vuln": ["oxygen", "limited mobility"],
     "language": "en", "family": {"name": "Ananya (daughter)", "notify": True}},
    {"id": "r2",  "name": "Robert Chen",     "age": 74, "vuln": ["heart condition"],        "language": "en"},
    {"id": "r3",  "name": "Eleanor Willis",  "age": 88, "vuln": ["no vehicle", "hearing aid"],"language": "en"},
    {"id": "r4",  "name": "James Park",      "age": 41, "vuln": [],                         "language": "en"},
    {"id": "r5",  "name": "Lucia Ramirez",   "age": 67, "vuln": ["no vehicle"],             "language": "en"},
    {"id": "r6",  "name": "Tom Okafor",      "age": 52, "vuln": [],                          "language": "en"},
    {"id": "r7",  "name": "Dolores Kim",     "age": 93, "vuln": ["bedridden", "no vehicle"], "language": "en"},
    {"id": "r8",  "name": "Hector Silva",    "age": 63, "vuln": ["diabetes"],                 "language": "en"},
    {"id": "r9",  "name": "Grace Nakamura",  "age": 78, "vuln": ["walker", "lives alone"],    "language": "en"},
    {"id": "r10", "name": "Vikram Shah",     "age": 45, "vuln": [],                          "language": "en"},
    {"id": "r11", "name": "Beatrice Cole",   "age": 85, "vuln": ["dementia", "no vehicle"],  "language": "en"},
    {"id": "r12", "name": "Sam Alvarez",     "age": 29, "vuln": [],                          "language": "en"},
]

GREETING = ("This is NoneLeft, the evacuation check-in line for your neighborhood. "
            "A fire order is active in your zone. "
            "Are you out of the evacuation zone right now?")

CLARIFY = ("I want to make sure we send the right help. Tell me one thing: "
           "are you OUT of the zone, do you NEED A RIDE, or is this a MEDICAL emergency?")

# ---------------------------------------------------------------- keyword model
OUT_KW      = ["out", "safe", "left", "already", "gone", "shelter", "hotel", "carson", "left already",
               "im out", "i'm out", "yes out"]
RIDE_KW     = ["ride", "car", "no car", "no ride", "drive", "drive me", "pickup", "pick me up",
               "cant drive", "can't drive", "stuck", "no one", "nobody to", "take me"]
MEDICAL_KW  = ["oxygen", "medical", "ambulance", "hurt", "chest", "breath", "breathing", "heart",
               "dizzy", "fall", "fallen", "bleeding", "stroke", "can't move", "cant move"]

def classify(text):
    t = " " + text.lower() + " "
    for kw in MEDICAL_KW:
        if kw in t: return "NEEDS_MEDICAL"
    for kw in RIDE_KW:
        if kw in t: return "NEEDS_RIDE"
    for kw in OUT_KW:
        if kw in t: return "OUT"
    return None

CONFIRM = {
    "OUT":           "Copy that — you're out and safe. Your family has been notified. Stay clear of the zone.",
    "NEEDS_RIDE":    "Understood — you need a ride. A transit team has been dispatched to your address on the priority list. Stay by your phone.",
    "NEEDS_MEDICAL": "Medical help is being prioritized to your location right now.",
    "NEEDS_HELP":    "Thank you — I've flagged you for a welfare check with the responders. Help is on the way.",
}

# ---------------------------------------------------------------- state
LOCK = threading.Lock()
S = {
    "residents": {r["id"]: {**r, "status": "PENDING", "attempts": 0, "last_change": None} for r in SEED},
    "calls": {},          # call_id -> call dict
    "campaign": {"started": False, "started_at": None},
    "log": [],
}

def log(msg):
    S["log"].insert(0, {"t": time.strftime("%H:%M:%S"), "msg": msg})
    S["log"] = S["log"][:60]

# ---------------------------------------------------------------- call engine
def start_campaign():
    with LOCK:
        if S["campaign"]["started"]:
            return False
        S["campaign"]["started"] = True
        S["campaign"]["started_at"] = time.time()
    log("EVACUATION ORDER RECEIVED — calling every resident in the zone")
    threading.Thread(target=_campaign_loop, daemon=True).start()
    return True

def _campaign_loop():
    for rid in [r["id"] for r in SEED]:
        with LOCK:
            if S["campaign"]["started"] and S["residents"][rid]["status"] == "PENDING":
                place_call(rid)
        time.sleep(CFG.get("stagger_seconds", 2.0))

def place_call(rid, attempt=1):
    call_id = uuid.uuid4().hex[:10]
    call = {
        "id": call_id, "resident_id": rid,
        "state": "RINGING", "attempt": attempt,
        "transcript": [], "created": time.time(),
    }
    S["calls"][call_id] = call
    log(f"Calling {S['residents'][rid]['name']} (attempt {attempt})")
    threading.Timer(CFG.get("ring_timeout_seconds", 25), _ring_timeout,
                    args=(call_id,)).start()
    return call_id

def _ring_timeout(call_id):
    with LOCK:
        c = S["calls"].get(call_id)
        if not c or c["state"] != "RINGING":
            return
        rid = c["resident_id"]
        r = S["residents"][rid]
        if c["attempt"] >= CFG.get("max_attempts", 3):
            c["state"] = "NO_ANSWER"
            r["status"] = "WELFARE_CHECK"
            r["attempts"] = c["attempt"]
            r["last_change"] = time.time()
            log(f"NO ANSWER x{c['attempt']} — {r['name']} flagged for WELFARE CHECK")
            _notify_family(rid, "did not answer. A responder welfare check has been dispatched.")
        else:
            c["state"] = "NO_ANSWER"
            r["attempts"] = c["attempt"]
            log(f"No answer from {r['name']} — retrying in {CFG.get('retry_gap_seconds', 20)}s")
            threading.Timer(CFG.get("retry_gap_seconds", 20), _retry, args=(rid, c["attempt"] + 1)).start()

def _retry(rid, attempt):
    with LOCK:
        r = S["residents"][rid]
        if r["status"] not in ("PENDING", "NO_ANSWER"):
            return
    place_call(rid, attempt)

def answer_call(call_id):
    with LOCK:
        c = S["calls"][call_id]
        if c["state"] != "RINGING":
            return None
        c["state"] = "IN_PROGRESS"
        c["transcript"].append({"who": "agent", "text": GREETING})
        return c

def reply(call_id, text):
    with LOCK:
        c = S["calls"][call_id]
        if c["state"] not in ("IN_PROGRESS", "CLARIFY"):
            return c
        c["transcript"].append({"who": "resident", "text": text})
        cat = classify(text)
        rid = c["resident_id"]
        if cat is None and c["state"] == "IN_PROGRESS":
            c["state"] = "CLARIFY"
            c["transcript"].append({"who": "agent", "text": CLARIFY})
            return c
        if cat is None:  # still unclear after clarification
            cat = "NEEDS_HELP"
        c["transcript"].append({"who": "agent", "text": CONFIRM[cat]})
        c["state"] = "DONE"
        r = S["residents"][rid]
        r["status"] = cat
        r["attempts"] = c["attempt"]
        r["last_change"] = time.time()
        log(f"{r['name']}: {cat.replace('_',' ')}")
        _notify_family(rid, ("is OUT and safe." if cat == "OUT" else
                             f"status: {cat.replace('_', ' ').lower()}. Responders have been notified."), cat == "OUT")
        return c

def _notify_family(rid, detail, only_if_out=False):
    r = S["residents"][rid]
    fam = r.get("family")
    if not fam or not fam.get("notify"):
        return
    if CFG.get("family_email", "") == "":
        log(f"[iMessage skipped — no family email in config.json] Would notify {fam['name']}: {r['name']} {detail}")
        return
    msg = f"NoneLeft | Evacuation update: {r['name']} {detail}"
    ok, err = send_imessage.send(CFG["family_email"], msg)
    log(("[iMessage sent] " if ok else "[iMessage FAILED] ") + msg + ("" if ok else f" — {err}"))

def reset():
    global S
    with LOCK:
        S = {
            "residents": {r["id"]: {**r, "status": "PENDING", "attempts": 0, "last_change": None} for r in SEED},
            "calls": {},
            "campaign": {"started": False, "started_at": None},
            "log": [],
        }
    log("System reset — zone census cleared")

# ---------------------------------------------------------------- scoring
def priority_score(r):
    base = 0
    for v in r["vuln"]:
        base += 2
    base += max(0, (r["age"] - 60)) / 8
    status = r["status"]
    mult = {"WELFARE_CHECK": 8, "NEEDS_MEDICAL": 5, "NEEDS_HELP": 4, "NEEDS_RIDE": 3,
            "PENDING": 1, "RINGING": 1, "NO_ANSWER": 1, "OUT": 0}.get(status, 1)
    return round(base * mult, 1)

# ---------------------------------------------------------------- API
def api_state():
    with LOCK:
        residents = []
        for r in S["residents"].values():
            residents.append({**r, "priority": priority_score(r)})
        residents.sort(key=lambda r: -r["priority"])
        total = len(residents)
        accounted = sum(1 for r in residents if r["status"] in
                        ("OUT", "NEEDS_RIDE", "NEEDS_MEDICAL", "NEEDS_HELP", "WELFARE_CHECK"))
        out = sum(1 for r in residents if r["status"] == "OUT")
        inside = [r for r in residents if r["status"] in ("NEEDS_RIDE", "NEEDS_MEDICAL", "NEEDS_HELP", "WELFARE_CHECK")]
        ringing = [c for c in S["calls"].values() if c["state"] == "RINGING"]
        return {
            "residents": residents,
            "calls": list(S["calls"].values()),
            "log": S["log"],
            "campaign": S["campaign"],
            "summary": {"total": total, "accounted": accounted, "out": out,
                        "still_inside_or_unknown": len(inside), "calls_ringing": len(ringing)},
            "family_email": CFG.get("family_email", ""),
            "twilio_ready": twilio_ready(),
            "phones": sorted(PHONES.keys()),
        }

# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (json.dumps(body) if isinstance(body, (dict, list)) else body.encode())
        if isinstance(data, str): data = data.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/board"):
            self._send(200, open(os.path.join(BASE, "static", "board.html"), "rb").read(), "text/html")
        elif p == "/phone":
            self._send(200, open(os.path.join(BASE, "static", "phone.html"), "rb").read(), "text/html")
        elif p == "/twiml/start":
            q = {k: v[0] for k, v in urllib.parse.parse_qs(urlparse(self.path).query).items()}
            self._send(200, handle_twiml_start(q), "text/xml")
        elif p == "/api/state":
            self._send(200, api_state())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("application/x-www-form-urlencoded"):
            q = urllib.parse.parse_qs(raw.decode())
            body = {k: v[0] for k, v in q.items()}
        else:
            try:
                body = json.loads(raw or b"{}")
            except Exception:
                body = {}
        body.update({k: v[0] for k, v in urllib.parse.parse_qs(urlparse(self.path).query).items()})
        if p == "/api/trigger":
            ok = start_campaign()
            self._send(200, {"ok": ok})
        elif p == "/api/reset":
            reset(); self._send(200, {"ok": True})
        elif p.startswith("/api/call/") and p.endswith("/answer"):
            cid = p.split("/")[3]
            c = answer_call(cid)
            self._send(200, {"ok": c is not None, "call": c})
        elif p.startswith("/api/call/") and p.endswith("/reply"):
            cid = p.split("/")[3]
            c = reply(cid, body.get("text", ""))
            self._send(200, {"ok": c is not None, "call": c})
        elif p == "/twiml/start":
            q = {k: v[0] for k, v in urllib.parse.parse_qs(urlparse(self.path).query).items()}
            self._send(200, handle_twiml_start(q), "text/xml")
        elif p == "/api/call-real":
            self._send(200, call_real(body.get("rid", "")))
        elif p == "/twiml/reply":
            self._send(200, handle_twiml_reply(body), "text/xml")
        elif p == "/twiml/status":
            self._send(200, handle_twiml_status(body), "text/xml")
        elif p == "/api/test-imessage":
            if not CFG.get("family_email"):
                self._send(400, {"ok": False, "error": "family_email not set in config.json"})
            else:
                ok, err = send_imessage.send(CFG["family_email"],
                    "NoneLeft TEST — this is what a family notification looks like. 🚀")
                self._send(200, {"ok": ok, "error": err})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, fmt, *a):
        try:
            open("/tmp/muster_access.log", "a").write(time.strftime("%H:%M:%S ") + (fmt % a) + "\n")
        except Exception:
            pass

if __name__ == "__main__":
    port = CFG.get("port", 8000)
    os.chdir(BASE)
    print(f"\n  NONELEFT — evacuation census agent")
    print(f"  Dispatch board : http://localhost:{port}/")
    print(f"  Resident phone : http://localhost:{port}/phone")
    print(f"  Family iMessage: {'configured -> ' + CFG['family_email'] if CFG.get('family_email') else 'NOT SET (edit config.json)'}\n")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
