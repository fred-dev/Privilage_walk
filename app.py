"""
Privilege Walk - multi-classroom server.

Design notes (why things are the way they are):

* Many teachers can run sessions at the same time. Every session has its own
  id, join QR code, teacher key and participant list; nothing is shared.
* Students are anonymous. On join they get a random alias ("Teal Fox") and an
  emoji so they can find themselves on the projector, plus a private token
  (stored on their device) and a short rejoin code (shown on their screen)
  so they can come back as the same person after losing connection,
  closing the tab, or their phone going to sleep.
* Answers are stored per question index, so a retry or double tap can never
  count twice and a missed question can never shift later answers.
* The walk never gets stuck on one student: students whose device has gone
  quiet are not waited for, an optional per-question timer moves things on,
  and the teacher can always skip ahead or finish.
* All state lives in one process (gunicorn must run a single worker, see
  gunicorn.conf.py) behind one lock, and is periodically saved to disk so a
  worker restart does not lose running classes.
"""

import os
import json
import time
import random
import secrets
import logging
import threading
from functools import wraps
from io import BytesIO

from flask import Flask, render_template, request, jsonify, send_file, redirect, make_response
from werkzeug.middleware.proxy_fix import ProxyFix
import qrcode

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Render (and most hosts) sit behind a proxy; trust its scheme/host headers so
# generated join links use the public https URL.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

DATA_FILE = os.environ.get('PW_DATA_FILE', 'sessions.json')
SESSION_TTL = int(os.environ.get('PW_SESSION_TTL_HOURS', '24')) * 3600
SAVE_INTERVAL = 2.0          # seconds between background saves when dirty
ACTIVE_WINDOW = 20.0         # a student polling within this window counts as "here"
AUTO_ADVANCE_GRACE = 3.0     # pause after everyone answered, so the room sees the last step
MAX_SESSIONS = 500
MAX_PARTICIPANTS = 200
REJOIN_MAX_FAILS = 30        # failed rejoin-code attempts per IP per session (a class often shares one IP)...
REJOIN_FAIL_WINDOW = 300     # ...per this many seconds
TIMER_CHOICES = (0, 15, 20, 30, 45, 60, 90, 120)
STRAGGLER_CHOICES = (0, 10, 20, 30, 60)
STRAGGLER_SHARE = 0.75       # once this share of connected students answered, start the straggler countdown

ADJECTIVES = [
    'Amber', 'Azure', 'Brave', 'Bright', 'Calm', 'Clever', 'Coral', 'Cosmic',
    'Crimson', 'Gentle', 'Golden', 'Happy', 'Indigo', 'Jade', 'Jolly', 'Kind',
    'Lively', 'Lucky', 'Lunar', 'Mellow', 'Misty', 'Noble', 'Olive', 'Plum',
    'Quick', 'Rosy', 'Ruby', 'Sandy', 'Silver', 'Sunny', 'Swift', 'Teal',
    'Velvet', 'Violet', 'Witty', 'Zesty',
]
ANIMALS = [
    ('Badger', '🦡'), ('Bear', '🐻'), ('Bee', '🐝'), ('Cat', '🐱'),
    ('Crab', '🦀'), ('Deer', '🦌'), ('Dolphin', '🐬'), ('Duck', '🦆'),
    ('Eagle', '🦅'), ('Fox', '🦊'), ('Frog', '🐸'), ('Giraffe', '🦒'),
    ('Hedgehog', '🦔'), ('Koala', '🐨'), ('Lion', '🦁'), ('Monkey', '🐵'),
    ('Octopus', '🐙'), ('Otter', '🦦'), ('Owl', '🦉'), ('Panda', '🐼'),
    ('Parrot', '🦜'), ('Penguin', '🐧'), ('Rabbit', '🐰'), ('Seal', '🦭'),
    ('Shark', '🦈'), ('Sloth', '🦥'), ('Snail', '🐌'), ('Tiger', '🐯'),
    ('Turtle', '🐢'), ('Unicorn', '🦄'), ('Whale', '🐳'), ('Wolf', '🐺'),
    ('Zebra', '🦓'), ('Llama', '🦙'), ('Hippo', '🦛'), ('Swan', '🦢'),
]
# Rejoin codes avoid look-alike characters (0/O, 1/I/L) so they can be read aloud.
CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

