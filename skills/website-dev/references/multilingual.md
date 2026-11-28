# Multilingual sites: keep it simple

How our sites usually do it; each site checks what fits (an Astro site uses its built-in i18n routing, an Eleventy
site plain folders). Start from the languages the customer really serves; a language nobody maintains goes stale.

**URLs.** Default language without prefix, the others under `/<code>/` (`/werkwijze`, `/en/werkwijze`). Keep the
default language's slug in the other languages unless the customer wants translated slugs (more SEO, more upkeep: a
renamed slug needs a 301). Taking over an old site: reuse its URL scheme, so the domain move needs no redirects.

**Where text lives.** Page text in one file per language (`en/werkwijze.html`, Astro `src/pages/[locale]/…` or a
content collection per locale). Interface text (menu, buttons, footer labels, form errors) in one strings file per
language (`_data/i18n.yml`, `src/i18n/<code>.ts`). Facts stay single-source: add `*_en` variants in the data file only
where the value really differs. The page's language comes from data (Eleventy: a directory data file `en/en.json`
with `{"lang": "en"}`; global default in `_data/lang.json`).

**Switcher.** A `<details>` list (no JS) linking to **the same page** in each language, each language in its own
name (Nederlands, English), no flags, `hreflang` on the links. No redirect by IP or browser language. A page without
a twin links to the other language's home (or is left out of that language's switcher).

**Head + sitemap.** `<html lang>` per page; a self `canonical`; `hreflang` alternates for every published version plus
`x-default` (the default language); `og:locale`. A missing translation is not published (no default-language body
under `/en/`). Sitemap: list every language's URLs (alternates optional).

**Forms and widgets.** Error messages and embedded widgets follow `document.documentElement.lang`; a form keeps its
`_next`/`_back` per language (`/en/contact/bedankt`).

**Upkeep.** A text change in one language: change the twin too, or say it still needs translating. Use the
customer's own existing translations first; machine-translate only what is missing and tell the owner.
Optional at scale: a check that every page has its twins and every strings key exists in every language.
