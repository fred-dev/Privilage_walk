#!/usr/bin/env python3
"""
Tests for the Privilege Walk server.
Run with: python -m pytest test_app.py -v
"""

import os
import sys

os.environ['PW_NO_BACKGROUND'] = '1'
os.environ['PW_DATA_FILE'] = ''
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import app as appmod  # noqa: E402
from app import app, active_sessions  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    active_sessions.clear()
    appmod._token_index.clear()
    appmod._rejoin_failures.clear()
    yield
    active_sessions.clear()


@pytest.fixture
def clock(monkeypatch):
    """Controllable clock so timers and connection windows can be tested."""
    t = {'now': 1_000_000.0}
    monkeypatch.setattr(appmod, 'now', lambda: t['now'])
    return t


def make_client():
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture
def host():
    return make_client()


def create(host, name='Class A'):
    r = host.post('/create_session', json={'session_name': name})
    assert r.status_code == 200
    return r.get_json()


def join(sid):
    """A fresh device (own cookie jar) joining the session."""
    c = make_client()
    r = c.post(f'/api/s/{sid}/join', json={})
    assert r.status_code == 200, r.get_json()
    return c, r.get_json()['me']


def state(c, sid, token=None):
    headers = {'X-Participant-Token': token} if token else {}
    return c.get(f'/api/s/{sid}/state', headers=headers).get_json()


def answer(c, sid, index, value='agree'):
    return c.post(f'/api/s/{sid}/answer', json={'answer': value, 'question_index': index})


def hstate(host, sid):
    r = host.get(f'/api/h/{sid}/state')
    assert r.status_code == 200
    return r.get_json()


def short_questions(sid, n=3):
    active_sessions[sid]['questions'] = [f'Q{i + 1}' for i in range(n)]


class TestSessions:
    def test_questions_load(self):
        qs = appmod.load_questions()
        assert len(qs) >= 1 and all(isinstance(q, str) for q in qs)

    def test_multiple_sessions_are_isolated(self, host):
        a = create(host, 'A')
        b = create(make_client(), 'B')
        assert a['session_id'] != b['session_id']
        ca, _ = join(a['session_id'])
        join(b['session_id'])
        join(b['session_id'])
        host.post(f"/api/h/{a['session_id']}/start", json={})
        assert active_sessions[a['session_id']]['status'] == 'active'
        assert active_sessions[b['session_id']]['status'] == 'waiting'
        assert len(active_sessions[a['session_id']]['participants']) == 1
        assert len(active_sessions[b['session_id']]['participants']) == 2

    def test_teacher_controls_need_key(self, host):
        sid = create(host)['session_id']
        student, _ = join(sid)
        assert student.post(f'/api/h/{sid}/start', json={}).status_code == 403
        assert student.get(f'/api/h/{sid}/state').status_code == 403
        assert student.get(f'/instructor/{sid}').status_code == 403
        assert host.get(f'/instructor/{sid}').status_code == 200

    def test_teacher_link_on_new_device(self, host):
        created = create(host)
        sid, key = created['session_id'], created['host_key']
        other = make_client()
        r = other.get(f'/instructor/{sid}?key={key}')
        assert r.status_code == 302 and r.headers['Location'].endswith(f'/instructor/{sid}')
        assert other.get(f'/instructor/{sid}').status_code == 200
        assert make_client().get(f'/instructor/{sid}?key=wrong').status_code == 403

    def test_qr_and_pages(self, host):
        sid = create(host)['session_id']
        assert host.get(f'/qr/{sid}').mimetype == 'image/png'
        assert host.get(f'/join/{sid}').status_code == 200
        assert host.get(f'/student/{sid}?username=legacy').status_code == 200
        assert host.get('/join/nope').status_code == 404
        assert host.get('/qr/nope').status_code == 404

    def test_public_base_url(self, host, monkeypatch):
        monkeypatch.setenv('PUBLIC_BASE_URL', 'https://walk.example.org/')
        sid = create(host)['session_id']
        assert f'https://walk.example.org/join/{sid}' in host.get(f'/instructor/{sid}').get_data(as_text=True)