lock = threading.RLock()
active_sessions = {}      # session_id -> session dict (persisted)
_token_index = {}         # token -> (session_id, pid)   (rebuilt on load)
_rejoin_failures = {}     # (session_id, ip) -> [timestamps]
_qr_cache = {}            # (session_id, join_url) -> png bytes
_dirty = False
_saver_started = False


def now():
    return time.time()


def mark_dirty():
    global _dirty
    _dirty = True


def load_questions():
    """Load question texts from questions.json, with a built-in fallback."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'questions.json'), 'r') as f:
            data = json.load(f)
        questions = [q['text'] if isinstance(q, dict) else str(q) for q in data['questions']]
        questions = [q for q in questions if q.strip()]
        if questions:
            return questions
        raise ValueError('questions.json has no questions')
    except Exception as e:
        logger.error(f"Error loading questions, using built-in list: {e}")
        return [
            "I have rarely been judged negatively or discriminated against because of my body size.",
            "My mental health is generally robust, and it has never seriously limited my opportunities.",
            "I am neurotypical, and my ways of thinking and learning are usually supported in school or work.",
            "My sexuality has never caused me to be excluded, harassed, or made invisible.",
            "I am able-bodied, and I do not face barriers to everyday activities, buildings, or services.",
            "I have access to post-secondary education and am likely to complete it.",
            "My skin colour has never caused me to be unfairly treated or stereotyped.",
            "I am a citizen or permanent resident and do not have to worry about losing my right to remain in this country.",
            "My gender identity is cisgender and has never been a barrier to being accepted or respected.",
            "English is my first or fluent language, and it has always been an advantage for me in education and society.",
            "I grew up in a family that was financially secure and could afford most of what we needed.",
            "I have always had secure housing and have never been at risk of homelessness."
        ]


def new_session(name=''):
    sid = secrets.token_hex(4)
    while sid in active_sessions:
        sid = secrets.token_hex(4)
    t = now()
    return {
        'id': sid,
        'name': (name or '').strip()[:80],
        'host_key': secrets.token_urlsafe(18),
        'created_at': t,
        'last_activity': t,
        'status': 'waiting',          # waiting | active | finished
        'current': 0,                 # index of the open question
        'question_started_at': None,
        'paused_at': None,            # set while the teacher has paused the walk
        'advance_at': None,           # scheduled auto-advance time
        'hold_auto_for': None,        # question index where "everyone answered" auto-advance is suppressed
        'finished_at': None,
        'straggler_since': None,      # when the "most have answered" countdown started
        'settings': {'timer': 0, 'auto_advance': True, 'joining_open': True, 'straggler_wait': 20},
        'questions': load_questions(),
        'participants': {},           # pid -> participant
        'next_pid': 1,
    }


def score_of(p):
    return sum(1 if a == 'agree' else -1 for a in p['answers'].values() if a in ('agree', 'disagree'))


def is_connected(p, t):
    return (t - p.get('last_seen', 0)) <= ACTIVE_WINDOW


def unique_alias(s):
    used = {p['alias'] for p in s['participants'].values()}
    used_emoji = {p['emoji'] for p in s['participants'].values()}
    combos = [(a, an) for a in ADJECTIVES for an in ANIMALS]
    random.shuffle(combos)
    # Prefer an animal nobody has yet, so in a normal-sized class the emoji
    # alone is enough for a student to spot themselves on a crowded screen.
    combos.sort(key=lambda c: c[1][1] in used_emoji)
    for adj, (animal, emoji) in combos:
        alias = f'{adj} {animal}'
        if alias not in used:
            return alias, emoji
    # Practically unreachable (over 1000 combos), but never fail a join.
    adj, (animal, emoji) = random.choice(ADJECTIVES), random.choice(ANIMALS)
    n = 2
    while f'{adj} {animal} {n}' in used:
        n += 1
    return f'{adj} {animal} {n}', emoji


def unique_code(s):
    used = {p['code'] for p in s['participants'].values()}
    while True:
        code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(4))
        if code not in used:
            return code


def rebuild_indexes():
    _token_index.clear()
    for sid, s in active_sessions.items():
        for pid, p in s['participants'].items():
            _token_index[p['token']] = (sid, pid)


# ---------------------------------------------------------------------------
# Walk progression (always called with the lock held)
# ---------------------------------------------------------------------------

def advance(s, reason):
    t = now()
    s['advance_at'] = None
    s['paused_at'] = None
    s['straggler_since'] = None
    if s['current'] < len(s['questions']) - 1:
        s['current'] += 1
        s['question_started_at'] = t
        logger.info(f"SESSION {s['id']}: advanced to Q{s['current'] + 1} ({reason})")
    else:
        s['status'] = 'finished'
        s['finished_at'] = t
        logger.info(f"SESSION {s['id']}: finished ({reason})")
    s['last_activity'] = t
    mark_dirty()


def answered_counts(s, t):
    """(answered, connected_waiting_for, total) for the open question."""
    key = str(s['current'])
    answered = 0
    waiting = 0
    for p in s['participants'].values():
        if key in p['answers']:
            answered += 1
        elif is_connected(p, t):
            waiting += 1
    return answered, waiting, len(s['participants'])


def tick(s):
    """Lazily apply timers. Every request touching a session calls this, and
    the background thread calls it too, so nothing depends on any one client."""
    if s['status'] != 'active' or s['paused_at'] is not None:
        return
    t = now()
    timer = s['settings'].get('timer') or 0
    if timer and s['question_started_at'] and t >= s['question_started_at'] + timer:
        advance(s, 'timer')
        return
    if s['settings'].get('auto_advance') and s['hold_auto_for'] != s['current']:
        answered, waiting, _ = answered_counts(s, t)
        if answered > 0 and waiting == 0:
            if s['advance_at'] is None:
                s['advance_at'] = t + AUTO_ADVANCE_GRACE
            elif t >= s['advance_at']:
                advance(s, 'everyone answered')
            return
        s['advance_at'] = None   # someone (re)connected without answering
        # Most of the room has answered: give the rest a short, visible
        # countdown instead of waiting forever for someone who won't answer.
        wait = s['settings'].get('straggler_wait') or 0
        if wait and answered > 0 and answered >= STRAGGLER_SHARE * (answered + waiting):
            if s.get('straggler_since') is None:
                s['straggler_since'] = t
            elif t >= s['straggler_since'] + wait:
                advance(s, 'waited for stragglers')
            return
    s['advance_at'] = None
    s['straggler_since'] = None


def time_left(s, t):
    """Seconds until the question closes on its own (timer or straggler countdown)."""
    if s['status'] != 'active':
        return None
    ref = s['paused_at'] if s['paused_at'] is not None else t
    deadlines = []
    timer = s['settings'].get('timer') or 0
    if timer and s['question_started_at']:
        deadlines.append(s['question_started_at'] + timer)
    wait = s['settings'].get('straggler_wait') or 0
    if wait and s.get('straggler_since') is not None and s['paused_at'] is None:
        deadlines.append(s['straggler_since'] + wait)
    if not deadlines:
        return None
    return max(0, round(min(deadlines) - ref))


def rankings(s):
    """Competition ranking: equal scores share a rank (1, 2, 2, 4)."""
    scores = sorted((score_of(p) for p in s['participants'].values()), reverse=True)
    first_index = {}
    for i, sc in enumerate(scores):
        first_index.setdefault(sc, i + 1)
    return first_index


def question_payload(s, t):
    total = len(s['questions'])
    q = None
    if s['status'] == 'active':
        q = {
            'index': s['current'],
            'number': s['current'] + 1,
            'text': s['questions'][s['current']],
        }
    return {
        'status': s['status'],
        'total_questions': total,
        'question': q,
        'paused': s['paused_at'] is not None,
        'time_left': time_left(s, t),
        'advance_in': max(0, round(s['advance_at'] - t, 1)) if s['advance_at'] else None,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_sessions_to_file():
    global _dirty
    if not DATA_FILE:
        return
    with lock:
        snapshot = json.dumps(active_sessions)
        _dirty = False
    tmp = f'{DATA_FILE}.tmp'
    try:
        with open(tmp, 'w') as f:
            f.write(snapshot)
        os.replace(tmp, DATA_FILE)  # atomic: a crash mid-write never corrupts the file
    except Exception as e:
        logger.error(f"Error saving sessions: {e}")


def load_sessions_from_file():
    if not DATA_FILE or not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        loaded = 0
        with lock:
            for sid, s in data.items():
                if isinstance(s, dict) and 'participants' in s and 'host_key' in s:
                    active_sessions[sid] = s
                    loaded += 1
            rebuild_indexes()
        logger.info(f"Loaded {loaded} sessions from {DATA_FILE}")
    except Exception as e:
        logger.error(f"Could not load {DATA_FILE} ({e}); starting empty")
        try:
            os.replace(DATA_FILE, f'{DATA_FILE}.corrupt')
        except Exception:
            pass


def cleanup_old_sessions():
    cutoff = now() - SESSION_TTL
    with lock:
        stale = [sid for sid, s in active_sessions.items() if s.get('last_activity', 0) < cutoff]
        for sid in stale:
            for p in active_sessions[sid]['participants'].values():
                _token_index.pop(p['token'], None)
            del active_sessions[sid]
            logger.info(f"Cleaned up old session {sid}")
        if stale:
            mark_dirty()
    return len(stale)


def _background_loop():
    last_cleanup = 0
    while True:
        time.sleep(1.0)
        try:
            with lock:
                for s in list(active_sessions.values()):
                    tick(s)
            if _dirty:
                save_sessions_to_file()
            if now() - last_cleanup > 600:
                last_cleanup = now()
                cleanup_old_sessions()
        except Exception as e:  # never let the background thread die
            logger.error(f"Background loop error: {e}")


def start_background():
    global _saver_started
    with lock:
        if _saver_started:
            return
        _saver_started = True
    threading.Thread(target=_background_loop, name='pw-background', daemon=True).start()


load_sessions_from_file()
if os.environ.get('PW_NO_BACKGROUND') != '1':
    start_background()


# ---------------------------------------------------------------------------
# Helpers for routes
# ---------------------------------------------------------------------------

def no_store(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def api_error(message, code, **extra):
    return no_store(make_response(jsonify({'error': message, **extra}), code))


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def host_cookie_name(sid):
    return f'pw_host_{sid}'


def participant_cookie_name(sid):
    return f'pw_p_{sid}'


def is_host(s):
    key = request.headers.get('X-Host-Key') or request.cookies.get(host_cookie_name(s['id']))
    return bool(key) and secrets.compare_digest(key, s['host_key'])


def set_cookie(resp, name, value):
    resp.set_cookie(name, value, max_age=SESSION_TTL + 3600, httponly=True,
                    samesite='Lax', secure=request.is_secure)


def get_base_url():
    configured = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    if configured:
        return configured
    if os.environ.get('LOCAL_TESTING', 'false').lower() == 'true':
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
            sock.close()
            return f'http://{local_ip}:{os.environ.get("PORT", 5001)}'
        except Exception as e:
            logger.warning(f"Could not detect local IP: {e}")
    return request.url_root.rstrip('/')


def join_url_for(sid):
    return f'{get_base_url()}/join/{sid}'


def with_session(host=False):
    """Look up the session, apply timers, optionally require the teacher key."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(session_id, *args, **kwargs):
            with lock:
                s = active_sessions.get(session_id)
                if s is None:
                    return api_error('Session not found. It may have expired.', 404, gone=True)
                if host and not is_host(s):
                    return api_error('Teacher access required for this session.', 403)
                tick(s)
                return fn(s, *args, **kwargs)
        return wrapper
    return decorator


