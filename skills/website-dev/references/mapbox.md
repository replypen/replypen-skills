# Mapbox on a site: a map with pins + a place search

Use Mapbox when a site needs a search box (type a town → results nearby) together with a map with pins. A plain
location map without search runs on MapLibre + OpenFreeMap, with no account and no token. Facts below were
verified on 2026-11-27. Docs change fast, so read the current version as Markdown:
[docs.mapbox.com/llms.txt](https://docs.mapbox.com/llms.txt). Every docs page also has a `.md` version, and there
is a Docs MCP at `https://mcp-docs.mapbox.com/mcp` that needs no key.

> [!IMPORTANT]
> **One Mapbox account per company that owns the sites**, e.g. one for all KampAdmin sites. A big client may get
> its own account, but only in the client's name and on the client's card, so it can take the account over.
> Mapbox's [ToS](https://www.mapbox.com/legal/tos) forbids extra accounts "for the purpose of not exceeding the
> monthly free usage credits" and lets Mapbox bill what you saved. That rules out `info+x@` accounts of our own
> made for a second free tier.

## 1 · Token (public: it ships in the page, so it is not a secret)

Create it under **Account → Tokens → Create a token**.

- **Name:** after the site, e.g. `site-heyo - kaart /kampen/`.
- **Scopes:** public only. Keep `styles:tiles`, `styles:read` and `fonts:read`; untick the rest. Geocoding works
  with any token.
- **URLs:** no wildcards, up to 100 entries. A listed domain also covers its own subdomains.
  - Add the live domain, `localhost` and the exact workers.dev host.
  - A preview host `<branch>-<site>.<account>.workers.dev` is a sibling of the live host, not a subdomain of it,
    so add each preview host you need. Never add bare `workers.dev`.
- **Where it goes:** commit it to the site repo as `_data/mapbox.yml` (`public_token: pk.…`). The page reads it
  with `window.MAPBOX = {{ site.data.mapbox | jsonify }}`. No secret store and no deploy change; a chat edit can
  paste it too.
- **Check it:** a new token takes about a minute to activate. Then:
  `curl -H "Referer: https://<live>/" "…/geocode/v6/forward?q=Gent&access_token=pk…"` returns 200, and any other
  referer returns 403. The browser must send a Referer, so the site must not set `Referrer-Policy: no-referrer`
  or `same-origin`.
- **Usage per site:** the Statistics page filters by token. There is no usage API and no spending cap; set usage
  alerts instead.

**CSP** (if the site sets one, from [Mapbox's guide](https://docs.mapbox.com/mapbox-gl-js/guides/security-and-testing.md)):
add `script-src` and `style-src https://api.mapbox.com`, `connect-src https://api.mapbox.com https://events.mapbox.com`,
`worker-src blob:` and `img-src data: blob:`.

## 2 · Place search: Geocoding v6, not the Search Box API

`GET https://api.mapbox.com/search/geocode/v6/forward?q=…&access_token=pk…`
([docs](https://docs.mapbox.com/api/search/geocoding.md)). It is billed per request with 100k free per month,
far cheaper than Search Box sessions.

Results below are from live tests on 2026-11-27:

| Knob | Use | Why (tested) |
|---|---|---|
| `country=be` | Always; ISO code = a hard filter (`be,nl` for two countries) | Without it, "Bree" returns Breezewood, USA first |
| `types=place,locality,postcode` | Municipalities, sub-municipalities, postcodes; no streets | `place` alone misses Wilsele (a `locality`) |
| `language=nl` | The site's language | "Bergen" and "Luik"; "Liège" still finds Luik |
| `proximity=<lng>,<lat>` | Soft bias toward the region (Flanders: `4.45,50.95`) | "Hal" gives 4 suggestions instead of 1; "Mons" finds Bergen |
| `bbox=minLng,minLat,maxLng,maxLat` | Hard area limit, only for a strictly regional site | It cuts off everything just outside the box |
| `limit=5`, `autocomplete=true` | Suggestions while typing (max 10) | — |

On the client side:

- Debounce typing by 250 ms and start from 2 characters; every keystroke is a billed request.
- Only the newest response may render.
- Put an exact name match first: autocomplete puts "Herentals" before "Herent".

**Rules** (Temporary Geocoding, Product Terms 2.7):

- Never store or cache a result, not in KV and not in the URL.
- Never show its latitude or longitude.
- Using it in memory to filter or sort by distance and to place it on a map is allowed.
- For a shareable link, keep the place name (`?plaats=Herent`) and geocode it again on load.
- To store coordinates, use `permanent=true`, which is paid and needs a card on file.

## 3 · Map with pins

Load Mapbox GL JS from `https://api.mapbox.com/mapbox-gl-js/vX.Y.Z/mapbox-gl.{js,css}`, pinning a release at least
2 weeks old (npm `mapbox-gl`).

- **Load on view:** start the map only when it scrolls into view (IntersectionObserver); every map load is billed.
- **Pins:** one GeoJSON source with `cluster: true`, one pin per location, with several items sharing one pin
  ([cluster example](https://docs.mapbox.com/mapbox-gl-js/example/cluster.md)). Clicking a cluster runs
  `getClusterExpansionZoom` → `easeTo`.
- **Tile ↔ pin:**
  - Hovering a tile shows one DOM `Marker` halo at its location; it works even when the pin sits inside a cluster.
  - Hovering a pin highlights its tiles; hovering a cluster highlights the tiles of all its pins
    (`getClusterLeaves`).
  - Clicking a pin opens a `Popup` built with `textContent`, never `innerHTML` with API text, and scrolls the list
    to the tile.
- **After a search:** draw the radius as a polygon with a dashed outline and add an origin `Marker`. Fit to the
  origin plus its results, not the whole circle, so close pins don't merge into one cluster.
- **Phones:** `cooperativeGestures: true` so the page still scrolls past the map; at phone width the map sits on
  top of the list.

A working reference with all of the above (~280 lines), built for camps:
[`kampadmin/site-demo-jeugdwerk`](https://github.com/kampadmin/site-demo-jeugdwerk), private, at
`/kaart/` (`kaart.html`, `assets/ka-kaart.js`).
