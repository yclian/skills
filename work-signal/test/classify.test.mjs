import test from 'node:test';
import assert from 'node:assert/strict';
import {
  computeWindow, isoWeek, matchSender, isInternalHuman, classifyThreads,
  threadLink, addressOf, displayNameOf, partsInZone,
} from '../src/classify.mjs';

const TZ = 'Asia/Singapore';
const WIN = { timezone: TZ, weekday_days: 1, monday_days: 2, still_open_days: 7 };

const cfg = {
  identity: {
    email: 'me@example.com',
    internal_domains: ['example.com'],
    timezone: TZ,
    me_aliases: ['me.alias@example.com'],
  },
  window: WIN,
  noise: {
    pipeline_senders: ['notifications-noreply@bitbucket.org'],
    vendor_senders: ['marketing@vendor.test'],
    subject_patterns: ['% off', 'webinar'],
  },
  buckets: {
    leadership: { senders: ['boss@', 'william@'] },
    security: { senders: ['@vanta.com'], keywords: ['security', 'certificate'] },
    approvals: { keywords: ['approval', 'purchase order'] },
    digests: { senders: ['worksights'], keywords: ['digest'] },
    team: { relay_senders: ['chat-noreply@google.com'] },
  },
};

const msg = (o) => ({
  sender: 'a@example.com', to: ['me@example.com'], cc: [],
  subject: 'hello', date: '2026-09-14T02:00:00Z', snippet: '', labelIds: [], ...o,
});
const thread = (id, messages) => ({ id, messages });

// --- window ------------------------------------------------------------------

test('Monday reaches back to Saturday', () => {
  // 2026-09-14 is a Monday.
  const w = computeWindow(new Date('2026-09-14T01:00:00Z'), WIN);
  assert.equal(w.today.dow, 1);
  assert.equal(w.gmail, '2026/09/12');       // the Saturday
  assert.equal(w.days, 2);
});

test('Tuesday looks back one day', () => {
  const w = computeWindow(new Date('2026-09-15T01:00:00Z'), WIN);
  assert.equal(w.gmail, '2026/09/14');
  assert.equal(w.days, 1);
});

test('Saturday looks back one day, not over the weekend', () => {
  const w = computeWindow(new Date('2026-09-19T01:00:00Z'), WIN);
  assert.equal(w.gmail, '2026/09/18');
});

test('window crosses a month boundary', () => {
  const w = computeWindow(new Date('2026-10-01T01:00:00Z'), WIN);
  assert.equal(w.gmail, '2026/09/30');
});

test('Monday window crosses a year boundary', () => {
  // 2027-01-04 is a Monday; Saturday before is 2027-01-02.
  const w = computeWindow(new Date('2027-01-04T01:00:00Z'), WIN);
  assert.equal(w.gmail, '2027/01/02');
});

test('timezone is honoured: 23:00 UTC is already tomorrow in Singapore', () => {
  // 2026-09-14T23:00Z is 2026-09-15 07:00 in SGT — a Tuesday, not a Monday.
  const w = computeWindow(new Date('2026-09-14T23:00:00Z'), WIN);
  assert.equal(w.today.day, 15);
  assert.equal(w.days, 1, 'should use the weekday window, not the Monday one');
});

test('--since overrides the computed window', () => {
  const w = computeWindow(new Date('2026-09-14T01:00:00Z'), WIN, { since: '2026-09-01' });
  assert.equal(w.gmail, '2026/09/01');
});

// --- ISO week ----------------------------------------------------------------

test('ISO week uses the company format', () => {
  assert.equal(isoWeek(partsInZone(new Date('2026-09-14T01:00:00Z'), TZ)), '2026.W38');
});

test('ISO week handles the year boundary', () => {
  // 2027-01-01 is a Friday, which falls in the final ISO week of 2026.
  assert.equal(isoWeek({ year: 2027, month: 1, day: 1 }), '2026.W53');
});

// --- sender matching ---------------------------------------------------------

test('local-part@ rule does not match a different person with a similar name', () => {
  assert.ok(matchSender('William Chen <william@example.com>', ['william@']));
  assert.ok(!matchSender('Williamson Lee <williamson@example.com>', ['william@']),
    'v1 substring-matched this and wrongly promoted them to Leadership');
});

