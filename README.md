# NoneLeft — the evacuation census agent

**Every system tonight will tell you a fire started. This is the only one that can tell you whether Maria made it out.**

Evacuation alerts today are a broadcast into the dark (Genasys/WEA). Nobody closes the
loop on who actually got out. NoneLeft works the phones until every person in the zone is
accounted for, and hands dispatch a priority-ranked list of who still needs saving.
Residents only ever touch a phone. No app. The one screen belongs to responders.

**Statuses:** `OUT` · `NEEDS RIDE` · `NEEDS MEDICAL` · `NEEDS HELP` · `NO ANSWER → WELFARE CHECK`

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
7. Close: *"Detection is solved — ALERTCalifornia tells us a fire started. NoneLeft is the missing census: 12 of 12 people, accounted for, ranked by who needs saving first."*

## One-time setup (only for the real-iMessage leg)

1. Type your iCloud email to the assistant → it goes into `config.json` → `"family_email"`.
2. This Mac: open the **Messages** app once, confirm it can reach your phone (same Apple ID).
3. Trigger a test — the assistant runs `python3 send_imessage.py <email> test`.
   A macOS popup appears → click **OK/Allow** (System Settings → Privacy & Security → Automation).
4. From then on, every status change for Maria's family pings your real phone.

If the popup is denied or Messages is signed out, the demo still works 100% —
the log line on the board shows the notification instead.

## Test commands

```bash
curl -X POST localhost:8000/api/trigger        # start the calling campaign
curl -X POST localhost:8000/api/reset          # reset for rehearsal
curl -X POST localhost:8000/api/test-imessage  # verify the real-iMessage leg
```

## How it maps to the challenge

- **Invisible Interfaces:** residents interact by voice only; the screen exists for responders.
- **Live data:** the trigger is the evacuation order feed (Genasys zone / CAL FIRE / NWS) —
  wired as the campaign trigger; in the simulator the operator fires it.
- **Unsupervised:** the agent runs the whole census alone — calling, classifying, retrying,
  escalating — and only interrupts a human (dispatch / family) when a decision needs them.
- **Why now, why us:** CBS reported a Santa Rosa woman died because her alert never reached her;
  California has no registry of who needs help evacuating (CA Commission on Ageing, Nov 2025).
  Headcount/EmergencyOS do roll-call for office buildings. Nobody does it for neighborhoods.

## Submission description (paste-ready)

> Every system tonight will tell you a fire started. NoneLeft is the only one that can tell you whether Maria made it out.
>
> Evacuation alerts are a one-way broadcast into the dark — and people die in the silence after them (Linda Tunis, Santa Rosa; California's own commission found shelters arrive with zero data on who needed help). NoneLeft closes the loop: when an evacuation order hits a zone, our agent works the phones — landlines included, English and Spanish — until every resident is in one of four states: OUT, NEEDS RIDE, NEEDS MEDICAL, or after three attempts, WELFARE CHECK. Dispatch gets a live census board ranked by vulnerability: who is still inside, and who responders should reach first. Families get one real notification when their person is accounted for.
>
> Residents never see an app. The only screen belongs to the people saving them.
