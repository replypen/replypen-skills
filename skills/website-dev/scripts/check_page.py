#!/usr/bin/env python3
"""Fetch a rendered preview page and assert what a diff cannot show.

A diff proves what you changed; it proves nothing about the page a human will open. This fetches the
preview URL and checks the failures that actually happen: a page that 404s, an `<img>` pointing at a
URL that does not exist, an internal link into nowhere, a section that silently did not render, a page
indexed in the wrong place (a dev/preview address search engines may index, or a live page that hides
from them), and (for KampAdmin sites) a booking embed that stays a loading spinner because jQuery loads too late.

    python /skills/website/scripts/check_page.py https://preview.example/kampen/koken/ \\
        --expect-selector "#inschrijven" --expect-selector ".facts" --embed kampadmin

Stdlib only (urllib + html.parser), so it runs in the workspace container as-is. Every network call
goes through the run's egress; a blocked host reads as a failed check, not as a crash.
Exit code 1 as soon as one check fails.

Two copies, kept byte-identical: ReplyPen's host skill `skills/website/scripts/check_page.py` (repo
replypen/replypen, mounted at /skills for the chat agent) and `skills/website-dev/scripts/check_page.py`
(public repo replypen/replypen-skills, vendored into site repos for coding agents). Change one, copy it to
the other and `cmp` them.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "rootcause-check-page/1.0"
TIMEOUT = 15
MAX_LINKS = 30  # per page, per kind: a check that walks a whole site is a crawler, not a check
MAX_WORKERS = 8
JQUERY_HINTS = ("jquery",)
EMBED_SCRIPT = "ka-embedv4"
DEV_HOST_SUFFIXES = (".workers.dev", ".pages.dev")  # previews + a site before its domain move
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")


# --- fetching --------------------------------------------------------------------------------


def fetch(url: str, method: str = "GET") -> dict:
    """{'status', 'body', 'headers', 'error'} — never raises. `body` is text only for GET on HTML."""
    request = Request(url, method=method, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - http(s) only, see below
            raw = response.read(2_000_000) if method == "GET" else b""
            charset = response.headers.get_content_charset() or "utf-8"
            return {"status": response.status, "body": raw.decode(charset, "replace"),
                    "headers": dict(response.headers), "error": None}
    except HTTPError as exc:
        return {"status": exc.code, "body": "", "headers": {}, "error": None}
    except (URLError, OSError, ValueError) as exc:
        return {"status": 0, "body": "", "headers": {}, "error": str(getattr(exc, "reason", exc))}


def probe(url: str) -> dict:
    """HEAD first (cheap), GET as the fallback — plenty of CDNs answer 405/403 to HEAD."""
    head = fetch(url, "HEAD")
    if 200 <= head["status"] < 300:
        return head
    return fetch(url, "GET")


def probe_all(urls: list[str]) -> dict:
    if not urls:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(urls))) as pool:
        return dict(zip(urls, pool.map(probe, urls)))


# --- parsing ---------------------------------------------------------------------------------


class _Page(HTMLParser):
    """Collects only what the checks need: elements (tag/id/class), images, links, scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, str, set]] = []
        self.images: list[str] = []
        self.links: list[str] = []
        self.scripts: list[dict] = []
        self.theme_urls: list[str] = []
        self.ids: list[str] = []
        self.robots: list[str] = []

    def handle_starttag(self, tag, attrs):
        adict = {k: (v or "") for k, v in attrs}
        self.elements.append((tag, adict.get("id", ""), set(adict.get("class", "").split())))
        if adict.get("id"):
            self.ids.append(adict["id"])
        if adict.get("data-theme-url"):
            self.theme_urls.append(adict["data-theme-url"])
        if tag == "meta" and adict.get("name", "").lower() in ("robots", "googlebot"):
            self.robots.append(adict.get("content", "").lower())
        if tag == "img" and adict.get("src"):
            self.images.append(adict["src"])
        elif tag == "a" and adict.get("href"):
            self.links.append(adict["href"])
        elif tag == "script" and adict.get("src"):
            self.scripts.append({"src": adict["src"], "order": len(self.scripts),
                                 "defer": "defer" in adict or "async" in adict})

    handle_startendtag = handle_starttag


def parse(body: str) -> _Page:
    page = _Page()
    page.feed(body)
    page.close()
    return page


def matches(selector: str, elements) -> int:
    """`#id`, `.class`, `tag`, and the combinations `tag#id` / `tag.class` / `.a.b`."""
    selector = selector.strip()
    want_tag, want_id, want_classes = "", "", set()
    token, kind = "", "tag"
    for char in selector + "\0":
        if char in "#.\0":
            if token:
                if kind == "tag":
                    want_tag = token.lower()
                elif kind == "id":
                    want_id = token
                else:
                    want_classes.add(token)
            token, kind = "", {"#": "id", ".": "class"}.get(char, kind)
        else:
            token += char
    return sum(1 for tag, el_id, classes in elements
               if (not want_tag or tag == want_tag)
               and (not want_id or el_id == want_id)
               and want_classes <= classes)


# --- checks ----------------------------------------------------------------------------------


def _ok(status) -> bool:
    return 200 <= status < 300


