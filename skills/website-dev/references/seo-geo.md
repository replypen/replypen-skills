# Search and AI answers (SEO + GEO) for a site you build or change

<!-- Condensed from ReplyPen's host skills `skills/website/seo.md` and `skills/geo/` (repo replypen/replypen): change one, align the other. -->

Search engines and AI answer engines (ChatGPT, Perplexity, Google AI Overviews) reward what a careful
visitor wants: plain text that says who, what, where, for whom, when and at what price, under headings
that name each section. No special "AI optimisation" exists; this is visitor-first craft. Never write
for a machine. On a change, apply it to the pages you touch; on a **new site** (first build after the
kickstart), apply all of it before the first preview.

## Every page

| Item | Rule |
|---|---|
| Title + description | Title ~30-60 chars naming the topic; description ~70-155 chars, one plain sentence with the key facts. |
| Headings | One `h1` naming the topic (the layout may supply it). Each heading says what follows ("Prijs en inschrijven", not "Meer info"). |
| First lines | What, for whom, where, when, price, how to book, in the first paragraph, as real text. |
| Real text | Headings, prices and dates live in the HTML, never only inside an image. |
| Alt text | Every image: what it shows, in the page's language, ≤ 125 chars; decorative `alt=""`. |
| Links | Link text says where it goes; prose links to the site's own page on that topic; every page reachable from the menu or a related page. |
| One fact, one value | Facts live once in the data file (`_data/site.yml`) and render everywhere; a contradiction makes engines drop the fact. |
| Address (URL) | Short lowercase slug of real words. Changing an existing URL only with a redirect. |
| `lang`, canonical, Open Graph | Set by the layout: check `lang` matches the copy, canonical is the page's own URL, `og:title/description/image` exist. |

## Site level (new site, or when touched)

- **Crawlable:** `robots.txt` does not block GPTBot, ClaudeBot, PerplexityBot, Google-Extended, Bingbot or
  Googlebot; a sitemap exists; pages render their text server-side (no JS-only content); every page 200.
- **Structured data** (JSON-LD in `<head>`): `Organization` or `LocalBusiness` on the homepage with only
  facts visible on the site; `Event` for a dated activity page; `FAQPage` only for a real visible FAQ.
  Unknown value ⇒ leave the property out and ask; validate with Google's Rich Results Test. A malformed
  block is worse than none.
- **Proof** a camp/practice really has (a real number, a quote from a real review, an accreditation with
  a link): show it; AI answers cite pages that carry it. Never invent it.
- **Fresh:** no last-year dates, past "inschrijvingen open", "dit jaar" without a year.
- **Off-site (ask the owner):** a claimed Google Business profile and directory listings with the same
  address, hours and phone as the site.

## Never

- Keyword stuffing, hidden text, meta keywords, `llms.txt` or other "AI files" as a visibility trick.
- Promising rankings, traffic or AI mentions.
- An FAQ only for "rich results"; inventing a fact (price, review count, founding year) to fill a gap.
- Removing a `noindex`, canonical or `robots.txt` rule without asking: it may be deliberate.
