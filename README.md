# NoneLeft — the evacuation census agent

**Every system tonight will tell you a fire started. This is the only one that can tell you whether Maria made it out.**

Evacuation alerts today are a broadcast into the dark (Genasys/WEA). Nobody closes the
loop on who actually got out. NoneLeft works the phones until every person in the zone is
accounted for, and hands dispatch a priority-ranked list of who still needs saving.
Residents only ever touch a phone. No app. The one screen belongs to responders.

**Track: No App** — residents interact purely by voice (phone calls); the only screen belongs to responders.
**Statuses:** `OUT` · `NEEDS RIDE` · `NEEDS MEDICAL` · `NEEDS HELP` · `NO ANSWER → WELFARE CHECK`

## What it does

When an evacuation order hits a zone, NoneLeft places calls to every resident on file:

- **Voice call script** (Twilio): greeting → menu → speech or DTMF (press 1/2/3) → spoken confirmation.
- **Unresponsive residents get 3 menu attempts**, then a welfare alert: *"A responder has been
  dispatched to check on you."* Status flips to `WELFARE_CHECK` (highest priority, red).
- **Dispatch board** (live): census of who's OUT / needs ride / needs medical / unaccounted,
  ranked by a vulnerability-weighted priority score (age, oxygen, mobility, bedridden).
- **Family notifications** (real iMessage): the moment a resident is accounted for, their
  emergency contact gets a text — *"Maria Gonzalez is OUT and safe."*
- **No-answer ladder:** 3 call attempts → red-flagged for an in-person welfare check.

Built in ~4 hours at c0mpiled-16 (UCSD). Python standard library only — no frameworks,
no external services required to run the core census.

## Run it

```bash
cd noneleft
python3 app.py
```

- **Dispatch board** (project this): http://localhost:8000/
- **Resident phone simulator** (teammate opens on their phone/laptop): http://localhost:8000/phone
  (same Wi-Fi: use `http://<this-mac's-ip>:8000/phone` — get the IP with `ipconfig getifaddr en0`)
- **Real iMessage family notification** lands on your actual phone (needs your iCloud email — see below).

No installs, no API keys, no external services — nothing can go down mid-demo.

### Optional: real phone calls (Twilio)

Copy `.env.example` (create it from the values below), fill in Twilio trial credentials,
expose the app over a public URL (e.g. `cloudflared tunnel --url http://localhost:8000`
or `ssh -R 80:localhost:8000 nokey@serveo.net`), and set `PUBLIC_URL` to it.

```
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_NUMBER=
PUBLIC_URL=
```

`resident_phones.json` maps resident IDs → phone numbers to call for real:
`{"r1": "+1..."}`. The board then shows a 📞 **call** button per mapped resident.

## Demo runbook (~90 seconds on stage)

1. **Board on screen** — "12 residents in the zone. Zero accounted for."
2. **Press ▶ TRIGGER EVACUATION ORDER.** Phones start ringing across the room.
3. **Teammate answers as Maria** (81, on oxygen, no car) on the phone panel:
   - Quick-reply: *"I need a ride — I have no car."*
   - Agent: *"Understood — a transit team has been dispatched. Stay by your phone."*
   - Board flips Maria → **NEEDS RIDE**, she sits at the top of the priority list.
4. **Your phone buzzes** — real iMessage: *"NoneLeft | Evacuation update: Maria Gonzalez status: needs ride. Responders have been notified."* Hold it up.
5. Second resident answers *"I'm out and safe"* → board goes green, census ticks up.
6. **The kill shot:** residents that never answer ring 3x, then flip to red
   **WELFARE CHECK** — "This is who the responders go find first."
7. Close: *"Detection is solved — ALERTCalifornia tells us a fire started. NoneLeft is the missing census: 12 of 12 people, accounted for, ranked by who needs saving first. When NoneLeft hits zero, everyone made it out."*

## One-time setup (only for the real-iMessage leg)

