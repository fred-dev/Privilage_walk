# 🚶 Privilege Walk

An interactive web app for running privilege walk activities in class. Students scan a QR code on their
phone, answer agree/disagree statements anonymously, and see the class "walk" on the projector.

Built to run **several classes at once** on unreliable school wifi with phones that go to sleep.

## How it works

### Teachers
1. Open the site and create a session (give it a name like "Sociology 101 - Section A").
   Every teacher creates their own session; each one has its own QR code and nothing is shared between them.
2. Project the teacher screen. Students scan the QR code and appear in the lobby.
3. Press **Begin**. Each statement appears on every phone and on the projector.
4. When the walk ends, look at the final positions, download a CSV, or run it again with the same students.

The teacher screen is protected: only the browser that created the session (or someone with the private
**teacher link**, under Settings) can control it. Students who type in the teacher URL get "access needed".
If your laptop restarts, reopen the site on the same browser (your sessions are listed on the home page)
or use the teacher link on another device.

### Students
- Tap **Join anonymously** and get a random name and animal, like "Teal Fox 🦊". Students see who they are
  at the top of their phone; nobody else knows which one is theirs. No names are typed or stored.
- The phone remembers who they are. If they lose wifi, close the tab, or their phone sleeps, they reopen the
  page (or rescan the QR code) and are the same person, with their answers intact.
- If they switch device or clear their browser, they enter the 4-character **rejoin code** shown on their screen.
- Answers given while offline are kept on the phone and sent automatically when the connection returns.
  An answer is locked once given (a retry or a double tap never counts twice), and the buttons stay
  locked for a moment when a new question appears so a late tap cannot land on the wrong question.

## Nobody gets stuck waiting

- **Disconnected students are not waited for.** A phone that hasn't checked in for 20 seconds (asleep, out of
  wifi, switched apps) is shown grey and the class moves on without it. When it comes back it joins the
  current question.
- **Move on when everyone connected has answered** (on by default, with a 3 second pause so the room sees the
  last step).
- **Stragglers:** once 3 in 4 connected students have answered, the rest get a short visible countdown
  (20 seconds by default, adjustable or off).
- **Optional timer** per question (off by default).
- **Next** always works, including on the last question (it becomes **Finish walk**). **Back**, **Pause** and
  **Resume** are available, and ghost entries (someone who joined twice) can be removed.
- Unanswered questions count as no step.
- Students who arrive late can join mid-walk (turn off "Allow new students to join" to lock the room).

## Running it

### Locally
```bash
pip install -r requirements.txt
python app.py                 # http://localhost:5001
```
Set `LOCAL_TESTING=true` to put your machine's LAN address in the QR code so phones on the same wifi can join.

### Production (Render)
`render.yaml` and `gunicorn.conf.py` are set up already. The start command is
`gunicorn app:app -c gunicorn.conf.py`.

**Important:** all live state is in memory in one process, so gunicorn must run exactly **one worker**
(`gunicorn.conf.py` enforces this and uses 32 threads instead). Do not raise `WEB_CONCURRENCY` or add workers.
Five classes of 35 students polling every few seconds is about 65 requests/second at ~4 ms each, well within
one worker.

State is saved to `sessions.json` every couple of seconds, so a crashed or restarted worker comes back with
every class intact. On Render's free plan the disk is wiped on redeploy, and the service sleeps after
15 minutes without traffic (the first visit then takes up to a minute). **Don't redeploy during a class,
and open the site a few minutes before class starts.** A paid instance with a persistent disk
(set `PW_DATA_FILE` to a path on it) removes both limits.

### Environment variables
| Variable | Default | Purpose |
|---|---|---|
| `PUBLIC_BASE_URL` | detected from the request | Force the URL used in QR codes, e.g. `https://privilage-walk.onrender.com` |
| `LOCAL_TESTING` | `false` | Use this machine's LAN IP in QR codes |
| `PW_DATA_FILE` | `sessions.json` | Where state is saved (empty to disable) |
| `PW_SESSION_TTL_HOURS` | `24` | Sessions unused for this long are deleted |
| `GUNICORN_THREADS` | `32` | Request threads in the single worker |

### Tests
```bash
pip install -r requirements-test.txt
python -m pytest test_app.py -v
```

## Customising questions
Edit `questions.json`. New sessions pick up the changes; running sessions keep the questions they started with.

## Privacy
- Students are identified only by a random alias. No names, emails or IP addresses are stored with answers.
- Sessions and their answers are deleted 24 hours after last use.
- The CSV export contains aliases and answers only.