test('@domain rule matches the whole domain', () => {
  assert.ok(matchSender('no-reply@vanta.com', ['@vanta.com']));
  assert.ok(!matchSender('no-reply@vanta.com.evil.test', ['@vanta.com']));
});

test('full address rule is exact', () => {
  assert.ok(matchSender('a@b.com', ['a@b.com']));
  assert.ok(!matchSender('aa@b.com', ['a@b.com']));
});

test('legacy bare fragment matches the domain only, never the local part', () => {
  assert.ok(matchSender('news@grazitti.com', ['grazitti']));
  assert.ok(!matchSender('grazitti@example.com', ['grazitti']),
    'a bare fragment must not match a person named like a vendor');
});

test('no-reply addresses are not internal humans', () => {
  assert.ok(isInternalHuman('jan@example.com', ['example.com']));
  assert.ok(!isInternalHuman('no-reply@example.com', ['example.com']));
  assert.ok(!isInternalHuman('jan@outside.test', ['example.com']));
});

test('address and display name parsing', () => {
  assert.equal(addressOf('Robert Davis <robert@example.com>'), 'robert@example.com');
  assert.equal(displayNameOf('"Davis, Robert" <robert@example.com>'), 'Davis, Robert');
  assert.equal(displayNameOf('robert@example.com'), 'robert');
});

// --- classification ----------------------------------------------------------

test('pipeline and vendor noise is suppressed and counted', () => {
  const r = classifyThreads([
    thread('t1', [msg({ sender: 'notifications-noreply@bitbucket.org', subject: 'Pipeline #4 failed' })]),
    thread('t2', [msg({ sender: 'marketing@vendor.test', subject: 'Big news' })]),
    thread('t3', [msg({ sender: 'someone@outside.test', subject: 'Free webinar on DevOps' })]),
  ], cfg, {});
  assert.equal(r.suppressed.pipeline, 1);
  assert.equal(r.suppressed.vendor, 2);
  assert.equal(Object.values(r.buckets).flat().length, 0);
});

test('a colleague forwarding vendor mail is never suppressed', () => {
  const r = classifyThreads([
    thread('t1', [
      msg({ sender: 'marketing@vendor.test', subject: 'Free webinar on DevOps' }),
      msg({ sender: 'jan@example.com', subject: 'Free webinar on DevOps', snippet: 'should we go?' }),
    ]),
  ], cfg, {});
  assert.equal(r.suppressed.vendor, 0);
  assert.equal(r.buckets.team.length, 1, 'an internal human on the thread rescues it');
});

test('handled is decided by who spoke last, not by content', () => {
  const r = classifyThreads([
    thread('t1', [msg({ sender: 'jan@example.com' }), msg({ sender: 'me@example.com' })]),
    thread('t2', [msg({ sender: 'me@example.com' }), msg({ sender: 'jan@example.com' })]),
  ], cfg, {});
  assert.equal(r.handled, 1);
  assert.equal(r.buckets.team.length, 1, 'a follow-up after my reply is not handled');
});

test('an alias of mine also counts as handled', () => {
  const r = classifyThreads([
    thread('t1', [msg({ sender: 'jan@example.com' }), msg({ sender: 'me.alias@example.com' })]),
  ], cfg, {});
  assert.equal(r.handled, 1);
});

test('Direct requires To, not Cc', () => {
  const r = classifyThreads([
    thread('t1', [msg({ sender: 'jan@example.com', to: ['me@example.com'] })]),
    thread('t2', [msg({ sender: 'jan@example.com', to: ['other@example.com'], cc: ['me@example.com'] })]),
  ], cfg, {});
  const [a, b] = r.buckets.team;
  assert.equal(a.direct, true);
  assert.equal(b.direct, false);
  assert.ok(r.buckets.team.indexOf(a) < r.buckets.team.indexOf(b), 'Direct sorts first');
});

test('leadership matches on any message, not just the latest sender', () => {
  const r = classifyThreads([
    thread('t1', [
      msg({ sender: 'boss@example.com', subject: 'Q4 plan' }),
      msg({ sender: 'jan@example.com', subject: 'Q4 plan' }),
    ]),
  ], cfg, {});
  assert.equal(r.buckets.leadership.length, 1,
    'a thread the boss started is still a leadership thread after a colleague replies');
  assert.equal(r.buckets.leadership[0].originator, 'boss');
});

