---
name: findability-score
description: >-
  Score how well a website will be found in Google and in AI assistants (ChatGPT, Perplexity, Google AI), old site
  vs new site, as one plain-language HTML report (Dutch or English) for a non-technical owner; also a monthly
  progress report. Use for "score <old url> vs <new url>", "hoe goed word ik gevonden", an SEO/GEO before-after for a
  rebuilt site, or a monthly ranking report. Fixing what it finds: website-dev references/seo-geo.md.
---

# findability-score

Edit in [replypen/replypen-skills](https://github.com/replypen/replypen-skills) only: installed copies are overwritten on update.

One command, one self-contained HTML page: a headline score out of 100 for the current and the new site, Google and
AI-assistant sub-scores, load time on a phone, 5 plain parts, and 3-4 ideas to score higher. Deterministic: ~27
fetch-and-parse checks (no LLM), so the same site gives the same score. Stdlib Python; `--lighthouse` adds mobile
speed through `pnpm dlx lighthouse` + local Chrome (median of `--runs 3`).

```bash
S=.agents/skills/findability-score/scripts/score_site.py
python3 $S compare https://www.old.example https://preview.example --lang nl --name "Praktijk X" \
  --assume-indexable new --lighthouse --json scores.json --out report-nl.html \
  [--rankings rankings.json] [--ai-answers ai.json] [--ideas ideas.json]
python3 $S compare … --reuse --json scores.json --lang en --out report-en.html   # second language, no re-crawl
python3 $S monthly history.json --lang nl --out monthly.html                     # month-by-month report
```

- **Preview sites:** a preview with `noindex`/`Disallow: /` scores zero on access. `--assume-indexable new` counts
  that one switch as "on at go-live" and the report says so. Score the preview URL, not localhost: speed and
  AI-bot blocking only show on the real host.
- **Rankings and AI answers are inputs, not crawled:** this needs paid SERP/LLM data. Fetch them with whatever data
  tool the project has (one call per term), store the raw answers, pass the summaries:
  `rankings.json` = `{"rows":[{"term","where":"google|maps","position":3|null}]}`,
  `ai.json` = `[{"question","engine","mentioned":true}]`. Present them as "today", measured on the current site.
- **`ideas.json`** = `[{"title","why","lang"}]`: practice-specific ideas from what you saw (reviews, a page per
  treatment, an English fact the AI got wrong). Shown first; the heaviest checks the new site still misses fill up.
- **Monthly history** = `{"name","sample":bool,"note","launch_after":0,"months":[{"label","google","ai",
  "rankings":{term:pos},"ai_mentions":[n,of],"done":[…],"next":[…]}]}`. `sample: true` shows a "fictional figures"
  callout with `note`; `launch_after` = index of the month after which the new site went live (chart marker).
- Tests (offline, stdlib): `python3 -m unittest discover -s .agents/skills/findability-score/scripts`.

## What the parts mean (labels are in the report, both languages)

| Part | Checks | Channel |
|---|---|---|
| Every page says what it is about | title 15-65 chars + unique per language, description 50-170 + unique, one h1, `lang`, canonical, Open Graph, alt text | both |
| Google and AI can read everything | 200s, https, no noindex, robots.txt allows Google + GPTBot/ClaudeBot/PerplexityBot/OAI-SearchBot, those bots really get a 200 (CDN bot blocking), sitemap, text without JS | both |
| Your details are unambiguous | LocalBusiness-type JSON-LD, its fields (address, phone, hours, geo/map, image, sameAs), valid JSON, phone on every page, tel:/mailto: | both |
| Answers to what people ask | a visible FAQ, FAQPage markup, ≥200 words, subheadings, town in title/first lines | mostly AI |
| Found in English too | hreflang on every page (only when the site has 2+ languages) | both |
| Fast on a phone | Lighthouse mobile performance (fallback: page weight + server time) | Google |

## Rules

- Never promise rankings or AI mentions: the report's method note says so; keep it.
- A score is evidence, not a goal: fix what helps visitors ([website-dev seo-geo.md](../website-dev/references/seo-geo.md)),
  never a check for its own sake (no `llms.txt`, no FAQ written for the score).
- Show the report in a browser before sending it (light, phone width too). Old site worse on a part? Say it plainly.
