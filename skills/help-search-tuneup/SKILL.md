---
name: help-search-tuneup
description: >-
  Weekly tune-up of a static help center's browser search from real visitor searches that ReplyPen logs:
  fetch the per-query report with rp, replay it on today's index, label each miss, fix it as data a build
  can test (synonyms, per-article searchTerms, query fixture) or one ranker idea, generalize, open one PR per
  site. Use for "tune help search", the weekly help-search job, or a zero-result/low-click query review.
---

# help-search-tuneup

Edit in [replypen/replypen-skills](https://github.com/replypen/replypen-skills) only: installed copies are overwritten on update.

Learning is editorial, never an automatic click boost. The site's root `AGENTS.md` names its paths (ranker and
its **twin** in the sibling site, common + site synonym lists, query fixture, built index, `rp` project); it wins
over this file. Event contract and privacy: ReplyPen `features/search-events.md`.

## Run (each site, then the cross-site pass)

1. **Fresh tree:** a sibling worktree, never switch a shared checkout:
   `git fetch origin && git worktree add -b help-search-tuneup-$(date +%F) ../<repo>-wt-tuneup origin/<base>`.
   **Since** = date in the newest remote `help-search-tuneup-*` branch (`git ls-remote --heads origin 'help-search-tuneup-*'`), else 30 days ago.
2. **Data:** `rp project search report --project <p> --from <since> -o json > /tmp/<p>-search.json`
   (per query: searches, zero results, no-click, shown list, clicks by rank, 👍/👎 on the articles it led to;
   `articles` = vote totals per article; queries arrive redacted).
   Fewer than ~5 searches since → skip steps 3–4 for this site and say so; still do step 5.
3. **Replay on today's build:** `bash build.sh`, then
   `node .agents/skills/help-search-tuneup/scripts/replay.mjs --ranker <ranker> --index <built index> --report /tmp/<p>-search.json`.
   Judge today's result, not what the visitor saw (`rev`/`v` show which build they had).
4. **Read before judging:** for every `zero`, `clicked-low`, `voted-down`, `check` row open the articles, then label
   it. A 👎 on a query→article pair = that article does not answer that query (wrong top hit, or an article gap);
   a 👍 pair = a fixture row worth adding. A 👎 without a search is an article-quality signal for the owner:
   - *vocabulary gap* → synonym: common list if generic SaaS wording, else the site list;
   - *article gap* → `searchTerms: [...]` in that article's front matter (words visitors use, the article doesn't);
     a title/heading that is plainly unclear → wording change (visible: owner's OK);
   - *missing article* → write nothing; list it for the owner with the queries that asked;
   - *ranker flaw* (right words present, wrong order; a rule misfires) → the twin ranker, at most one idea per run;
   - *noise* (test rows, off-topic, gibberish) → nothing, or a must-find-nothing fixture row.
5. **Two steps back** (the point of the run): for each fix ask what it generalizes to. A word missing on one
   article is usually missing on its siblings; a synonym learned here is replayed on the twin site; a family of
   phrasings failing the same way is a ranker/stop-word question, not twenty synonyms. A query that works well is
   a fixture row worth protecting. Probe candidates before writing them: `scripts/probe.mjs` (same args as
   replay, `--queries <[{q,expect,from}]>`) prints today's rank per query.

## Guards (hard)

- Every fix adds its query (expected article) to that site's fixture; both sites' `bash build.sh` stay green; a
  fix that does not move its query into the expected top is dropped, not kept "for later".
- Evidence or it doesn't go in: a logged query, or a generalization labelled with the query it came from.
- Expect only listed articles: unlisted ones are not in the index.
- Synonym keys go through the ranker's stop words: a key that is mostly stop words ("get back" → "back") rewrites
  every query containing the rest. Replay the whole fixture after each synonym.
- Exact matches keep ranking above synonym matches; no edit lowers a fixture score.
- ≤ ~20 data edits per site per run; a ranker change brings before/after fixture numbers for both sites and bumps
  `VERSION`.
- No names or personal data in fixtures or `searchTerms`; keep the intent ("restore a colleague's workspace").
- Twin files byte-identical at the end: `cmp` ranker and common synonyms against the sibling site.

## Ship

One branch + PR per site, body = what was learned in plain words and the fixture numbers before/after.
- **Data-only** (synonyms, `searchTerms`, fixture rows, ranker tuning: no visible copy) → merge it yourself once
  the gate/CI is green, then verify live: twin ranker served and `cmp`-identical across both sites, one query that
  only works through the new data, search events still leaving for ReplyPen.
- **Visible wording** (title, heading, article text) → its own PR, left open for the site owner (named in the
  site's `AGENTS.md`); never bundled with a data-only PR.

## Report (to whoever started the run)

Searches seen per site; share of queries failing then vs on today's replay; what changed; what generalized;
missing articles for the owner; one line on what would make next week's run easier.