test('bucket precedence: leadership beats security beats approvals', () => {
  const r = classifyThreads([
    thread('t1', [msg({ sender: 'boss@example.com', subject: 'security approval needed' })]),
    thread('t2', [msg({ sender: 'x@outside.test', subject: 'certificate approval needed' })]),
    thread('t3', [msg({ sender: 'x@outside.test', subject: 'purchase order 42' })]),
  ], cfg, {});
  assert.equal(r.buckets.leadership.length, 1);
  assert.equal(r.buckets.security.length, 1);
  assert.equal(r.buckets.approvals.length, 1);
});

test('carried threads are marked against the previous slot', () => {
  const slot = Date.parse('2026-09-14T00:30:00Z');
  const r = classifyThreads([
    thread('new', [msg({ sender: 'jan@example.com', date: '2026-09-14T02:00:00Z' })]),
    thread('old', [msg({ sender: 'jan@example.com', date: '2026-09-13T02:00:00Z' })]),
  ], cfg, { slot });
  const byId = Object.fromEntries(r.buckets.team.map((x) => [x.threadId, x]));
  assert.equal(byId.new.carried, false);
  assert.equal(byId.old.carried, true);
});

test('external senders are flagged and never promoted to leadership', () => {
  const r = classifyThreads([
    thread('t1', [msg({ sender: '"Robert Davis, CEO" <ceo@attacker.test>', subject: 'urgent approval' })]),
  ], cfg, {});
  assert.equal(r.buckets.leadership.length, 0, 'display name must not confer leadership');
  const row = [...r.buckets.approvals, ...r.buckets.security, ...r.buckets.team][0];
  assert.equal(row.external, true);
});

test('chat relays are flagged', () => {
  const r = classifyThreads([
    thread('t1', [msg({ sender: 'chat-noreply@google.com', subject: 'Jan mentioned you' })]),
  ], cfg, {});
  assert.equal(r.buckets.team[0].relay, true);
});

test('unread counts are per message', () => {
  const r = classifyThreads([
    thread('t1', [
      msg({ sender: 'jan@example.com', labelIds: [] }),
      msg({ sender: 'jan@example.com', labelIds: ['UNREAD'] }),
    ]),
  ], cfg, {});
  assert.equal(r.buckets.team[0].unreadCount, 1);
  assert.equal(r.buckets.team[0].unread, true);
});

test('messages out of order still resolve the latest correctly', () => {
  const r = classifyThreads([
    thread('t1', [
      msg({ sender: 'jan@example.com', date: '2026-09-14T05:00:00Z' }),
      msg({ sender: 'boss@example.com', date: '2026-09-14T01:00:00Z' }),
    ]),
  ], cfg, {});
  assert.equal(r.buckets.leadership[0].from, 'jan', 'latest by date, not by array position');
});

test('missing subject does not break anything', () => {
  const r = classifyThreads([
    thread('t1', [msg({ sender: 'jan@example.com', subject: undefined })]),
  ], cfg, {});
  assert.equal(r.buckets.team[0].subject, '(no subject)');
});

test('a calendar invite from a boss is not an ask', () => {
  const c = {
    ...cfg,
    buckets: {
      ...cfg.buckets,
      leadership: { senders: ['boss@'], exclude_subjects: ['invitation:', 'rsvp response'] },
    },
  };
  const r = classifyThreads([
    thread('ask', [msg({ sender: 'boss@example.com', subject: 'Q4 plan' })]),
    thread('cal', [msg({ sender: 'boss@example.com', subject: 'Invitation: Weekly sync' })]),
  ], c, {});
  assert.equal(r.buckets.leadership.length, 1);
  assert.equal(r.buckets.leadership[0].threadId, 'ask');
  assert.equal(r.buckets.team.length, 1, 'the invite drops out of Leadership');
});

test('an approvals sender beats a security keyword', () => {
  const c = {
    ...cfg,
    buckets: {
      ...cfg.buckets,
      approvals: { senders: ['system@sent-via.netsuite.com'], keywords: ['approval'] },
    },
  };
  const r = classifyThreads([
    thread('po', [msg({
      sender: 'system@sent-via.netsuite.com',
      subject: 'Urgent: signature required on Purchase Requisition',
    })]),
  ], c, {});
  assert.equal(r.buckets.approvals.length, 1, '"urgent" is a security keyword but the sender wins');
  assert.equal(r.buckets.security.length, 0);
});