class TestIdentity:
    def test_join_gives_anonymous_unique_identity(self, host):
        sid = create(host)['session_id']
        ids = [join(sid)[1] for _ in range(30)]
        assert len({i['alias'] for i in ids}) == 30
        assert len({i['code'] for i in ids}) == 30
        assert len({i['token'] for i in ids}) == 30

    def test_rejoin_same_device_returns_same_person(self, host):
        sid = create(host)['session_id']
        c, me = join(sid)
        again = c.post(f'/api/s/{sid}/join', json={}).get_json()['me']
        assert again['pid'] == me['pid']
        assert len(active_sessions[sid]['participants']) == 1

    def test_token_header_works_without_cookie(self, host):
        sid = create(host)['session_id']
        _, me = join(sid)
        fresh = make_client()
        s = state(fresh, sid, token=me['token'])
        assert s['me']['pid'] == me['pid']
        r = fresh.post(f'/api/s/{sid}/join', json={}, headers={'X-Participant-Token': me['token']})
        assert r.get_json()['me']['pid'] == me['pid']

    def test_rejoin_with_code_on_new_device(self, host):
        sid = create(host)['session_id']
        short_questions(sid)
        c, me = join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        answer(c, sid, 0, 'agree')
        new_device = make_client()
        r = new_device.post(f'/api/s/{sid}/rejoin', json={'code': me['code'].lower()})
        assert r.status_code == 200
        s = state(new_device, sid)
        assert s['me']['pid'] == me['pid'] and s['me']['score'] == 1 and s['me']['answer'] == 'agree'

    def test_rejoin_code_rate_limited(self, host):
        sid = create(host)['session_id']
        join(sid)
        c = make_client()
        codes = [p['code'] for p in active_sessions[sid]['participants'].values()]
        bad = 'ZZZZ' if 'ZZZZ' not in codes else 'YYYY'
        for _ in range(appmod.REJOIN_MAX_FAILS):
            assert c.post(f'/api/s/{sid}/rejoin', json={'code': bad}).status_code == 404
        assert c.post(f'/api/s/{sid}/rejoin', json={'code': codes[0]}).status_code == 429

    def test_closed_joining(self, host):
        sid = create(host)['session_id']
        c, me = join(sid)
        host.post(f'/api/h/{sid}/settings', json={'joining_open': False})
        r = make_client().post(f'/api/s/{sid}/join', json={})
        assert r.status_code == 403 and r.get_json()['closed']
        # Existing students can still come back.
        assert c.post(f'/api/s/{sid}/join', json={}).status_code == 200
        assert make_client().post(f'/api/s/{sid}/rejoin', json={'code': me['code']}).status_code == 200

    def test_removed_participant_must_rejoin(self, host):
        sid = create(host)['session_id']
        c, me = join(sid)
        host.post(f'/api/h/{sid}/remove', json={'pid': me['pid']})
        assert state(c, sid)['me'] is None
        host.post(f'/api/h/{sid}/start', json={})
        assert answer(c, sid, 0).status_code == 401


class TestAnswers:
    def test_answer_is_idempotent_and_changeable(self, host):
        sid = create(host)['session_id']
        c, _ = join(sid)
        join(sid)  # second student so the walk doesn't auto-advance
        host.post(f'/api/h/{sid}/start', json={})
        for _ in range(3):
            assert answer(c, sid, 0, 'agree').status_code == 200
        assert state(c, sid)['me']['score'] == 1
        answer(c, sid, 0, 'disagree')
        assert state(c, sid)['me']['score'] == -1

    def test_stale_answer_rejected(self, host):
        sid = create(host)['session_id']
        short_questions(sid)
        c, _ = join(sid)
        join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        host.post(f'/api/h/{sid}/next', json={'from_index': 0})
        r = answer(c, sid, 0)
        assert r.status_code == 409 and r.get_json()['question']['index'] == 1
        assert state(c, sid)['me']['score'] == 0

    def test_missed_question_does_not_shift_later_answers(self, host):
        sid = create(host)['session_id']
        short_questions(sid)
        c, _ = join(sid)
        join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        host.post(f'/api/h/{sid}/next', json={'from_index': 0})
        answer(c, sid, 1, 'agree')
        s = state(c, sid)
        assert s['me']['answer'] == 'agree' and s['question']['index'] == 1
        # Answering again doesn't double count.
        answer(c, sid, 1, 'agree')
        assert state(c, sid)['me']['score'] == 1

    def test_bad_answer_values(self, host):
        sid = create(host)['session_id']
        c, _ = join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        assert c.post(f'/api/s/{sid}/answer', json={'answer': 'maybe', 'question_index': 0}).status_code == 400
        assert c.post(f'/api/s/{sid}/answer', json={'answer': 'agree'}).status_code == 400
        assert c.post(f'/api/s/{sid}/answer', data='junk').status_code == 400

    def test_answer_before_start(self, host):
        sid = create(host)['session_id']
        c, _ = join(sid)
        assert answer(c, sid, 0).status_code == 409


