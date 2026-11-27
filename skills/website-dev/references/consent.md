# Cookie consent on a site: one data file, no banner until needed

Standard for every company's sites: [vanilla-cookieconsent v3](https://github.com/orestbida/cookieconsent) (MIT,
~24 KB JS + 32 KB CSS), self-hosted (our CSP allows only `'self'` scripts), driven by `_data/cookies.yml`. No
Cookiebot or other paid banner. Files to copy: [assets/consent/](../assets/consent/) (also wired into `replypen/site-template`);
live example: [site-demo-jeugdwerk](https://site-demo-jeugdwerk.kampadmin-sites.workers.dev/) (one demo analytics script).

> [!IMPORTANT]
> **Only strictly necessary storage → no banner** (Belgian DPA, [GBA cookies](https://www.gegevensbeschermingsautoriteit.be/burger/thema-s/internet/cookies)),
> but still list it on `/cookies`. localStorage/sessionStorage count like cookies
> ([EDPB Guidelines 2/2023](https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202302_technical_scope_art_53_eprivacydirective_v2_en_0.pdf)).
> Analytics, ads, pixels, GTM, a chat widget that tracks: consent first. Exempt: security (bot check), a session the
> visitor asked for (login, cart, form input), a UI preference, the consent cookie itself
> ([WP29 Opinion 04/2012](https://ec.europa.eu/justice/article-29/documentation/opinion-recommendation/files/2012/wp194_en.pdf)).
> The site owner is controller and owns the policy prose; the template text is a start, not legal advice.

## Files (copy from [assets/consent/](../assets/consent/), dropping `.txt`; the lib from npm)

`.txt` keeps Eleventy from building the skill copy in a consumer's `.agents/` as pages; such a site should also
`eleventyConfig.ignores.add(".agents/**")` and `".claude/**"`.


| File | Role |
|---|---|
| `_data/cookies.yml` | The only place: `gtm_id`, `consent_mode`, `policy_url`, `categories`, `scripts`, `cookies`, banner texts. Comments in it say how to add a tool. |
| `_includes/consent.html` | In `<head>`. Renders nothing while `categories` holds only `necessary` (dormant). Else: JSON config block, vendored lib, `assets/consent.js`, and each `scripts` entry as `<script type="text/plain" data-category data-src>` that the lib runs after consent. |
| `assets/consent.js` (+ a few `#cc-main { --cc-btn-primary-bg: … }` lines in the site CSS for house colours) | Google Consent Mode v2 default (all denied) → `CookieConsent.run` → on every choice: `gtag('consent','update')`, GTM load (basic mode: only after analytics or marketing consent), `window.kaConsent` + `ka:consent` event for our own scripts (KampAdmin embed). |
| `assets/vendor/cookieconsent-<version>/` | Unmodified `dist/cookieconsent.umd.js`, `.css`, `LICENSE` from `https://registry.npmjs.org/vanilla-cookieconsent/-/vanilla-cookieconsent-<version>.tgz` (3.3.0 tested). Upgrade = new folder + the two paths in `consent.html`. |
| `_includes/cookie-table.html`, `cookies.html` (set `permalink` to the site's URL style) | `/cookies`: one table per category from the same yml, so banner and policy can't drift. |
| footer (add by hand) | Link to `/cookies`; when active also `<button data-cc="show-preferencesModal">Cookie-instellingen</button>` (reopens the choice). |

The includes read `cookies` (template: every `_data/*.yml` is global) or `site.data.cookies` (Jekyll-style sites):
`{% assign ck = cookies | default: site.data.cookies %}`, so the same files work in both.

## Switching it on for a customer

1. List their tools (GTM container contents, pixels, chat). Each gets a category, its cookies and its domains.
2. `categories`: add `analytics` and/or `marketing` (fixed ids: they map to Consent Mode `analytics_storage` /
   `ad_storage, ad_user_data, ad_personalization`; `preferences` → functionality/personalization).
3. `gtm_id` or `scripts` entries; cookie rows (name ending in `*` = prefix, also auto-cleared on reject).
4. CSP in `_headers`: GTM needs `script-src https://www.googletagmanager.com` plus whatever its tags load
   (`connect-src`/`img-src` for GA: `*.google-analytics.com`, `*.analytics.google.com`).
5. Tags inside their GTM container must respect Consent Mode (Google tags do; others: the customer's or agency's job,
   say so in the offer). `consent_mode: advanced` (GTM loads before the choice, cookieless pings) only on request.

## Check (browser, fresh profile)

- Before any click: `document.cookie` empty, `localStorage` without tool keys, no gated script requested
  (network tab), `dataLayer[0]` = consent default denied.
- "Enkel noodzakelijke" → only `cc_cookie`; reload: no banner, still nothing loaded.
- Footer "Cookie-instellingen" → modal; "Alles aanvaarden" → the gated script loads, its cookie appears,
  `dataLayer` has `consent update … granted`. Reject again → its `*` cookies are gone.
- Accept and reject buttons look equal (same weight is a GBA expectation). 390 px: banner fits, table scrolls.
- Headless browsers: the lib hides the banner from bots (`navigator.webdriver`); use a real browser profile.

Pricing and who may switch it on: the company's wrapper skill (e.g. KampAdmin `customer-websites`).
