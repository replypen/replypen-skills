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