class TestProgression:
    def test_auto_advance_when_all_connected_answered(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid)
        a, _ = join(sid)
        b, _ = join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        answer(a, sid, 0)
        assert hstate(host, sid)['current'] == 0
        answer(b, sid, 0, 'disagree')
        s = hstate(host, sid)
        assert s['current'] == 0 and s['advance_in'] is not None   # grace period
        clock['now'] += appmod.AUTO_ADVANCE_GRACE + 0.1
        assert hstate(host, sid)['current'] == 1

    def test_disconnected_student_not_waited_for(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid)
        a, _ = join(sid)
        sleeper, _ = join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        clock['now'] += appmod.ACTIVE_WINDOW + 1   # sleeper's phone goes to sleep
        state(a, sid)                               # a keeps polling
        answer(a, sid, 0)
        clock['now'] += appmod.AUTO_ADVANCE_GRACE + 0.1
        state(a, sid)
        assert hstate(host, sid)['current'] == 1
        # Sleeper wakes up and lands on the current question, as the same person.
        s = state(sleeper, sid)
        assert s['question']['index'] == 1 and s['me']['answer'] is None
        assert answer(sleeper, sid, 1).status_code == 200

    def test_reconnecting_student_cancels_pending_auto_advance(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid)
        a, _ = join(sid)
        b, _ = join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        clock['now'] += appmod.ACTIVE_WINDOW + 1
        state(a, sid)
        answer(a, sid, 0)
        assert hstate(host, sid)['advance_in'] is not None
        state(b, sid)   # b comes back before the grace period ends
        assert hstate(host, sid)['advance_in'] is None
        clock['now'] += appmod.AUTO_ADVANCE_GRACE + 1
        state(b, sid)
        assert hstate(host, sid)['current'] == 0

    def test_timer_advances_without_answers(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid)
        join(sid)
        host.post(f'/api/h/{sid}/settings', json={'timer': 30})
        host.post(f'/api/h/{sid}/start', json={})
        assert hstate(host, sid)['time_left'] == 30
        clock['now'] += 31
        assert hstate(host, sid)['current'] == 1

    def test_timer_finishes_walk(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid, 2)
        join(sid)
        host.post(f'/api/h/{sid}/settings', json={'timer': 15})
        host.post(f'/api/h/{sid}/start', json={})
        clock['now'] += 16
        hstate(host, sid)
        clock['now'] += 16
        assert hstate(host, sid)['status'] == 'finished'

    def test_pause_stops_timer(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid)
        join(sid)
        host.post(f'/api/h/{sid}/settings', json={'timer': 30})
        host.post(f'/api/h/{sid}/start', json={})
        clock['now'] += 10
        host.post(f'/api/h/{sid}/pause', json={})
        clock['now'] += 100
        s = hstate(host, sid)
        assert s['current'] == 0 and s['paused'] and s['time_left'] == 20
        host.post(f'/api/h/{sid}/resume', json={})
        assert hstate(host, sid)['time_left'] == 20

    def test_teacher_can_always_advance_and_finish(self, host):
        sid = create(host)['session_id']
        short_questions(sid, 2)
        join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        host.post(f'/api/h/{sid}/next', json={'from_index': 0})
        r = host.post(f'/api/h/{sid}/next', json={'from_index': 1})   # last question, nobody answered
        assert r.status_code == 200 and r.get_json()['status'] == 'finished'

    def test_double_click_next_skips_only_one(self, host):
        sid = create(host)['session_id']
        short_questions(sid, 5)
        join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        host.post(f'/api/h/{sid}/next', json={'from_index': 0})
        host.post(f'/api/h/{sid}/next', json={'from_index': 0})
        assert hstate(host, sid)['current'] == 1

    def test_back_holds_auto_advance(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid)
        a, _ = join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        answer(a, sid, 0)
        clock['now'] += appmod.AUTO_ADVANCE_GRACE + 0.1
        assert hstate(host, sid)['current'] == 1
        host.post(f'/api/h/{sid}/back', json={})
        clock['now'] += 10
        s = hstate(host, sid)
        assert s['current'] == 0 and s['auto_held']
        assert state(a, sid)['me']['answer'] == 'agree'

    def test_finish_and_reopen(self, host):
        sid = create(host)['session_id']
        short_questions(sid)
        join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        host.post(f'/api/h/{sid}/finish', json={})
        assert hstate(host, sid)['status'] == 'finished'
        host.post(f'/api/h/{sid}/back', json={})
        s = hstate(host, sid)
        assert s['status'] == 'active' and s['current'] == 2

    def test_reset_keeps_people_clears_answers(self, host):
        sid = create(host)['session_id']
        c, me = join(sid)
        join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        answer(c, sid, 0)
        host.post(f'/api/h/{sid}/reset', json={})
        s = state(c, sid)
        assert s['status'] == 'waiting' and s['me']['pid'] == me['pid'] and s['me']['score'] == 0

    def test_late_joiner(self, host):
        sid = create(host)['session_id']
        short_questions(sid)
        join(sid)
        join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        host.post(f'/api/h/{sid}/next', json={'from_index': 0})
        late, _ = join(sid)
        s = state(late, sid)
        assert s['question']['index'] == 1
        assert answer(late, sid, 1).status_code == 200

    def test_rankings_share_ties(self, host):
        sid = create(host)['session_id']
        short_questions(sid)
        a, _ = join(sid)
        b, _ = join(sid)
        c, _ = join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        answer(a, sid, 0, 'agree')
        answer(b, sid, 0, 'agree')
        answer(c, sid, 0, 'disagree')
        assert state(a, sid)['me']['rank'] == 1
        assert state(b, sid)['me']['rank'] == 1
        assert state(c, sid)['me']['rank'] == 3

    def test_export_csv(self, host):
        sid = create(host)['session_id']
        short_questions(sid)
        a, me = join(sid)
        join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        answer(a, sid, 0)
        body = host.get(f'/api/h/{sid}/export.csv').get_data(as_text=True)
        assert body.splitlines()[0] == 'alias,score,Q1,Q2,Q3'
        assert f"{me['alias']},1,agree,," in body