def participant_from_request(s):
    token = request.headers.get('X-Participant-Token') or request.cookies.get(participant_cookie_name(s['id']))
    if not token:
        return None
    hit = _token_index.get(token)
    if not hit or hit[0] != s['id']:
        return None
    return s['participants'].get(hit[1])


def add_participant(s):
    t = now()
    alias, emoji = unique_alias(s)
    pid = f"p{s['next_pid']}"
    s['next_pid'] += 1
    p = {
        'pid': pid,
        'token': secrets.token_urlsafe(18),
        'code': unique_code(s),
        'alias': alias,
        'emoji': emoji,
        'joined_at': t,
        'last_seen': t,
        'answers': {},      # str(question index) -> 'agree' | 'disagree'
    }
    s['participants'][pid] = p
    _token_index[p['token']] = (s['id'], pid)
    s['last_activity'] = t
    mark_dirty()
    logger.info(f"SESSION {s['id']}: joined {pid} ({len(s['participants'])} participants)")
    return p


def participant_identity(s, p):
    return {
        'pid': p['pid'], 'alias': p['alias'], 'emoji': p['emoji'],
        'code': p['code'], 'token': p['token'], 'session_id': s['id'],
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    if 'Render' in request.headers.get('User-Agent', ''):
        return jsonify({'status': 'healthy', 'timestamp': now()})
    return render_template('index.html')


@app.route('/create_session', methods=['POST'])
def create_session():
    data = request.get_json(silent=True) or request.form or {}
    with lock:
        if len(active_sessions) >= MAX_SESSIONS:
            cleanup_old_sessions()
            if len(active_sessions) >= MAX_SESSIONS:
                return api_error('The server is at capacity. Please try again later.', 503)
        s = new_session(data.get('session_name', ''))
        active_sessions[s['id']] = s
        mark_dirty()
        sid, key = s['id'], s['host_key']
    logger.info(f"SESSION {sid}: created")
    resp = jsonify({'session_id': sid, 'host_key': key,
                    'instructor_url': f'/instructor/{sid}', 'name': s['name']})
    set_cookie(resp, host_cookie_name(sid), key)
    return no_store(resp)


@app.route('/instructor/<session_id>')
def instructor_view(session_id):
    with lock:
        s = active_sessions.get(session_id)
        if s is None:
            return render_template('message.html', title='Session not found',
                                   message='This session does not exist or has expired. Create a new one from the home page.'), 404
        key = request.args.get('key')
        if key:
            if not secrets.compare_digest(key, s['host_key']):
                return render_template('message.html', title='Wrong teacher link',
                                       message='That teacher link is not valid for this session.'), 403
            # Store the key in a cookie and drop it from the address bar so it
            # is not visible on the projector.
            resp = redirect(f'/instructor/{session_id}')
            set_cookie(resp, host_cookie_name(session_id), key)
            return resp
        if not is_host(s):
            return render_template('message.html', title='Teacher access needed',
                                   message='This is the teacher screen for a session. Open it using the teacher link you saved when you created the session (or from the same browser you created it in). Students should scan the QR code instead.'), 403
        name = s['name']
        key = s['host_key']
    return no_store(make_response(render_template(
        'instructor.html', session_id=session_id, session_name=name or 'Privilege Walk',
        join_url=join_url_for(session_id), host_key=key, timer_choices=TIMER_CHOICES,
        straggler_choices=STRAGGLER_CHOICES)))


@app.route('/instructor/test')
def instructor_test():
    return render_template('instructor_test.html', session_name="Privilege Walk Test Mode",
                           base_url=get_base_url())


@app.route('/join/<session_id>')
@app.route('/s/<session_id>')
@app.route('/student/<session_id>')
def student_view(session_id):
    """One page handles joining, answering, reconnecting and the final screen."""
    with lock:
        s = active_sessions.get(session_id)
        if s is None:
            return render_template('message.html', title='Session not found',
                                   message='This session does not exist or has expired. Ask your teacher for the current QR code.'), 404
        name = s['name']
    return no_store(make_response(render_template('student.html', session_id=session_id, session_name=name)))


@app.route('/qr/<session_id>')
def qr_code(session_id):
    with lock:
        if session_id not in active_sessions:
            return "Session not found", 404
    url = join_url_for(session_id)
    png = _qr_cache.get((session_id, url))
    if png is None:
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=3)
        qr.add_data(url)
        qr.make(fit=True)
        buf = BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buf, 'PNG')
        png = buf.getvalue()
        if len(_qr_cache) > 1000:
            _qr_cache.clear()
        _qr_cache[(session_id, url)] = png
    resp = send_file(BytesIO(png), mimetype='image/png')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


