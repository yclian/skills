#!/usr/bin/env node
/**
 * work-signal CLI — the fallback path, for terminals and agents with no Gmail
 * connector. The scheduled morning run does NOT use this; see
 * references/scheduling.md.
 *
 * Emits `--format json` for an agent to apply the judgement pass to, or
 * `--format md` for a human.
 */

import { loadConfig, buildSignalQuery, buildStillOpenQuery, buildPipelineQuery } from './config.mjs';
import { Gmail, authorize } from './gmail.mjs';
import {
  classifyThreads, computeWindow, previousSlot, isoWeek, isoDate, threadLink, sortRows,
} from './classify.mjs';

const BUCKET_META = {
  leadership: { emoji: '👑', title: 'Leadership & Key Stakeholders' },
  security: { emoji: '🛡️', title: 'Security, Compliance & Infrastructure' },
  approvals: { emoji: '📋', title: 'Approvals & Action Items' },
  team: { emoji: '👥', title: 'Team Mentions & Colleague Threads' },
  digests: { emoji: '📊', title: 'Executive Reports & Digests' },
};
const ORDER = ['leadership', 'security', 'approvals', 'team', 'digests'];

function parseArgs(argv) {
  const args = { format: 'md' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === '--auth') args.auth = true;
    else if (a === '--unread') args.unread = true;
    else if (a === '--days') args.days = Number(next());
    else if (a === '--since') args.since = next();
    else if (a === '--as-of') args.asOf = next();
    else if (a === '--format') args.format = next();
    else if (a === '--config') args.config = next();
    else if (a === '--max') args.max = Number(next());
    else if (a === '--help' || a === '-h') args.help = true;
  }
  return args;
}

const HELP = `
work-signal — morning triage of a work Gmail inbox

  node src/work-signal.mjs [options]

  --days N              lookback window in days (default: 1, or 2 on Monday)
  --since YYYY-MM-DD    absolute window start
  --as-of YYYY-MM-DD    pretend today is this date (for testing Monday logic)
  --unread              restrict to unread
  --format json|md      output format (default: md)
  --config PATH         explicit config path
  --max N               maximum threads to inspect (default: 100)
  --auth                run the OAuth flow and exit
`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) { console.log(HELP.trim()); return; }

  const cfg = await loadConfig(args.config);
  if (args.auth) { await authorize(cfg); return; }

  const now = args.asOf ? new Date(`${args.asOf}T12:00:00Z`) : new Date();
  const win = computeWindow(now, { timezone: cfg.identity.timezone, ...(cfg.window || {}) },
    { days: args.days, since: args.since });
  const slot = args.since ? null : previousSlot(now, { timezone: cfg.identity.timezone, ...(cfg.window || {}) });

  const gmail = new Gmail(cfg);
  const query = buildSignalQuery(cfg, win.gmail, { unread: args.unread });
  const { threads, truncated } = await gmail.searchThreads(query, { maxThreads: args.max ?? 100 });

  const result = classifyThreads(threads, cfg, { slot });

  // Still-open probe: unread, internal, already seen on an earlier morning.
  const seen = new Set(threads.map((t) => t.id));
  let stillOpen = [];
  try {
    const probe = await gmail.searchThreads(buildStillOpenQuery(cfg), { maxThreads: 25 });
    const fresh = probe.threads.filter((t) => !seen.has(t.id));
    stillOpen = classifyThreads(fresh, cfg, { slot: Infinity });
    stillOpen = ORDER.flatMap((k) => stillOpen.buckets[k]).sort(sortRows).slice(0, 10);
  } catch { /* the probe is a nicety; never fail the brief over it */ }

  if (cfg.report?.show_suppressed_counts !== false) {
    const pq = buildPipelineQuery(cfg, win.gmail);
    if (pq) {
      try { result.suppressed.pipeline = await gmail.countThreads(pq); } catch { /* keep client-side count */ }
    }
  }

  const payload = {
    meta: {
      version: cfg.meta?.version ?? 'unknown',
      configSource: cfg._source,
      isExampleConfig: Boolean(cfg._isExample),
      path: 'cli',
      calls: gmail.calls,
      isoWeek: isoWeek(win.today),
      today: isoDate(win.today),
      windowStart: isoDate(win.start),
      timezone: cfg.identity.timezone,
      truncated,
    },
    buckets: result.buckets,
    stillOpen,
    handled: result.handled,
    scanned: result.scanned,
    suppressed: result.suppressed,
  };

  console.log(args.format === 'json' ? JSON.stringify(payload, null, 2) : renderMarkdown(payload, cfg));
}

