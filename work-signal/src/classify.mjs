/**
 * Pure classification and window logic.
 *
 * Deliberately free of network and filesystem access so it can be unit tested,
 * and so the connector path and the CLI path provably agree: both apply these
 * same rules. See references/classification.md for the spec this implements.
 */

const NO_REPLY_PATTERNS = [
  'no-reply', 'noreply', 'no_reply', 'donotreply', 'do-not-reply',
  'notifications', 'notification', 'mailer-daemon', 'automation', 'bot@',
];

// --- dates -------------------------------------------------------------------

/** Calendar parts of `date` as observed in `timeZone`. */
export function partsInZone(date, timeZone) {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short',
  });
  const p = Object.fromEntries(fmt.formatToParts(date).map((x) => [x.type, x.value]));
  const weekdays = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  return {
    year: Number(p.year),
    month: Number(p.month),
    day: Number(p.day),
    dow: weekdays[p.weekday],
  };
}

/** Gmail's `after:` wants YYYY/MM/DD. */
export function gmailDate({ year, month, day }) {
  return `${year}/${String(month).padStart(2, '0')}/${String(day).padStart(2, '0')}`;
}

export function isoDate({ year, month, day }) {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/**
 * ISO week, formatted to the company convention: 2026.W38.
 * Thursday-of-the-week rule: the week containing the year's first Thursday is W1.
 */
export function isoWeek({ year, month, day }) {
  const d = new Date(Date.UTC(year, month - 1, day));
  const dow = d.getUTCDay() || 7;                 // Mon=1 .. Sun=7
  d.setUTCDate(d.getUTCDate() + 4 - dow);         // shift to the week's Thursday
  const isoYear = d.getUTCFullYear();
  const jan1 = new Date(Date.UTC(isoYear, 0, 1));
  const week = Math.ceil(((d - jan1) / 86400000 + 1) / 7);
  return `${isoYear}.W${String(week).padStart(2, '0')}`;
}

/**
 * The lookback window.
 *
 * Monday reaches back over the weekend to Saturday; every other day looks back
 * one. Day-granular on purpose: a scheduled run that fires late (app was closed
 * at 08:30, opened at 10:00) must not silently lose those hours, which is what a
 * rolling `newer_than:1d` would do.
 */
export function computeWindow(now, { timezone, weekday_days = 1, monday_days = 2 }, override = {}) {
  const today = partsInZone(now, timezone);

  if (override.since) {
    const [y, m, d] = override.since.split('-').map(Number);
    const start = { year: y, month: m, day: d };
    return { today, start, days: null, gmail: gmailDate(start) };
  }

  const days = override.days ?? (today.dow === 1 ? monday_days : weekday_days);
  const back = new Date(Date.UTC(today.year, today.month - 1, today.day));
  back.setUTCDate(back.getUTCDate() - days);
  const start = {
    year: back.getUTCFullYear(),
    month: back.getUTCMonth() + 1,
    day: back.getUTCDate(),
  };
  return { today, start, days, gmail: gmailDate(start) };
}

/** The previous morning slot — what "new since last brief" is measured against. */
export function previousSlot(now, cfg, hour = 8, minute = 30) {
  const { start } = computeWindow(now, cfg);
  return Date.UTC(start.year, start.month - 1, start.day, hour, minute);
}

// --- matching ----------------------------------------------------------------

export function addressOf(sender = '') {
  const m = sender.match(/<([^>]+)>/);
  return (m ? m[1] : sender).trim().toLowerCase();
}

export function displayNameOf(sender = '') {
  const m = sender.match(/^\s*"?([^"<]+?)"?\s*</);
  const name = m ? m[1].trim() : '';
  return name || addressOf(sender).split('@')[0] || 'Unknown';
}

/**
 * Sender rules are `local-part@`, a full address, or `@domain`.
 * A bare substring is not a rule: v1 matched "billy" and hit every William.
 */