# ---------------------------------------------------------------------------
# Student API
# ---------------------------------------------------------------------------

@app.route('/api/s/<session_id>/join', methods=['POST'])
@with_session()
def api_join(s):
    # Already joined from this device? Hand back the same identity.
    p = participant_from_request(s)
    if p is None:
        if not s['settings']['joining_open']:
            return api_error('The teacher has closed joining for this session. If you joined earlier, use your rejoin code.', 403, closed=True)
        if len(s['participants']) >= MAX_PARTICIPANTS:
            return api_error('This session is full.', 403)
        p = add_participant(s)
    p['last_seen'] = now()
    resp = jsonify({'success': True, 'me': participant_identity(s, p)})
    set_cookie(resp, participant_cookie_name(s['id']), p['token'])
    return no_store(resp)


@app.route('/api/s/<session_id>/rejoin', methods=['POST'])
@with_session()
def api_rejoin(s):
    code = ''.join(ch for ch in str(json_body().get('code', '')).upper() if ch.isalnum())
    ip = request.remote_addr or '?'
    key = (s['id'], ip)
    t = now()
    fails = [x for x in _rejoin_failures.get(key, []) if t - x < REJOIN_FAIL_WINDOW]
    if len(fails) >= REJOIN_MAX_FAILS:
        return api_error('Too many attempts. Wait a few minutes or ask your teacher.', 429)
    p = next((p for p in s['participants'].values() if p['code'] == code), None) if len(code) == 4 else None
    if p is None:
        fails.append(t)
        _rejoin_failures[key] = fails
        return api_error('That code was not found in this session. Check it and try again.', 404)
    _rejoin_failures.pop(key, None)
    p['last_seen'] = t
    logger.info(f"SESSION {s['id']}: {p['pid']} rejoined with code")
    resp = jsonify({'success': True, 'me': participant_identity(s, p)})
    set_cookie(resp, participant_cookie_name(s['id']), p['token'])
    return no_store(resp)


