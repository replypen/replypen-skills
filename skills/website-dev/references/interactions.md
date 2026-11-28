# Interactions (carousel, lightbox, menus, tabs): native first, a library when it earns it

Hints, not a standard: each site picks what fits. The ladder from [site-behaviour.md](site-behaviour.md) applies:
HTML and CSS first, a few lines of own JS next, a library last.

| Need | Native / own JS (usually enough) | Library when the need grows |
|---|---|---|
| Enlarge a photo (lightbox) | `<dialog>` + `showModal()`: focus trap, Escape and `::backdrop` come free; ~40 lines for prev/next, arrow keys, backdrop click, focus back to the thumbnail | [PhotoSwipe](https://photoswipe.com) (pinch-zoom, swipe, responsive sources), [GLightbox](https://biati-digital.github.io/glightbox/) (also video) |
| Photo strip / carousel | `overflow-x: auto` + `scroll-snap-type`; hide the bar (`scrollbar-width: none` + `::-webkit-scrollbar`), prev/next buttons calling `scrollBy`, `cursor: zoom-in` on clickable photos | [Embla Carousel](https://www.embla-carousel.com) (loop, autoplay, dots) |
| Disclosure, FAQ, simple dropdown, mobile menu, language switcher | `<details>`/`<summary>` (no JS, keyboard and screen reader for free) | none |
| Nav dropdown with hover + full keyboard rules | button + `aria-expanded`, see site-behaviour.md | none |
| Small reactive bits (tabs, filters, toggles on many pages) | own JS | [Alpine.js](https://alpinejs.dev): its **CSP build** (`@alpinejs/csp`), the standard build needs `'unsafe-eval'`, which the template CSP blocks |

- **Vendor, don't hot-link.** The template CSP is `script-src 'self'`: copy the pinned file into
  `assets/vendor/<name>-<version>/` (like cookieconsent), with its licence. A CDN (`cdn.jsdelivr.net/npm/<pkg>@<exact>`)
  means widening the CSP for that host: only with a reason, and always an exact version.
- One library per job across the site; drop it again when native covers it (e.g. `<dialog>`, `popover`).
- Respect `prefers-reduced-motion` (no smooth scroll or zoom animations), keep controls ≥ 44 px on touch, give every
  icon button an `aria-label` in the page's language.
- Check: the photo opens and closes with mouse, keyboard (Enter, arrows, Escape) and touch at 390 px; without JS the
  strip still scrolls and the images still show.
