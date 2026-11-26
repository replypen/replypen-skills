#!/usr/bin/env node
// Today's rank for candidate queries, before you write a synonym or searchTerms entry.
//
//   node probe.mjs --ranker <ranker.js> --index <built search index .json> --queries <file>
//
// queries: [{ "q": "...", "expect": ["article-id", ...], "from": "the logged query it generalizes" }]
// ("expect": [] = must find nothing). Dependency-free; Node 18+.
import fs from 'node:fs';
import path from 'node:path';

const arg = (name) => {
  const i = process.argv.indexOf(`--${name}`);
  if (i < 0 || !process.argv[i + 1]) { console.error(`missing --${name}`); process.exit(2); }
  return process.argv[i + 1];
};
await import(path.resolve(arg('ranker')));
const { docs, synonyms } = JSON.parse(fs.readFileSync(arg('index'), 'utf8'));
const ranker = globalThis.HelpSearchRanker.create(docs, { synonyms });
const ids = new Set(docs.map((d) => d.id));
const queries = JSON.parse(fs.readFileSync(arg('queries'), 'utf8'));
let ok = 0;
for (const { q, expect = [], from = '' } of queries) {
  for (const e of expect) if (!ids.has(e)) console.log(`  note: ${e} is not in the index (unlisted or deleted)`);
  const { total, results } = ranker.search(q);
  const top = results.map((r) => r.doc.id);
  const pos = top.findIndex((id) => expect.includes(id)) + 1;
  const good = expect.length ? pos === 1 : total === 0;
  if (good) ok++;
  const at = expect.length ? (pos ? `#${pos}` : 'none') : total ? `found ${total}` : 'none';
  console.log(`${good ? 'ok  ' : 'MISS'} ${q.slice(0, 36).padEnd(36)} ${at.padEnd(8)} top: ${top.slice(0, 3).join(', ') || '-'}${from ? `   [${from}]` : ''}`);
}
console.log(`${ok}/${queries.length} at #1`);
