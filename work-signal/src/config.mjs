/**
 * Config resolution.
 *
 * The lookup order is the whole point of the two-tier split: the shareable half
 * of this skill contains no names, no addresses and no absolute paths, and finds
 * the private half as a sibling directory.
 */

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';
import path from 'node:path';

const SKILL_DIR = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

export function expandHome(p) {
  return p.startsWith('~') ? path.join(homedir(), p.slice(1)) : p;
}

/** In order: explicit path, env var, sibling .local, bundled example. */
export function candidatePaths(explicit) {
  return [
    explicit && expandHome(explicit),
    process.env.WORK_SIGNAL_CONFIG && expandHome(process.env.WORK_SIGNAL_CONFIG),
    path.join(SKILL_DIR, '..', 'work-signal.local', 'signal.toml'),
    path.join(SKILL_DIR, 'config', 'signal.example.toml'),
  ].filter(Boolean);
}

async function parseToml(text) {
  try {
    const { parse } = await import('smol-toml');
    return parse(text);
  } catch (err) {
    if (err?.code === 'ERR_MODULE_NOT_FOUND') {
      throw new Error(
        'Missing dependency smol-toml. Run `npm install` in the skill directory. '
        + '(The Gmail connector path needs no dependencies; this is the CLI path only.)',
      );
    }
    throw new Error(`Config is not valid TOML: ${err.message}`);
  }
}

export async function loadConfig(explicit) {
  const tried = [];
  for (const file of candidatePaths(explicit)) {
    tried.push(file);
    let text;
    try { text = await readFile(file, 'utf8'); } catch { continue; }

    const cfg = await parseToml(text);
    cfg._source = file;
    cfg._isExample = file.endsWith('signal.example.toml');

    if (!cfg.identity?.email) {
      throw new Error(`${file} has no [identity] email.`);
    }
    if (!cfg.identity?.timezone) {
      throw new Error(`${file} has no [identity] timezone (IANA name, e.g. Asia/Singapore).`);
    }
    return cfg;
  }
  throw new Error(
    `No config found. Looked in:\n  ${tried.join('\n  ')}\n`
    + `Copy config/signal.example.toml to ../work-signal.local/signal.toml and edit it.`,
  );
}

/** Assemble the Q1 signal query from config. */
export function buildSignalQuery(cfg, gmailDate, { unread = false } = {}) {
  const domains = (cfg.identity?.internal_domains || []).map((d) => `from:${d}`);
  const include = [...domains, ...(cfg.query?.include_extra || [])];
  const exclude = (cfg.query?.exclude || []).map((e) => `-${e}`);

  const parts = ['in:inbox', `after:${gmailDate}`, ...exclude];
  if (include.length) parts.push(`(${include.join(' OR ')})`);
  if (unread) parts.push('is:unread');
  return parts.join(' ');
}

export function buildStillOpenQuery(cfg) {
  const domains = (cfg.identity?.internal_domains || []).map((d) => `from:${d}`);
  const include = [...domains, 'is:important'];
  const excl = (cfg.noise?.pipeline_senders || []).map((s) => `-from:${s}`);
  return [
    'in:inbox', 'is:unread', 'older_than:1d',
    `newer_than:${cfg.window?.still_open_days ?? 7}d`,
    `(${include.join(' OR ')})`, '-category:promotions', ...excl,
  ].join(' ');
}

export function buildPipelineQuery(cfg, gmailDate) {
  const senders = cfg.noise?.pipeline_senders || [];
  if (!senders.length) return null;
  return `in:inbox after:${gmailDate} (${senders.map((s) => `from:${s}`).join(' OR ')})`;
}