export function matchSender(sender, rules = []) {
  const addr = addressOf(sender);
  if (!addr) return false;
  return rules.some((raw) => {
    const rule = String(raw).trim().toLowerCase();
    if (!rule) return false;
    if (rule.startsWith('@')) return addr.endsWith(rule);
    if (rule.endsWith('@')) return addr.startsWith(rule);
    if (rule.includes('@')) return addr === rule;
    // Legacy bare fragments from v1 configs: tolerated, but only against the
    // domain, never the local part — so they cannot match a person's name.
    return addr.split('@')[1]?.includes(rule) ?? false;
  });
}

export function isInternal(sender, domains = []) {
  const addr = addressOf(sender);
  return domains.some((d) => addr.endsWith(`@${String(d).toLowerCase()}`));
}

export function isNoReply(sender) {
  const addr = addressOf(sender);
  return NO_REPLY_PATTERNS.some((p) => addr.includes(p));
}

export function isInternalHuman(sender, domains = []) {
  return isInternal(sender, domains) && !isNoReply(sender);
}

function hasKeyword(text = '', keywords = []) {
  const t = text.toLowerCase();
  return keywords.some((k) => t.includes(String(k).toLowerCase()));
}

// --- the rule pass -----------------------------------------------------------

/** Normalise a thread: messages oldest-first, latest last. */
function normalise(thread) {
  const messages = [...(thread.messages || [])].sort(
    (a, b) => new Date(a.date) - new Date(b.date),
  );
  return { ...thread, messages, latest: messages.at(-1), first: messages[0] };
}

/**
 * Collapse mirror duplicates: the same alert relayed twice, once direct and once
 * through an internal security/ops alias. Keeps the copy addressed to the user.
 */
export function dedupeMirrors(threads, cfg) {
  const mirrors = cfg.dedupe?.mirror_senders || [];
  if (!mirrors.length) return { threads, removed: 0 };

  const windowMs = (cfg.dedupe?.window_seconds ?? 120) * 1000;
  const origins = cfg.dedupe?.mirrors_of || [];
  const keep = [];
  let removed = 0;

  for (const t of threads) {
    const messages = [...(t.messages || [])].sort((a, b) => new Date(a.date) - new Date(b.date));
    const latest = messages.at(-1);
    if (!latest || !matchSender(latest.sender, mirrors)) { keep.push(t); continue; }

    const twin = threads.find((o) => {
      if (o === t) return false;
      const om = [...(o.messages || [])].sort((a, b) => new Date(a.date) - new Date(b.date)).at(-1);
      if (!om) return false;
      if ((om.subject || '') !== (latest.subject || '')) return false;
      if (origins.length && !matchSender(om.sender, origins)) return false;
      return Math.abs(new Date(om.date) - new Date(latest.date)) <= windowMs;
    });

    if (twin) { removed++; continue; }   // drop the mirror, keep the original
    keep.push(t);
  }
  return { threads: keep, removed };
}

/**
 * Collapse high-volume automation senders into one counted row per bucket.
 * Internal humans are never aggregated — people get their own rows.
 */
export function aggregateRows(rows, cfg) {
  const senders = cfg.aggregate?.senders || [];
  const min = cfg.aggregate?.min_rows ?? 2;
  if (!senders.length) return rows;

  const groups = new Map();
  const out = [];
  for (const r of rows) {
    const rule = senders.find((s) => matchSender(r.fromAddress, [s]));
    if (!rule || r.internalHuman) { out.push(r); continue; }
    if (!groups.has(rule)) groups.set(rule, []);
    groups.get(rule).push(r);
  }

  for (const [, group] of groups) {
    if (group.length < min) { out.push(...group); continue; }
    const sorted = [...group].sort((a, b) => new Date(b.date) - new Date(a.date));
    const newest = sorted[0];
    const oldest = sorted.at(-1);
    out.push({
      ...newest,
      aggregated: true,
      aggregateCount: group.length,
      oldestDate: oldest.firstDate || oldest.date,
      subjects: sorted.map((r) => r.subject),
      count: group.reduce((n, r) => n + r.count, 0),
      unreadCount: group.reduce((n, r) => n + r.unreadCount, 0),
      unread: group.some((r) => r.unread),
      direct: group.some((r) => r.direct),
    });
  }
  return out.sort(sortRows);
}