@app.route('/api/s/<session_id>/state')
@with_session()
def api_student_state(s):
    t = now()
    p = participant_from_request(s)
    payload = question_payload(s, t)
    payload['session_name'] = s['name']
    payload['joining_open'] = s['settings']['joining_open']
    if p is None:
        payload['me'] = None
        return no_store(jsonify(payload))
    p['last_seen'] = t
    score = score_of(p)
    ranks = rankings(s)
    me = participant_identity(s, p)
    me.update({
        'score': score,
        'rank': ranks.get(score),
        'participants': len(s['participants']),
        'answer': p['answers'].get(str(s['current'])) if s['status'] == 'active' else None,
        'answered_count': len(p['answers']),
    })
    payload['me'] = me
    if s['status'] == 'active':
        answered, waiting, total = answered_counts(s, t)
        payload['progress'] = {'answered': answered, 'total': total}
    return no_store(jsonify(payload))


@app.route('/api/s/<session_id>/answer', methods=['POST'])
@with_session()
def api_answer(s):
    data = json_body()
    p = participant_from_request(s)
    if p is None:
        return api_error('You are not part of this session on this device. Rejoin to continue.', 401, rejoin=True)
    answer = data.get('answer')
    if answer not in ('agree', 'disagree'):
        return api_error('Answer must be agree or disagree.', 400)
    try:
        index = int(data.get('question_index'))
    except (TypeError, ValueError):
        return api_error('Missing question number.', 400)
    p['last_seen'] = now()
    if s['status'] != 'active' or s['paused_at'] is not None or index != s['current']:
        # Stale answer (question moved on while offline): tell the client the
        # real state instead of recording it against the wrong question.
        return api_error('That question is no longer open.', 409, stale=True, **question_payload(s, now()))
    # Keyed by question: retries and double taps are harmless, and a change
    # of mind replaces the answer for this question only.
    p['answers'][str(index)] = answer
    s['last_activity'] = now()
    mark_dirty()
    tick(s)
    return no_store(jsonify({'success': True, 'answer': answer, 'question_index': index, 'score': score_of(p)}))


