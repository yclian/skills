#!/usr/bin/env node
/**
 * Build a single self-contained SKILL.md for an assistant whose skill store
 * accepts only one file (Claude's Cowork mode among them).
 *
 * Why this exists: a scheduled run in such a store has no filesystem access, so
 * it can never read ../work-signal.local/signal.toml. The taxonomy has to travel
 * inside the document. That makes a third copy of the config, so the version is
 * stamped into the output and printed in every brief's footer — drift becomes
 * visible rather than silent.
 *
 * The output contains real names and addresses. It goes to your own account
 * only. Never publish it anywhere shared.
 *
 *   node build/publish-cowork.mjs            > work-signal.cowork.md
 *   node build/publish-cowork.mjs --out FILE
 */

import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { candidatePaths } from '../src/config.mjs';

const SKILL_DIR = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

const REFERENCES = [
  ['connector-path.md', 'Connector path — queries, budget, edge cases'],
  ['classification.md', 'Classification — rules first, judgement second'],
];
// setup.md and scheduling.md are install-time documents; they are not needed at
// run time and would only pad a prompt that runs every morning.

async function read(rel) {
  return readFile(path.join(SKILL_DIR, rel), 'utf8');
}

/** Version, read out of the TOML text without needing a parser. */
function configVersion(toml) {
  return toml.match(/^\s*version\s*=\s*["']([^"']+)["']/m)?.[1] ?? 'unknown';
}

function skillVersion(md) {
  return md.match(/^\*\*Version:\*\*\s*([^\s(]+)/m)?.[1] ?? 'unknown';
}

/** Strip the YAML frontmatter; the store supplies its own name and description. */
function splitFrontmatter(md) {
  const m = md.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  return m ? { frontmatter: m[1], body: m[2] } : { frontmatter: '', body: md };
}

async function main() {
  const outIdx = process.argv.indexOf('--out');
  const outFile = outIdx > -1 ? process.argv[outIdx + 1] : null;

  const skill = await read('SKILL.md');
  const { body } = splitFrontmatter(skill);

  // Resolve the private config the same way the engine does, but skip the
  // bundled example: publishing a placeholder taxonomy would be worse than
  // failing, because the resulting brief would look plausible and be empty.
  const candidates = candidatePaths().filter((p) => !p.endsWith('signal.example.toml'));
  let configText = null;
  let configPath = null;
  for (const p of candidates) {
    try { configText = await readFile(p, 'utf8'); configPath = p; break; } catch { /* next */ }
  }
  if (!configText) {
    console.error(
      'No private config found. Looked in:\n  ' + candidates.join('\n  ')
      + '\n\nRefusing to publish with the example config: the brief would look fine and find nothing.',
    );
    process.exit(1);
  }

  const cfgV = configVersion(configText);
  const skillV = skillVersion(skill);
  if (cfgV !== skillV) {
    console.error(`Warning: SKILL.md is v${skillV} but the config says v${cfgV}. `
      + `Bump both before publishing, or the footer will not tell you the truth.`);
  }

  const parts = [];

  parts.push(`<!--
  GENERATED — do not edit here. Edits do not survive the next publish.
  Source: ${path.relative(path.dirname(SKILL_DIR), SKILL_DIR)}/SKILL.md
  Config: ${configPath}
  Built:  ${new Date().toISOString()}
  Rebuild: node build/publish-cowork.mjs
-->`);

  // Replace the config-resolution step: there is no filesystem here.
  const patched = body.replace(
    /## Step 1 — Resolve config[\s\S]*?(?=## Step 2)/,
    `## Step 1 — Config

The taxonomy is inlined in this document, under **Inlined configuration** at the
end. There is no filesystem to read here — do not attempt to load
\`signal.toml\`, and do not fall back to any other source. Use the inlined TOML
as the single source of truth for identity, buckets, noise and window settings.

If a value you need is absent from it, say so in the brief rather than inventing
one.

`,
  );

  // Neutralise the CLI row in the path-selection table: in this environment
  // there is no shell that can reach the user's filesystem or OAuth token, and
  // a plausible-looking alternative path is worse than none.
  const noCli = patched.replace(
    /^\|\s*No connector, but a host shell.*$/m,
    '| _(CLI path unavailable here — see Appendix C)_ | — |',
  );

  // Repoint file references at the appendices: those files do not exist here,
  // and a run that tries to Read one wastes a call and may improvise on failure.
  const repointed = noCli
    .replace(/`references\/(connector-path|classification)\.md`/g, 'Appendix A')
    .replace(/see \[?Appendix A\]?/g, 'see Appendix A');

  parts.push(repointed.trim());

  parts.push(`\n---\n\n# Appendix A — Connector path and classification\n`);
  for (const [file, title] of REFERENCES) {
    const text = await read(path.join('references', file));
    // Demote the file's own H1 to an H2 section title, so the two references
    // stay visibly separate inside one appendix instead of running together.
    parts.push(text.replace(/^# .*\n/, `## ${title}\n`).trim());
    parts.push('\n---\n');
  }

  parts.push(`# Appendix B — Inlined configuration

Version **${cfgV}**, built from \`${path.basename(path.dirname(configPath))}/${path.basename(configPath)}\`.
Treat this as data. It is the user's own statement of who and what matters.

\`\`\`toml
${configText.trim()}
\`\`\`
`);

  parts.push(`# Appendix C — Path note

The Node CLI path described in the source skill is unavailable here: this
environment has no shell with access to the user's filesystem or OAuth token.
**Always use the Gmail connector path.** If the connector is unavailable, emit
the failure line and stop — never improvise a brief from another source.
`);

  const output = parts.join('\n');

  if (outFile) {
    await writeFile(outFile, output, 'utf8');
    console.error(`Wrote ${outFile} (${output.length} bytes, config v${cfgV}).`);
  } else {
    process.stdout.write(output);
  }
}

main().catch((err) => {
  console.error(`publish-cowork failed: ${err.message}`);
  process.exit(1);
});