1. Set `family_email` in `config.json` (the contact who should receive real notifications).
2. This Mac: open the **Messages** app once, confirm it can reach your phone (same Apple ID).
3. Trigger a test: `python3 send_imessage.py <email> "NoneLeft test"`.
   A macOS popup appears → click **OK/Allow** (System Settings → Privacy & Security → Automation).
4. From then on, every status change for a resident with family info pings the real phone.

If the popup is denied or Messages is signed out, the demo still works 100% —
the log line on the board shows the notification instead.

## Test commands

```bash
curl -X POST localhost:8000/api/trigger        # start the calling campaign
curl -X POST localhost:8000/api/reset          # reset for rehearsal
curl -X POST localhost:8000/api/test-imessage  # verify the real-iMessage leg
curl -X POST -d '{"rid":"r1"}' -H "Content-Type: application/json" localhost:8000/api/call-real  # real Twilio call
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Dispatch board |
| GET | `/phone` | Resident phone simulator |
| GET | `/api/state` | Full census state (JSON) |
| POST | `/api/trigger` | Start the calling campaign |
| POST | `/api/reset` | Reset all state |
| POST | `/api/call/{id}/answer` | Answer a call (simulator) |
| POST | `/api/call/{id}/reply` | Reply as resident (simulator) |
| POST | `/api/call-real` | Place a real Twilio call (`rid`) |
| GET/POST | `/twiml/start` | TwiML: greeting + menu (Twilio fetches) |
| POST | `/twiml/reply` | TwiML: classify response, 3-attempt ladder |
| POST | `/api/test-imessage` | Send a test family notification |

## How it maps to the challenge

- **No App (primary track):** residents interact purely by voice; if users have to look at a
  screen, it doesn't count — Maria is 81 on a landline, and the app is precisely what she
  doesn't have.
- **Dispatch:** the trigger is the evacuation order feed (Genasys zone / CAL FIRE / NWS),
  and the output routes physical help — rides, medical response, welfare checks.
- **Unsupervised:** the agent runs the whole census alone — calling, classifying, retrying,
  escalating — and only interrupts a human (dispatch / family) when a decision needs them.
- **Why now, why us:** CBS reported a Santa Rosa woman died because her alert never reached her;
  California has no registry of who needs help evacuating (CA Commission on Ageing, Nov 2025).
  Headcount/EmergencyOS do roll-call for office buildings. Nobody does it for neighborhoods.

## FAQ (for judges)

- **Why not an app?** The people who die in evacuations are exactly the people without apps:
  seniors on landlines, the disabled, the unhoused. Voice is the only universal interface.
- **Isn't this reverse-911?** Reverse-911 is a broadcast — it can't hear "I can't leave."
  NoneLeft is the reconciliation layer *after* the alert.
- **Liability?** The agent never gives advice and never calls 911 itself. It classifies and
  hands humans a ranked list. Responders stay the decision-makers.
- **What about people who answer but can't respond?** After 3 menu attempts, the resident is
  flagged `WELFARE_CHECK` — we don't guess, we send a person.
- **Voice rails?** Twilio is commodity infrastructure. The product is the census engine —
  the state machine, the retry ladder, the priority ranking — which is what we built.
- **Business?** Counties already pay Genasys, Zonehaven, and mass-notification vendors.
  Accountability-after-alert is the missing module in that same procurement.

## Submission description (paste-ready)

> When an evacuation order goes out, NoneLeft calls every resident until each one is accounted for — are you out, do you need a ride, or is this a medical emergency? Dispatch gets a live list of who's still inside and who to find first, and families get a text the moment their loved one is safe.
>
> Evacuation alerts are a one-way broadcast into the dark — and people die in the silence
> after them (Linda Tunis, Santa Rosa; California's own commission found shelters arrive with
> zero data on who needed help). NoneLeft closes that loop: a live census of who's still
> inside, ranked by who needs saving first. Residents never see an app — the only screen
> belongs to the people saving them.