function renderMarkdown(p, cfg) {
  const emoji = cfg.report?.emoji_headings !== false;
  const cap = cfg.report?.max_rows_per_bucket ?? 12;
  const email = cfg.identity.email;
  const need = ORDER.reduce((n, k) => n + p.buckets[k].length, 0);
  const out = [];

  out.push(`## ${emoji ? '🎯 ' : ''}Work Signal — ${p.meta.isoWeek} ${p.meta.today} (${p.meta.timezone})`);
  out.push(`Window: ${p.meta.windowStart} → now · ${p.scanned} threads scanned · ${need} need you · ${p.handled} already handled`);
  if (cfg.report?.show_suppressed_counts !== false) {
    out.push(`Suppressed: ${emoji ? '⚡ ' : ''}${p.suppressed.pipeline} pipeline · ${emoji ? '🔇 ' : ''}${p.suppressed.vendor} vendor · Config ${p.meta.version}`);
  }
  if (p.meta.isExampleConfig) {
    out.push(`\n> Running on the bundled example config — leadership and noise lists are empty. See references/setup.md.`);
  }
  if (p.meta.truncated) out.push(`\n> Results truncated: more threads matched than were inspected.`);
  out.push('');

  if (need === 0 && p.stillOpen.length === 0) {
    out.push(`${emoji ? '🎉 ' : ''}Nothing needs you this morning. ${p.scanned} threads scanned since ${p.meta.windowStart}; `
      + `${p.suppressed.pipeline} pipeline and ${p.suppressed.vendor} vendor threads suppressed; ${p.handled} already handled. Still open: none.`);
    out.push('');
    out.push(footer(p));
    return out.join('\n');
  }

  for (const key of ORDER) {
    const rows = p.buckets[key];
    if (!rows.length) continue;               // omit empty buckets entirely
    const m = BUCKET_META[key];
    out.push(`### ${emoji ? `${m.emoji} ` : ''}${m.title}`);
    out.push(table(rows, cap, email));
    out.push('');
  }

  if (p.stillOpen.length) {
    out.push(`### ${emoji ? '⏳ ' : ''}Still open (unread, 1–${cfg.window?.still_open_days ?? 7} days)`);
    out.push(table(p.stillOpen, cap, email));
    out.push('');
  }

  out.push(footer(p));
  return out.join('\n');
}

function footer(p) {
  return `work-signal ${p.meta.version} · ${p.meta.path} · ${p.meta.calls} calls`;
}

function table(rows, cap, email) {
  const lines = ['| From | Ask | Thread | |', '| --- | --- | --- | --- |'];
  for (const r of rows.slice(0, cap)) {
    const from = [
      esc(r.from),
      r.relay ? ' (via Chat)' : '',
      r.external ? ' (external)' : '',
      r.direct ? ' → you' : '',
    ].join('');
    // The CLI has no judgement pass, so the subject stands in for the Ask.
    // An agent consuming --format json replaces this with a written ask.
    const ask = esc(r.subject) + (r.carried && r.firstDate ? ` (since ${r.firstDate.slice(0, 10)})` : '');
    const count = `${r.count} msg${r.count === 1 ? '' : 's'}${r.unreadCount ? `, ${r.unreadCount} unread` : ''}`;
    lines.push(`| ${from} | ${ask} | ${count} | [open](${threadLink(r.threadId, email)}) |`);
  }
  if (rows.length > cap) lines.push(`| | +${rows.length - cap} more | | |`);
  return lines.join('\n');
}

function esc(s = '') {
  return String(s).replace(/\|/g, '\\|').replace(/\n/g, ' ').trim() || '(no subject)';
}

main().catch((err) => {
  console.error(`Work Signal could not run: ${err.message}`);
  process.exit(1);
});