# ---------------------------------------------------------------------------
# Teacher API
# ---------------------------------------------------------------------------

@app.route('/api/h/<session_id>/state')
@with_session(host=True)
def api_host_state(s):
    t = now()
    ranks = rankings(s)
    key = str(s['current'])
    people = []
    for p in sorted(s['participants'].values(), key=lambda p: p['joined_at']):
        sc = score_of(p)
        people.append({
            'pid': p['pid'], 'alias': p['alias'], 'emoji': p['emoji'],
            'score': sc, 'rank': ranks.get(sc),
            'answered': s['status'] == 'active' and key in p['answers'],
            'connected': is_connected(p, t),
        })
    payload = question_payload(s, t)
    answered, waiting, total = answered_counts(s, t)
    payload.update({
        'session_id': s['id'],
        'name': s['name'],
        'current': s['current'],
        'settings': s['settings'],
        'participants': people,
        'counts': {
            'total': total,
            'connected': sum(1 for p in people if p['connected']),
            'answered': answered if s['status'] == 'active' else 0,
            'waiting_for': waiting if s['status'] == 'active' else 0,
        },
        'auto_held': s['hold_auto_for'] == s['current'],
        'straggler_countdown': s.get('straggler_since') is not None,
        'server_time': t,
    })
    return no_store(jsonify(payload))


