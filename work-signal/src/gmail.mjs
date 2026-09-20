/**
 * Minimal Gmail REST client.
 *
 * Zero dependencies: Node 18+ ships global fetch, which is all the OAuth refresh
 * and the two API calls need. Read-only scope. No message bodies are fetched
 * unless a caller explicitly asks for a thread.
 */

import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';

const SCOPE = 'https://www.googleapis.com/auth/gmail.readonly';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth';
const API = 'https://gmail.googleapis.com/gmail/v1/users/me';

export function expandHome(p) {
  return p.startsWith('~') ? path.join(homedir(), p.slice(1)) : p;
}

function authDir(cfg) {
  return expandHome(process.env.WORK_SIGNAL_AUTH_DIR || cfg.auth?.dir || '~/.config/work-signal');
}

async function readJson(file) {
  try { return JSON.parse(await readFile(file, 'utf8')); } catch { return null; }
}

async function loadCredentials(cfg) {
  const file = path.join(authDir(cfg), 'credentials.json');
  const raw = await readJson(file);
  if (!raw) {
    throw new Error(
      `No OAuth client at ${file}. Create a Desktop-app OAuth client in Google Cloud `
      + `with the Gmail API enabled, and save the JSON there. See references/setup.md.`,
    );
  }
  const c = raw.installed || raw.web || raw;
  if (!c.client_id || !c.client_secret) {
    throw new Error(`${file} is not a Desktop-app OAuth client (no client_id/client_secret).`);
  }
  return c;
}

async function refreshAccessToken(creds, refreshToken) {
  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: creds.client_id,
      client_secret: creds.client_secret,
      refresh_token: refreshToken,
      grant_type: 'refresh_token',
    }),
  });
  if (!res.ok) {
    throw new Error(
      `Token refresh failed (${res.status}). The refresh token may have been revoked — `
      + `re-run with --auth. Detail: ${(await res.text()).slice(0, 200)}`,
    );
  }
  return res.json();
}

/** Loopback OAuth flow. Interactive, run once via --auth. */
export async function authorize(cfg) {
  const creds = await loadCredentials(cfg);
  const dir = authDir(cfg);

  const server = createServer();
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  const redirect = `http://127.0.0.1:${port}/`;

  const url = `${AUTH_URL}?${new URLSearchParams({
    client_id: creds.client_id,
    redirect_uri: redirect,
    response_type: 'code',
    scope: SCOPE,
    access_type: 'offline',
    prompt: 'consent',
  })}`;

  console.error(`\nOpening your browser to authorise read-only Gmail access.`);
  console.error(`If it does not open, visit:\n\n${url}\n`);
  openBrowser(url);

  const code = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Timed out waiting for authorisation.')), 300000);
    server.on('request', (req, res) => {
      const q = new URL(req.url, redirect).searchParams;
      res.writeHead(200, { 'content-type': 'text/plain' });
      if (q.get('code')) {
        res.end('Authorised. You can close this tab.');
        clearTimeout(timer);
        resolve(q.get('code'));
      } else {
        res.end('No authorisation code received.');
      }
    });
  });
  server.close();

  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: creds.client_id,
      client_secret: creds.client_secret,
      redirect_uri: redirect,
      grant_type: 'authorization_code',
    }),
  });
  if (!res.ok) throw new Error(`Token exchange failed (${res.status}): ${await res.text()}`);

  const token = await res.json();
  if (!token.refresh_token) {
    throw new Error('Google returned no refresh token. Revoke the app in your Google account and retry.');
  }
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, 'token.json'), JSON.stringify(token, null, 2), { mode: 0o600 });
  console.error(`Saved token to ${path.join(dir, 'token.json')}`);
}

function openBrowser(url) {
  const cmd = process.platform === 'win32' ? ['cmd', ['/c', 'start', '', url]]
    : process.platform === 'darwin' ? ['open', [url]]
      : ['xdg-open', [url]];
  try { spawn(cmd[0], cmd[1], { stdio: 'ignore', detached: true }).unref(); } catch { /* print-only */ }
}

export class Gmail {
  #token = null;
  #calls = 0;

  constructor(cfg) { this.cfg = cfg; }

  get calls() { return this.#calls; }

  async #accessToken() {
    if (this.#token) return this.#token;
    const dir = authDir(this.cfg);
    const stored = await readJson(path.join(dir, 'token.json'));
    if (!stored?.refresh_token) {
      throw new Error(`Not authorised. Run: node src/work-signal.mjs --auth`);
    }
    const creds = await loadCredentials(this.cfg);
    const fresh = await refreshAccessToken(creds, stored.refresh_token);
    this.#token = fresh.access_token;
    return this.#token;
  }

  async #get(pathname, params = {}) {
    const token = await this.#accessToken();
    const qs = new URLSearchParams(
      Object.entries(params).flatMap(([k, v]) => (Array.isArray(v) ? v.map((x) => [k, x]) : [[k, v]])),
    );
    this.#calls++;
    const res = await fetch(`${API}/${pathname}?${qs}`, {
      headers: { authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`Gmail API ${pathname} failed (${res.status}): ${(await res.text()).slice(0, 200)}`);
    return res.json();
  }

  /**
   * Threads matching `query`, with per-message metadata headers only.
   *
   * One list call plus one metadata call per thread — the REST API has no
   * batch-with-metadata equivalent of the connector's minimal thread view. The
   * connector path is cheaper; this is the fallback.
   */
  async searchThreads(query, { maxThreads = 100 } = {}) {
    const out = [];
    let pageToken;
    do {
      const page = await this.#get('threads', {
        q: query, maxResults: 50, ...(pageToken ? { pageToken } : {}),
      });
      for (const t of page.threads || []) {
        if (out.length >= maxThreads) return { threads: out, truncated: true };
        out.push(await this.#thread(t.id));
      }
      pageToken = page.nextPageToken;
    } while (pageToken && out.length < maxThreads);
    return { threads: out, truncated: Boolean(pageToken) };
  }

  /** Count only — for the honest suppression figure. */
  async countThreads(query) {
    const page = await this.#get('threads', { q: query, maxResults: 50 });
    const n = (page.threads || []).length;
    return page.nextPageToken ? `${n}+` : String(n);
  }

  async #thread(id) {
    const t = await this.#get(`threads/${id}`, {
      format: 'metadata',
      metadataHeaders: ['From', 'To', 'Cc', 'Subject', 'Date'],
    });
    return {
      id: t.id,
      messages: (t.messages || []).map((m) => {
        const h = Object.fromEntries(
          (m.payload?.headers || []).map((x) => [x.name.toLowerCase(), x.value]),
        );
        return {
          id: m.id,
          sender: h.from || '',
          to: splitAddresses(h.to),
          cc: splitAddresses(h.cc),
          subject: h.subject || '',
          date: h.date ? new Date(h.date).toISOString() : new Date(Number(m.internalDate)).toISOString(),
          snippet: m.snippet || '',
          labelIds: m.labelIds || [],
        };
      }),
    };
  }
}

function splitAddresses(value = '') {
  return value ? value.split(',').map((s) => s.trim()).filter(Boolean) : [];
}
