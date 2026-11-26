#!/usr/bin/env node
// Replay logged help-center searches on TODAY's built index with the site's own ranker.
//
//   node replay.mjs --ranker <ranker.js> --index <built search index .json> --report <rp search report -o json file>
//
// Prints one line per query and a summary: how many queries failed then (zero results, no click, or a click at
// rank 3+) and how many still look wrong today. "check" = needs a human/agent read: it had results but nobody
// opened one, so only the articles can say whether today's top hit answers it. Dependency-free; Node 18+.
import fs from 'node:fs';
import path from 'node:path';

const arg = (name) => {
  const i = process.argv.indexOf(`--${name}`);
  if (i < 0 || !process.argv[i + 1]) { console.error(`missing --${name}`); process.exit(2); }
  return process.argv[i + 1];
};
await import(path.resolve(arg('ranker')));
const { docs, synonyms } = JSON.parse(fs.readFileSync(arg('index'), 'utf8'));
const report = JSON.parse(fs.readFileSync(arg('report'), 'utf8'));
const ranker = globalThis.HelpSearchRanker.create(docs, { synonyms });
const ids = new Set(docs.map((d) => d.id));

let failedThen = 0, failingNow = 0, check = 0;
for (const q of report.queries || []) {
  if (!q.q) continue;
  const lowClick = (q.clicks || []).some((c) => Object.keys(c.ranks || {}).some((r) => Number(r) >= 3));
  const then = q.zero_results > 0 || q.no_click > 0 || lowClick;
  if (then) failedThen++;
  const { total, results } = ranker.search(q.q);
  const top = results.map((r) => r.doc.id);
  const opened = (q.clicks || [])[0]?.id; // most-clicked article
  const openedNow = opened ? top.indexOf(opened) + 1 : 0;
  let status = 'ok';
  if (!total) status = 'zero';
  else if (opened && ids.has(opened) && (openedNow === 0 || openedNow > 2)) status = 'clicked-low';
  else if (opened && !ids.has(opened)) status = 'gone'; // the opened article left the index (deleted/unlisted)
  else if (!opened && then) status = 'check';
  if (status === 'zero' || status === 'clicked-low') failingNow++;
  if (status === 'check') check++;
  const was = [q.zero_results && `zero×${q.zero_results}`, q.no_click && `noclick×${q.no_click}`, lowClick && 'click@3+'].filter(Boolean).join(' ') || '-';
  console.log(`${status.padEnd(11)} ${String(q.searches).padStart(3)}× ${q.q.slice(0, 40).padEnd(40)} then: ${was.padEnd(22)} now: ${top.slice(0, 3).join(', ') || '(none)'}${opened ? `  opened: ${opened}${openedNow ? ' #' + openedNow : ''}` : ''}`);
}
const n = (report.queries || []).length;
console.log(`\n${n} queries, ${report.searches} searches. Failed then: ${failedThen}. Still failing today: ${failingNow} (zero or opened article not top 2), plus ${check} to read (results, no click).`);