def host_action(fn):
    return app.route(f'/api/h/<session_id>/{fn.__name__[5:]}', methods=['POST'],
                     endpoint=fn.__name__)(with_session(host=True)(fn))


def host_ok(s):
    s['last_activity'] = now()
    mark_dirty()
    tick(s)
    return no_store(jsonify({'success': True, **question_payload(s, now())}))


@host_action
def host_start(s):
    if s['status'] == 'active':
        return host_ok(s)
    s['status'] = 'active'
    s['current'] = 0
    s['question_started_at'] = now()
    s['paused_at'] = None
    s['advance_at'] = None
    s['hold_auto_for'] = None
    s['finished_at'] = None
    s['straggler_since'] = None
    for p in s['participants'].values():
        p['answers'] = {}
    logger.info(f"SESSION {s['id']}: started with {len(s['participants'])} participants")
    return host_ok(s)


@host_action
def host_next(s):
    if s['status'] != 'active':
        return api_error('The walk is not running.', 400)
    # Guard against a double click skipping two questions.
    expected = json_body().get('from_index')
    if expected is not None and str(expected) != str(s['current']):
        return host_ok(s)
    advance(s, 'teacher')
    return host_ok(s)


@host_action
def host_back(s):
    if s['status'] == 'finished':
        s['status'] = 'active'
        s['finished_at'] = None
    elif s['status'] != 'active' or s['current'] == 0:
        return api_error('Already at the first question.', 400)
    else:
        s['current'] -= 1
    s['question_started_at'] = now()
    s['paused_at'] = None
    s['advance_at'] = None
    # Everyone may already have answered this one; don't bounce straight forward.
    s['hold_auto_for'] = s['current']
    s['straggler_since'] = None
    return host_ok(s)