export function classifyThreads(threads, cfg, { slot } = {}) {
  const domains = cfg.identity?.internal_domains || [];
  const me = [cfg.identity?.email, ...(cfg.identity?.me_aliases || [])]
    .filter(Boolean).map((s) => s.toLowerCase());

  const buckets = { leadership: [], security: [], approvals: [], team: [], digests: [] };
  const suppressed = { pipeline: 0, vendor: 0, mirror: 0 };
  let handled = 0;

  const deduped = dedupeMirrors(threads, cfg);
  suppressed.mirror = deduped.removed;

  for (const raw of deduped.threads) {
    const t = normalise(raw);
    if (!t.latest) continue;

    const latestSender = t.latest.sender || '';
    const subject = t.latest.subject || t.first?.subject || '(no subject)';
    const anyInternalHuman = t.messages.some((m) => isInternalHuman(m.sender, domains));

    // 1. Noise — but never at the cost of an internal human's thread.
    if (!anyInternalHuman) {
      if (matchSender(latestSender, cfg.noise?.pipeline_senders)) { suppressed.pipeline++; continue; }
      if (matchSender(latestSender, cfg.noise?.vendor_senders)
          || hasKeyword(subject, cfg.noise?.subject_patterns)) { suppressed.vendor++; continue; }
    }

    // 2. Handled — decided only by who spoke last, never by content.
    if (me.includes(addressOf(latestSender))) { handled++; continue; }

    // 3. Direct — To only. Being copied is not being asked.
    const to = (t.latest.to || []).map((a) => addressOf(a));
    const direct = to.some((a) => me.includes(a));

    // 4. New vs carried.
    const latestAt = new Date(t.latest.date).getTime();
    const carried = slot != null && latestAt <= slot;

    // 5. Bucket — first match wins.
    // A calendar invite from a boss is not an ask. Mirrors the negated_query on
    // the user's own mail filter rather than inventing a second policy.
    const leadershipExcluded =
      hasKeyword(subject, cfg.buckets?.leadership?.exclude_subjects);

    let bucket;
    if (!leadershipExcluded
        && t.messages.some((m) => matchSender(m.sender, cfg.buckets?.leadership?.senders))) {
      bucket = 'leadership';
    } else if (matchSender(latestSender, cfg.buckets?.approvals?.senders)) {
      bucket = 'approvals';
    } else if (matchSender(latestSender, cfg.buckets?.security?.senders)
               || hasKeyword(subject, cfg.buckets?.security?.keywords)) {
      bucket = 'security';
    } else if (hasKeyword(subject, cfg.buckets?.approvals?.keywords)) {
      bucket = 'approvals';
    } else if (matchSender(latestSender, cfg.buckets?.digests?.senders)
               || hasKeyword(subject, cfg.buckets?.digests?.keywords)) {
      bucket = 'digests';
    } else {
      bucket = 'team';
    }

    const relay = matchSender(latestSender, cfg.buckets?.team?.relay_senders);

    buckets[bucket].push({
      threadId: t.id,
      from: displayNameOf(latestSender),
      fromAddress: addressOf(latestSender),
      originator: displayNameOf(t.first?.sender || latestSender),
      subject,
      snippet: t.latest.snippet || '',
      date: t.latest.date,
      firstDate: t.first?.date,
      count: t.messages.length,
      unread: t.messages.some((m) => (m.labelIds || []).includes('UNREAD')),
      unreadCount: t.messages.filter((m) => (m.labelIds || []).includes('UNREAD')).length,
      direct,
      carried,
      relay,
      external: !isInternal(latestSender, domains),
      internalHuman: isInternalHuman(latestSender, domains),
    });
  }

  for (const key of Object.keys(buckets)) {
    buckets[key] = aggregateRows(buckets[key].sort(sortRows), cfg);
  }
  return { buckets, suppressed, handled, scanned: threads.length };
}

/** Direct first, then unread, then newest. */
export function sortRows(a, b) {
  if (a.direct !== b.direct) return a.direct ? -1 : 1;
  if (a.unread !== b.unread) return a.unread ? -1 : 1;
  return new Date(b.date) - new Date(a.date);
}

export function threadLink(threadId, email) {
  return `https://mail.google.com/mail/?authuser=${encodeURIComponent(email)}#all/${threadId}`;
}