// --- mirror dedupe -----------------------------------------------------------

const mirrorCfg = {
  ...cfg,
  dedupe: {
    mirror_senders: ['csirt@example.com'],
    mirrors_of: ['alerts-noreply@google.com'],
    window_seconds: 120,
  },
};

test('a mirrored alert is collapsed, keeping the copy addressed to me', () => {
  const r = classifyThreads([
    thread('direct', [msg({
      sender: 'alerts-noreply@google.com', subject: 'Alert: phishing reported',
      date: '2026-09-14T01:03:51Z', to: ['me@example.com'],
    })]),
    thread('mirror', [msg({
      sender: 'csirt@example.com', subject: 'Alert: phishing reported',
      date: '2026-09-14T01:03:52Z', to: ['csirt@example.com'],
    })]),
  ], mirrorCfg, {});
  assert.equal(r.suppressed.mirror, 1);
  const rows = Object.values(r.buckets).flat();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].threadId, 'direct', 'keeps the copy addressed to me');
});

test('the same subject outside the window is two real events', () => {
  const r = classifyThreads([
    thread('a', [msg({ sender: 'alerts-noreply@google.com', subject: 'Alert: phishing reported', date: '2026-09-14T01:00:00Z' })]),
    thread('b', [msg({ sender: 'csirt@example.com', subject: 'Alert: phishing reported', date: '2026-09-14T09:00:00Z' })]),
  ], mirrorCfg, {});
  assert.equal(r.suppressed.mirror, 0);
  assert.equal(Object.values(r.buckets).flat().length, 2);
});

// --- aggregation -------------------------------------------------------------

const aggCfg = {
  ...cfg,
  buckets: { ...cfg.buckets, security: { senders: ['@vanta.com'], keywords: [] } },
  aggregate: { senders: ['@vanta.com'], min_rows: 2 },
};

test('repeated automation collapses to one counted row', () => {
  const r = classifyThreads([
    thread('v1', [msg({ sender: 'no-reply@vanta.com', subject: 'access requested for A', date: '2026-09-14T01:00:00Z', labelIds: ['UNREAD'] })]),
    thread('v2', [msg({ sender: 'no-reply@vanta.com', subject: 'access requested for B', date: '2026-09-13T01:00:00Z', labelIds: ['UNREAD'] })]),
    thread('v3', [msg({ sender: 'no-reply@vanta.com', subject: 'access requested for C', date: '2026-09-12T01:00:00Z' })]),
  ], aggCfg, {});
  assert.equal(r.buckets.security.length, 1, 'three notifications, one row');
  const row = r.buckets.security[0];
  assert.equal(row.aggregated, true);
  assert.equal(row.aggregateCount, 3);
  assert.equal(row.unreadCount, 2);
  assert.equal(row.oldestDate, '2026-09-12T01:00:00Z');
  assert.equal(row.subjects.length, 3);
});

test('a single automation thread is not aggregated', () => {
  const r = classifyThreads([
    thread('v1', [msg({ sender: 'no-reply@vanta.com', subject: 'access requested for A' })]),
  ], aggCfg, {});
  assert.equal(r.buckets.security[0].aggregated, undefined);
});

test('internal humans are never aggregated', () => {
  const humanAgg = { ...cfg, aggregate: { senders: ['@example.com'], min_rows: 2 } };
  const r = classifyThreads([
    thread('h1', [msg({ sender: 'jan@example.com', subject: 'one' })]),
    thread('h2', [msg({ sender: 'jan@example.com', subject: 'two' })]),
  ], humanAgg, {});
  assert.equal(r.buckets.team.length, 2, 'people get their own rows');
});

// --- links -------------------------------------------------------------------

test('thread links use authuser, not an account index, and #all not #inbox', () => {
  const link = threadLink('abc123', 'me@example.com');
  assert.ok(link.includes('authuser=me%40example.com'));
  assert.ok(link.includes('#all/abc123'));
  assert.ok(!/\/u\/\d+\//.test(link), 'u/N is a per-browser-profile index and breaks elsewhere');
  assert.ok(!link.includes('#inbox/'), '#inbox 404s once a thread is archived');
});