@host_action
def host_pause(s):
    if s['status'] != 'active':
        return api_error('The walk is not running.', 400)
    if s['paused_at'] is None:
        s['paused_at'] = now()
        s['advance_at'] = None
    return host_ok(s)


@host_action
def host_resume(s):
    if s['paused_at'] is not None:
        if s['question_started_at']:
            s['question_started_at'] += now() - s['paused_at']
        s['paused_at'] = None
        s['straggler_since'] = None
    return host_ok(s)


@host_action
def host_finish(s):
    if s['status'] == 'active':
        s['current'] = len(s['questions']) - 1
        advance(s, 'teacher ended walk')
    return host_ok(s)


@host_action
def host_reset(s):
    s.update({'status': 'waiting', 'current': 0, 'question_started_at': None, 'paused_at': None,
              'advance_at': None, 'hold_auto_for': None, 'finished_at': None, 'straggler_since': None})
    for p in s['participants'].values():
        p['answers'] = {}
    logger.info(f"SESSION {s['id']}: reset")
    return host_ok(s)


@host_action
def host_settings(s):
    data = json_body()
    st = s['settings']
    if 'timer' in data:
        try:
            timer = int(data['timer'])
        except (TypeError, ValueError):
            return api_error('Invalid timer.', 400)
        if timer < 0 or timer > 600:
            return api_error('Invalid timer.', 400)
        st['timer'] = timer
        if s['status'] == 'active':
            s['question_started_at'] = now()   # new timer applies from now
    if 'straggler_wait' in data:
        try:
            wait = int(data['straggler_wait'])
        except (TypeError, ValueError):
            return api_error('Invalid wait.', 400)
        if wait < 0 or wait > 600:
            return api_error('Invalid wait.', 400)
        st['straggler_wait'] = wait
        s['straggler_since'] = None
    if 'auto_advance' in data:
        st['auto_advance'] = bool(data['auto_advance'])
    if 'joining_open' in data:
        st['joining_open'] = bool(data['joining_open'])
    if 'name' in data:
        s['name'] = str(data['name']).strip()[:80]
    return host_ok(s)


@host_action
def host_remove(s):
    pid = json_body().get('pid')
    p = s['participants'].pop(pid, None)
    if p is None:
        return api_error('Participant not found.', 404)
    _token_index.pop(p['token'], None)
    logger.info(f"SESSION {s['id']}: removed {pid}")
    return host_ok(s)


@app.route('/api/h/<session_id>/export.csv')
@with_session(host=True)
def host_export(s):
    lines = ['alias,score,' + ','.join(f'Q{i + 1}' for i in range(len(s['questions'])))]
    for p in sorted(s['participants'].values(), key=score_of, reverse=True):
        cells = [p['answers'].get(str(i), '') for i in range(len(s['questions']))]
        lines.append(f"{p['alias']},{score_of(p)}," + ','.join(cells))
    resp = make_response('\n'.join(lines) + '\n')
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=privilege-walk-{s["id"]}.csv'
    return no_store(resp)


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------

@app.route('/health')
def health_check():
    with lock:
        return jsonify({
            'status': 'healthy',
            'timestamp': now(),
            'active_sessions': len(active_sessions),
            'total_users': sum(len(s['participants']) for s in active_sessions.values()),
        })


@app.route('/cleanup')
def cleanup_endpoint():
    removed = cleanup_old_sessions()
    with lock:
        count = len(active_sessions)
    return jsonify({'status': 'success', 'removed': removed, 'active_sessions': count})


@app.errorhandler(500)
def internal_error(e):
    if request.path.startswith('/api/'):
        return api_error('Server error, please retry.', 500)
    return render_template('message.html', title='Something went wrong',
                           message='Please reload the page. Your progress is saved.'), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
