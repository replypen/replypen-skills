# Site-wide behaviour: where a rule lives, how it is applied

North star: the built HTML says what the page does; JavaScript only adds what cannot exist before the browser runs.

- **Owner first.** One site's rule → that site's repo. One company's sites → its kickstart profile, wrapper skill
  and `_data/site.yml`. The shared template only takes what every site wants: no company names, domains or
  one customer's policy there.
- **Lowest rung that works:** authored HTML for one-offs (`target`, `rel`, `loading` on the element) → build time
  for a repeated rule (layout, include, or an Eleventy transform driven by `_data/site.yml`) → runtime JS only for
  markup that exists only in the browser, set by the component that creates it. No page-wide DOM rewrite or
  click/focus interceptor to patch markup the build could emit.
- Standard HTML before an invented attribute (`target="_self"`, not a custom `data-*` opt-out).
- A UX request against common guidance (forced new tabs, autoplay, pop-ups): build it scoped to the sites that
  asked, and name the trade-off once with a source (new tabs: WCAG techniques
  [G200](https://www.w3.org/WAI/WCAG22/Techniques/general/G200), [G201](https://www.w3.org/WAI/WCAG22/Techniques/general/G201)).
- Check the rule in `_site/` (it holds without JS) and dynamic content after it appears.

Example (2026-11): "external links open in a new tab, except KampAdmin" landed as a runtime script with
`kampadmin.be` hardcoded in the shared template and was reverted. Right shape: an opt-in Eleventy transform
reading `_data/site.yml` in the company's sites; the credit line keeps its authored `target="_blank"`.

## Data from an outside system: build time or runtime

Same ladder for data (offer, prices, availability). Decide by **freshness**, not size:

| | Build time (snapshot in the page, regenerated + redeployed) | Runtime (one fixed, CDN-cached URL per page) |
|---|---|---|
| Fits | data that changes per season; also large sets (compact columns/rows compress well) | data that must be right to the minute (spots, sold out) |
| Costs | stale until the next build; needs a regenerate trigger (on change, or daily) | a fetch on every visit; API down = empty page, so show a fallback link |

- Fetch the whole set once and filter in the browser up to ~1000 items. Beyond that, filter on the server
  (query params), which loses the shared CDN cache: only then.
- Don't bake "stable" lookup tables while fetching the main rows live: little saving if the API already
  inlines them, and a new lookup row breaks rows until the next build.
- One page per item (generated at build time, front matter = id) is for SEO text; the live parts load on it.
- Reference: KampAdmin `site-demo-jeugdwerk` `/zoeker/` (runtime), `/snelzoeker/` (build time), `/kaart/` (runtime + map).

## Dropdown in the main nav, without a framework

A `<button aria-expanded aria-controls>` + `<ul>`; the parent item is the button, not a link. CSS opens it on hover
only under `@media (hover: hover)`; ~25 lines of JS toggle a class + `aria-expanded` on click, close on Escape (focus
back to the button), on focus leaving, and on an outside click. At phone width let the panel span the nav width,
else it runs off-screen. Check one line at 1280 px and the open panel at 390 px.