def check_embed(page: _Page) -> list[dict]:
    """The KampAdmin booking embed: one anchor div, its script, and jQuery running BEFORE it."""
    out = []
    anchors = sum(1 for el_id in page.ids if el_id == "kampadmin-booking")
    out.append({"name": "embed: exactly one #kampadmin-booking", "ok": anchors == 1,
                "detail": f"{anchors} gevonden"})

    embeds = [s for s in page.scripts if EMBED_SCRIPT in s["src"]]
    out.append({"name": f"embed: <script src=…{EMBED_SCRIPT}.js>", "ok": bool(embeds),
                "detail": embeds[0]["src"] if embeds else "niet gevonden op de pagina (ook niet in <head>)"})

    if embeds:
        embed = embeds[0]
        jqs = [s for s in page.scripts if any(h in s["src"].lower() for h in JQUERY_HINTS)]
        # A sync script always runs before a deferred one; two deferred scripts run in document
        # order; a deferred jQuery before a sync embed is the real-world breakage.
        good = [j for j in jqs
                if (not j["defer"] and embed["defer"]) or (j["defer"] <= embed["defer"] and j["order"] < embed["order"])]
        out.append({"name": "embed: jQuery loads before the embed", "ok": bool(good),
                    "detail": (good[0]["src"] if good else
                               ("geen jQuery <script> gevonden" if not jqs else
                                f"{jqs[0]['src']} draait ná {embed['src']} (defer/volgorde)"))})

    bad = [u for u in page.theme_urls if "embedded=" in u]
    out.append({"name": "embed: data-theme-url zonder embedded=", "ok": not bad,
                "detail": bad[0] if bad else "ok"})
    return out


def check_indexing(url: str, page: _Page, headers: dict, allow_noindex: bool) -> list[dict]:
    """Dev and preview addresses must stay out of search engines; the live site must be findable."""
    host = (urlparse(url).hostname or "").lower()
    if host in LOCAL_HOSTS:
        return []
    header = next((v for k, v in headers.items() if k.lower() == "x-robots-tag"), "").lower()
    noindex = any("noindex" in c for c in page.robots) or "noindex" in header
    if host.endswith(DEV_HOST_SUFFIXES):
        return [{"name": "index: dev/preview-adres is noindex", "ok": noindex,
                 "detail": "ok" if noindex else f"{host} mag geïndexeerd worden: zoekmachines kunnen deze kopie vinden"}]
    return [{"name": "index: live pagina is indexeerbaar", "ok": not noindex or allow_noindex,
             "detail": "ok" if not noindex else
             ("noindex, toegestaan met --allow-noindex" if allow_noindex else
              "noindex op de live site: zoekmachines en AI-antwoorden slaan deze pagina over")}]


def check_page(url: str, expect_selectors=(), embed: str = "", allow_noindex: bool = False) -> dict:
    checks: list[dict] = []
    response = fetch(url)
    checks.append({"name": f"GET {url}", "ok": response["status"] == 200,
                   "detail": response["error"] or f"HTTP {response['status']}"})
    result = {"url": url, "status": response["status"], "checks": checks}
    if response["status"] != 200:
        result["ok"] = False
        return result

    page = parse(response["body"])

    images = []
    for src in page.images:
        if src.startswith("data:"):
            continue
        absolute = urljoin(url, src)
        if urlparse(absolute).scheme in ("http", "https") and absolute not in images:
            images.append(absolute)
    origin = urlparse(url)
    internal = []
    for href in page.links:
        if href.startswith("/") and not href.startswith("//"):
            absolute = urljoin(f"{origin.scheme}://{origin.netloc}", href)
            if absolute not in internal:
                internal.append(absolute)

    for label, urls in (("afbeelding", images[:MAX_LINKS]), ("interne link", internal[:MAX_LINKS])):
        for target, probed in probe_all(urls).items():
            checks.append({"name": f"{label} {target}", "ok": _ok(probed["status"]),
                           "detail": probed["error"] or f"HTTP {probed['status']}"})

    for selector in expect_selectors:
        found = matches(selector, page.elements)
        checks.append({"name": f"selector {selector}", "ok": found >= 1, "detail": f"{found}×"})

    checks.extend(check_indexing(url, page, response["headers"], allow_noindex))

    if embed == "kampadmin":
        checks.extend(check_embed(page))

    result["ok"] = all(c["ok"] for c in checks)
    result["capped"] = {"images": len(images) > MAX_LINKS, "links": len(internal) > MAX_LINKS}
    return result


def render(results: list[dict]) -> str:
    lines = []
    for result in results:
        lines.append(result["url"])
        lines += [f"  {'✓' if c['ok'] else '✗'} {c['name']} — {c['detail']}" for c in result["checks"]]
        capped = [k for k, v in result.get("capped", {}).items() if v]
        if capped:
            lines.append(f"  … alleen de eerste {MAX_LINKS} gecontroleerd ({', '.join(capped)})")
    failed = sum(1 for r in results for c in r["checks"] if not c["ok"])
    total = sum(len(r["checks"]) for r in results)
    lines.append(f"{total - failed}/{total} checks ok over {len(results)} pagina('s)"
                 + ("" if failed else " — niets gevonden dat een bezoeker zou opvallen"))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch preview pages and check images, internal links, expected sections and the embed.",
        epilog='example: python /skills/website/scripts/check_page.py https://preview.example/ '
               '--expect-selector "#inschrijven" --embed kampadmin')
    parser.add_argument("urls", nargs="+", help="Preview URLs to check.")
    parser.add_argument("--expect-selector", action="append", default=[], metavar="CSS",
                        help="#id, .class, tag (or tag.class) that must appear at least once. Repeatable.")
    parser.add_argument("--embed", choices=["kampadmin"], default="",
                        help="Also check the booking embed wiring on every page.")
    parser.add_argument("--allow-noindex", action="store_true",
                        help="A live page that is noindex on purpose (thank-you page, 404).")
    parser.add_argument("--json", action="store_true", help="Structured payload instead of text.")
    args = parser.parse_args(argv)

    results = [check_page(url, args.expect_selector, args.embed, args.allow_noindex) for url in args.urls]
    print(json.dumps({"pages": results, "ok": all(r["ok"] for r in results)}, indent=2, ensure_ascii=False)
          if args.json else render(results))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