class TestPersistence:
    def test_save_and_load_roundtrip(self, host, tmp_path, monkeypatch):
        monkeypatch.setattr(appmod, 'DATA_FILE', str(tmp_path / 'sessions.json'))
        sid = create(host)['session_id']
        c, me = join(sid)
        host.post(f'/api/h/{sid}/start', json={})
        answer(c, sid, 0)
        appmod.save_sessions_to_file()
        active_sessions.clear()
        appmod._token_index.clear()
        appmod.load_sessions_from_file()
        s = state(c, sid)
        assert s['me']['pid'] == me['pid'] and s['me']['answer'] == 'agree'

    def test_corrupt_file_is_moved_aside(self, tmp_path, monkeypatch):
        path = tmp_path / 'sessions.json'
        path.write_text('{not json')
        monkeypatch.setattr(appmod, 'DATA_FILE', str(path))
        appmod.load_sessions_from_file()
        assert active_sessions == {}
        assert (tmp_path / 'sessions.json.corrupt').exists()

    def test_cleanup_old_sessions(self, host, clock):
        sid = create(host)['session_id']
        _, me = join(sid)
        clock['now'] += appmod.SESSION_TTL + 1
        assert appmod.cleanup_old_sessions() == 1
        assert sid not in active_sessions and me['token'] not in appmod._token_index


class TestOps:
    def test_health(self, host):
        create(host)
        data = host.get('/health').get_json()
        assert data['status'] == 'healthy' and data['active_sessions'] == 1

    def test_unknown_session_api(self, host):
        r = host.get('/api/s/nope/state')
        assert r.status_code == 404 and r.get_json()['gone']

    def test_api_responses_not_cached(self, host):
        sid = create(host)['session_id']
        assert host.get(f'/api/s/{sid}/state').headers['Cache-Control'] == 'no-store'


class TestStragglers:
    def test_silent_but_connected_students_do_not_block(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid)
        devices = [join(sid)[0] for _ in range(8)]
        host.post(f'/api/h/{sid}/start', json={})
        for c in devices[:5]:
            answer(c, sid, 0)
        assert hstate(host, sid)['time_left'] is None          # 5/8 < 75%
        answer(devices[5], sid, 0)                              # 6/8 = 75%
        s = hstate(host, sid)
        assert s['straggler_countdown'] and s['current'] == 0
        clock['now'] += 10
        for c in devices[6:]:
            state(c, sid)                                       # still connected, not answering
        assert hstate(host, sid)['time_left'] == 10
        clock['now'] += 11
        assert hstate(host, sid)['current'] == 1

    def test_straggler_wait_can_be_disabled(self, host, clock):
        sid = create(host)['session_id']
        short_questions(sid)
        devices = [join(sid)[0] for _ in range(4)]
        host.post(f'/api/h/{sid}/settings', json={'straggler_wait': 0})
        host.post(f'/api/h/{sid}/start', json={})
        for c in devices[:3]:
            answer(c, sid, 0)
        for _ in range(5):
            clock['now'] += 10
            state(devices[3], sid)
        assert hstate(host, sid)['current'] == 0


def test_class_sized_groups_get_distinct_emoji(host):
    sid = create(host)['session_id']
    emoji = [join(sid)[1]['emoji'] for _ in range(len(appmod.ANIMALS))]
    assert len(set(emoji)) == len(appmod.ANIMALS)
