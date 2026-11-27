# Site search

Search always runs **in the browser**, over an index the deploy builds or the page fetches. There is no search
server. ReplyPen only receives what visitors searched, saw, clicked and voted, and only on sites that need tuning.
Pick the smallest level that does the job.

## 1 · Local only (default)

| What is searched | Engine | Recipe |
|---|---|---|
| The site's own pages | [Pagefind](https://pagefind.app) | `pagefind --site _site` after the build. Index only `<main data-pagefind-body>`; skip pages with front matter `search: false` and blocks with `data-pagefind-ignore`. Test it on a build: dev-serve has no index. |
| Live data from an API (camps, products) | [MiniSearch](https://github.com/lucaong/minisearch), vendored | Fetch the data with a fixed URL per page so the CDN can cache it. **Whitelist the indexed fields**: a read token often sees more than is public. Build the index at the first search, not on page load. |
| Several kinds of results | One box, separate groups | Results from different engines don't rank against each other: show each group on its own, with `?q=` as a deeplink. |

**Ranking that works** (from KA and PB/MO):

- Every word must match (AND), at the start of a word.
- Then "contains" for words of 4+ letters, e.g. "tuin" finds "moestuin", ranked below the word-start matches.
- Typo tolerance only when both find nothing, and only for words of 5+ letters.
- Weight the fields: title ≫ headings ≫ description > body.
- Use a stop-word list in the site's language.
- Typos may only match words that appear in the index, so an off-topic query returns nothing.

**Fixture in the build:** keep a JSON file of `{q, expect}` pairs, and let `build.sh` fail when a known query loses
its result. Every fix adds its query. Live API data changes, so test it in a separate script (network), not in
the build.

## 2 · Tuned from real searches (help centers, big sites)

Use the same local search, plus three things:

- **Vocabulary as data:**
  - a directional synonym list (`mfa` also finds `2fa`, not the reverse);
  - front matter `searchTerms: [...]` on an article for the words visitors use that the article doesn't (indexed,
    never shown).
- **Events to ReplyPen:**
  - `POST https://app.replypen.com/search-events/{project}` with `navigator.sendBeacon`, as `text/plain`; the
    server always answers 204.
  - Send `search` once per settled query (about 1 s idle or Enter), zero results included; `click` with rank;
    `feedback` 👍/👎 under an article. Result links carry `#hs=<sid>`, so the vote joins the search it came from.
  - The browser sends no cookie and no visitor id, and only from the production host; ReplyPen redacts the
    queries.
- **Weekly editorial tune-up:** [help-search-tuneup](../../help-search-tuneup/SKILL.md) replays the logged queries
  on today's index and fixes misses as data (a synonym, `searchTerms`, a fixture row). It never adds an automatic
  click boost: with a few hundred searches a month, clicks are mostly noise and position bias.

Worth it from about 100 searches a month on one site. A camp site with a small offering stays on level 1; for camp
sites, the best match for level 2 is a shared synonym list across all of a company's sites.

Reference implementations:

- Level 1: KampAdmin `site-demo-jeugdwerk` `/zoeken/` (Pagefind + MiniSearch over the KA API).
- Level 2: ProBackup and MomentumTools `/help` (one twin ranker file in both sites, BM25 + prefix + typos +
  synonyms, query fixture in the build).
