#!/usr/bin/env python3
"""How well will a website be found in Google and in AI assistants? Old vs new, in plain words.

    python3 score_site.py compare https://old.example https://new.example --lang nl --name "Praktijk X" \\
        --out report.html [--assume-indexable new] [--lighthouse] [--rankings r.json] [--ai-answers a.json] [--ideas i.json]
    python3 score_site.py score https://site.example --json site.json [--assume-indexable]
    python3 score_site.py monthly history.json --lang nl --out monthly.html

Deterministic checks only (fetch + parse, no LLM): the same site gives the same score. Stdlib only; `--lighthouse`
shells out to `pnpm dlx lighthouse` + local Chrome for mobile speed. See ../SKILL.md for what each part means.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36 findability-score/1.0"
# User agents the big answer engines and search engines crawl with (robots.txt names + a realistic UA string).
AI_FETCHERS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
}
ROBOTS_AGENTS = ["Googlebot", "Bingbot", "Google-Extended", "Applebot", *AI_FETCHERS]
BUSINESS_TYPES = {"LocalBusiness", "Dentist", "MedicalBusiness", "MedicalClinic", "Physician", "MedicalOrganization",
                  "Organization", "ProfessionalService", "HealthAndBeautyBusiness", "SportsActivityLocation",
                  "EducationalOrganization", "Corporation", "LodgingBusiness", "TouristAttraction"}
BUSINESS_FIELDS = ["name", "address", "telephone", "url", "openingHoursSpecification", "geo", "image", "sameAs"]
MAX_PAGES = 20
TIMEOUT = 20


# --- fetching -------------------------------------------------------------------------------------------------------


def fetch(url: str, ua: str = BROWSER_UA, method: str = "GET") -> dict:
    """{'url' (after redirects), 'status' (0 = no answer), 'headers', 'body', 'bytes', 'ttfb'}; never raises."""
    t0 = time.monotonic()
    try:
        if urlparse(url).scheme not in ("http", "https"):
            raise ValueError(f"not http(s): {url[:80]}")
        req = Request(url, method=method, headers={"User-Agent": ua, "Accept-Language": "nl,en;q=0.8"})
        with urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - scheme checked above
            first = r.read(1)
            ttfb = time.monotonic() - t0
            raw = first + (r.read(3_000_000) if method == "GET" else b"")
            try:
                body = raw.decode(r.headers.get_content_charset() or "utf-8", "replace")
            except LookupError:  # unknown charset name
                body = raw.decode("utf-8", "replace")
            return {"url": r.url, "status": r.status, "headers": {k.lower(): v for k, v in r.headers.items()},
                    "body": body, "bytes": len(raw), "ttfb": ttfb}
    except HTTPError as e:
        return {"url": url, "status": e.code, "headers": {k.lower(): v for k, v in (e.headers or {}).items()},
                "body": "", "bytes": 0, "ttfb": time.monotonic() - t0}
    except (URLError, OSError, ValueError) as e:
        return {"url": url, "status": 0, "headers": {}, "body": "", "bytes": 0, "ttfb": 0, "error": str(e)}


class Page(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.title = ""
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.hreflang: dict[str, str] = {}
        self.h1 = 0
        self.headings: list[str] = []
        self.imgs: list[dict] = []
        self.links: list[str] = []
        self.ld: list[str] = []
        self.summaries = 0
        self.accordions = 0  # CMS accordion items (class accordion / faq-item): an FAQ without <details>
        self.text: list[str] = []
        self._stack: list[str] = []
        self._ld = False
        self._cap: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link":
            rel = a.get("rel", "").lower().split()
            if "canonical" in rel:
                self.canonical = a.get("href", "")
            if "alternate" in rel and a.get("hreflang"):
                self.hreflang[a["hreflang"].lower()] = a.get("href", "")
        elif tag == "img":
            self.imgs.append(a)
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "script" and "ld+json" in a.get("type", ""):
            self._ld = True
            self._buf = []
        elif tag == "summary":
            self.summaries += 1
        if re.search(r"(^|\s)(accordion|accordion-item|faq-item|faq-question)(\s|$)", a.get("class", "")):
            self.accordions += 1
        if tag in ("title", "h1", "h2", "h3"):
            self._cap, self._buf = tag, []
            if tag == "h1":
                self.h1 += 1
        if tag not in ("meta", "link", "img", "br", "hr", "input", "source"):
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "script" and self._ld:
            self.ld.append("".join(self._buf))
            self._ld = False
        if tag == self._cap:
            txt = " ".join("".join(self._buf).split())
            if tag == "title":
                self.title = txt
            else:
                self.headings.append(txt)
            self._cap = None
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self._ld or self._cap:
            self._buf.append(data)
        if not any(t in self.SKIP for t in self._stack):
            self.text.append(data)

    @property
    def words(self) -> list[str]:
        return " ".join(self.text).split()


def parse(body: str) -> Page:
    p = Page()
    try:
        p.feed(body)
    except Exception:  # noqa: BLE001 - a broken page scores low, it must not crash the run
        pass
    return p


def ld_objects(page: Page) -> tuple[list[dict], int]:
    """All JSON-LD objects (flattening @graph) and the number of blocks that failed to parse."""
    objs, bad = [], 0
    for raw in page.ld:
        try:
            data = json.loads(raw)
        except ValueError:
            bad += 1
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                objs.append(o)
                stack.extend(v for v in o.values() if isinstance(v, dict))  # @graph is a list: covered below
                stack.extend(x for v in o.values() if isinstance(v, list) for x in v if isinstance(x, dict))
    return objs, bad


def types(o: dict) -> set[str]:
    t = o.get("@type", [])
    return {x for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}


# --- crawl ----------------------------------------------------------------------------------------------------------


def crawl(base: str) -> dict:
    base = base.rstrip("/")
    host = urlparse(base).netloc
    home = fetch(base + "/")
    if home["status"] == 200:  # follow a bare-domain → www (or http → https) redirect for everything else
        final = urlparse(home["url"])
        base, host = f"{final.scheme}://{final.netloc}", final.netloc
    robots_txt = fetch(base + "/robots.txt")
    robots = robots_txt["body"] if robots_txt["status"] == 200 else ""
    sitemap_urls = re.findall(r"(?im)^sitemap:\s*(\S+)", robots) or [base + "/sitemap.xml"]
    locs: list[str] = []
    sitemap_ok = False
    for sm in sitemap_urls[:3]:
        r = fetch(rebase(sm, base))
        found = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r["body"]) if r["status"] == 200 else []
        if found:
            sitemap_ok = True
            for loc in found:  # one level of sitemap index
                if loc.endswith(".xml"):
                    sub = fetch(rebase(loc, base))
                    locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sub["body"])
                else:
                    locs.append(loc)
    urls = [base + "/"]
    candidates = [rebase(u, base) for u in locs] or [
        urljoin(base + "/", h) for h in parse(home["body"]).links]
    for u in candidates:
        u = u.split("#")[0]
        if urlparse(u).netloc == host and u not in urls and not re.search(r"\.(pdf|jpe?g|png|zip|xml)$", u, re.I):
            urls.append(u)
    urls = urls[:MAX_PAGES]
    with ThreadPoolExecutor(8) as ex:
        fetched = list(ex.map(fetch, urls))
    with ThreadPoolExecutor(4) as ex:
        bots = dict(zip(AI_FETCHERS, ex.map(lambda ua: fetch(base + "/", ua)["status"], AI_FETCHERS.values())))
    pages = []
    for r in fetched:
        p = parse(r["body"])
        pages.append({"url": r["url"], "status": r["status"], "page": p,
                      "x_robots": r["headers"].get("x-robots-tag", ""), "bytes": r["bytes"], "ttfb": r["ttfb"]})
    return {"base": base, "home": home, "robots": robots, "sitemap_ok": sitemap_ok, "pages": pages, "bots": bots}


def rebase(url: str, base: str) -> str:
    """Sitemaps of a preview often name the production host: score the host we were given."""
    u, b = urlparse(url), urlparse(base)
    return u._replace(scheme=b.scheme, netloc=b.netloc).geturl()


# --- checks ---------------------------------------------------------------------------------------------------------
# part, weight, channels (g = Google, a = AI assistants), plain label, idea when it fails (nl, en)

CHECKS = {
    "title": ("pages", 3, "ga", ("Elke pagina heeft een duidelijke titel", "Every page has a clear title"),
              ("Geef elke pagina een eigen titel van 30-60 tekens die zegt waarover ze gaat.",
               "Give every page its own 30-60 character title that says what it is about.")),
    "title_unique": ("pages", 2, "g", ("Geen twee pagina's met dezelfde titel", "No two pages share a title"),
                     ("Maak elke paginatitel uniek.", "Make every page title unique.")),
    "description": ("pages", 3, "ga", ("Elke pagina heeft een korte samenvatting voor Google",
                                       "Every page has a short summary for Google"),
                    ("Schrijf per pagina één zin (70-155 tekens) met de belangrijkste feiten.",
                     "Write one sentence (70-155 characters) per page with the key facts.")),
    "h1": ("pages", 2, "ga", ("Eén hoofdkop per pagina", "One main heading per page"),
           ("Zet bovenaan elke pagina precies één hoofdkop die het onderwerp noemt.",
            "Put exactly one main heading naming the topic at the top of each page.")),
    "lang": ("pages", 1, "ga", ("De taal van elke pagina is aangegeven", "Each page declares its language"),
             ("Zet de taal van de pagina in de code (lang).", "Declare the page language (lang).")),
    "canonical": ("pages", 1, "g", ("Elke pagina wijst naar haar eigen vaste adres", "Each page names its own address"),
                  ("Voeg per pagina een canonical-link naar het eigen adres toe.",
                   "Add a canonical link to each page's own address.")),
    "share": ("pages", 1, "a", ("Mooi voorbeeld bij delen (titel + foto)", "Nice preview when shared (title + photo)"),
              ("Voeg een deelfoto en -titel toe (Open Graph).", "Add a share image and title (Open Graph).")),
    "alt": ("pages", 2, "ga", ("Foto's hebben een beschrijving", "Photos have a description"),
            ("Beschrijf elke foto in een korte zin (alt-tekst).", "Describe every photo in a short sentence (alt text).")),
    "status": ("access", 3, "ga", ("Alle pagina's openen zonder fout", "All pages open without errors"),
               ("Herstel pagina's die een fout geven.", "Fix pages that return an error.")),
    "https": ("access", 1, "ga", ("Beveiligde verbinding (https)", "Secure connection (https)"),
              ("Zet https aan.", "Switch on https.")),
    "indexable": ("access", 5, "ga", ("Google mag elke pagina opnemen", "Google may list every page"),
                  ("Haal 'noindex' weg van pagina's die gevonden moeten worden.",
                   "Remove 'noindex' from pages that should be found.")),
    "robots": ("access", 4, "ga", ("Google én AI-assistenten mogen de site lezen", "Google and AI assistants may read the site"),
               ("Laat Googlebot, GPTBot, ClaudeBot en PerplexityBot toe in robots.txt.",
                "Allow Googlebot, GPTBot, ClaudeBot and PerplexityBot in robots.txt.")),
    "ai_fetch": ("access", 3, "a", ("AI-assistenten krijgen de pagina echt te zien", "AI assistants actually get the page"),
                 ("Zorg dat de hosting AI-bots niet blokkeert (bv. Cloudflare 'Block AI bots').",
                  "Make sure hosting does not block AI bots (e.g. Cloudflare 'Block AI bots').")),
    "sitemap": ("access", 2, "g", ("Een inhoudstafel (sitemap) voor zoekmachines", "A table of contents (sitemap) for search engines"),
                ("Publiceer een sitemap.xml met alle pagina's.", "Publish a sitemap.xml listing every page.")),
    "server_text": ("access", 3, "ga", ("Tekst leesbaar zonder JavaScript", "Text readable without JavaScript"),
                    ("Zet de tekst rechtstreeks in de pagina, niet pas na laden via JavaScript.",
                     "Put the text in the page itself, not loaded later by JavaScript.")),
    "schema": ("facts", 4, "ga", ("Je praktijk staat als 'bedrijf' in de code", "Your business is described in the code"),
               ("Voeg op de homepage gestructureerde gegevens (LocalBusiness/Dentist) toe.",
                "Add structured business data (LocalBusiness/Dentist) to the homepage.")),
    "schema_fields": ("facts", 3, "ga", ("Adres, telefoon, uren, kaart en foto zitten erin", "Address, phone, hours, map and photo included"),
                      ("Vul de bedrijfsgegevens aan: openingsuren, ligging op de kaart, foto en profielen (Google Maps).",
                       "Complete the business data: opening hours, map location, photo and profiles (Google Maps).")),
    "schema_valid": ("facts", 2, "ga", ("De gegevens bevatten geen fouten", "The data has no errors"),
                     ("Herstel de gestructureerde gegevens die niet ingelezen kunnen worden.",
                      "Fix structured data that cannot be read.")),
    "nap": ("facts", 3, "ga", ("Telefoon en adres op elke pagina, overal hetzelfde", "Phone and address on every page, the same everywhere"),
            ("Toon telefoon en adres in de voettekst van elke pagina, overal in dezelfde vorm.",
             "Show phone and address in every page footer, in the same form everywhere.")),
    "contact_links": ("facts", 1, "g", ("Bellen of mailen met één tik", "Call or mail with one tap"),
                      ("Maak telefoon en e-mail klikbaar (tel:/mailto:).", "Make phone and e-mail clickable (tel:/mailto:).")),
    "faq": ("answers", 3, "a", ("Antwoorden op veelgestelde vragen", "Answers to frequently asked questions"),
            ("Zet de vragen die patiënten echt stellen met hun antwoord op een pagina.",
             "Put the questions customers really ask, with their answers, on a page.")),
    "faq_schema": ("answers", 1, "ga", ("Die vragen zijn ook voor machines gemarkeerd", "Those questions are marked up for machines"),
                   ("Markeer de bestaande vragenlijst als FAQPage.", "Mark the existing question list up as FAQPage.")),
    "depth": ("answers", 2, "a", ("Genoeg uitleg per pagina", "Enough explanation per page"),
              ("Leg per onderwerp in gewone woorden uit wat, voor wie, hoe en wat het kost.",
               "Explain each topic in plain words: what, for whom, how and what it costs.")),
    "headings": ("answers", 2, "ga", ("Tussenkoppen die zeggen wat volgt", "Subheadings that say what follows"),
                 ("Deel lange pagina's op met tussenkoppen die het onderwerp noemen.",
                  "Break long pages up with subheadings that name the topic.")),
    "place": ("answers", 2, "ga", ("De gemeente staat in titel of eerste zin", "The town appears in the title or first lines"),
              ("Noem de gemeente in de titel en de eerste zin van de homepage.",
               "Name the town in the homepage title and first sentence.")),
    "hreflang": ("languages", 3, "ga", ("Google weet welke pagina bij welke taal hoort", "Google knows which page is which language"),
                 ("Koppel elke pagina aan haar vertaling (hreflang).", "Link each page to its translation (hreflang).")),
    "speed": ("speed", 3, "g", ("Snel op een gsm", "Fast on a phone"),
              ("Maak de site lichter: kleinere foto's, minder scripts.", "Make the site lighter: smaller photos, fewer scripts.")),
}
PARTS = {
    "pages": ("Elke pagina zegt duidelijk waarover ze gaat", "Every page says clearly what it is about"),
    "access": ("Google en AI-assistenten kunnen alles lezen", "Google and AI assistants can read everything"),
    "facts": ("Google en AI-assistenten herkennen je gegevens", "Google and AI assistants recognise your details"),
    "answers": ("Antwoorden op wat mensen vragen", "Answers to what people ask"),
    "languages": ("Taalversies aan elkaar gekoppeld", "Language versions linked to each other"),
    "speed": ("Snel op een gsm", "Fast on a phone"),
}


def frac(xs) -> float:
    xs = list(xs)
    return sum(1 for x in xs if x) / len(xs) if xs else 0.0


def score_site(c: dict, assume_indexable: bool = False, city: str = "", speed: dict | None = None) -> dict:
    ok = [p for p in c["pages"] if p["status"] == 200]
    pp = [p["page"] for p in ok]
    home = pp[0] if pp else Page()
    res: dict[str, tuple[float, str]] = {}
    titles = [p.title for p in pp]
    res["title"] = (frac(15 <= len(t) <= 65 for t in titles), f"{len(titles)} pagina's")
    # unique within a language: a translated twin may share its title ("Contact · Naam")
    keyed = [(p.lang[:2], p.title) for p in pp]
    res["title_unique"] = (len(set(keyed)) / len(keyed) if keyed else 0, f"{len(set(keyed))}/{len(keyed)} uniek")
    descs = [p.meta.get("description", "").strip() for p in pp]
    per = [1.0 if 50 <= len(x) <= 170 else 0.5 if x else 0.0 for x in descs]
    uniq = len(set((p.lang[:2], x) for p, x in zip(pp, descs) if x)) / len(descs) if descs else 0
    res["description"] = (sum(per) / len(per) * uniq if per else 0.0, f"{len(set(descs))}/{len(descs)} verschillend")
    res["h1"] = (frac(p.h1 == 1 for p in pp), "")
    res["lang"] = (frac(bool(p.lang) for p in pp), "")
    res["canonical"] = (frac(p.canonical and urlparse(urljoin(o["url"], p.canonical)).path.rstrip("/") ==
                             urlparse(o["url"]).path.rstrip("/") for o, p in zip(ok, pp)), "")
    res["share"] = (frac(p.meta.get("og:title") and p.meta.get("og:image") for p in pp), "")
    imgs = [i for p in pp for i in p.imgs]
    res["alt"] = (frac("alt" in i for i in imgs) if imgs else 1.0, f"{len(imgs)} foto's")
    res["status"] = (len(ok) / len(c["pages"]) if c["pages"] else 0, f"{len(ok)}/{len(c['pages'])}")
    res["https"] = (1.0 if c["base"].startswith("https://") else 0.0, "")
    def blocks(v: str) -> bool:
        return bool(re.search(r"\b(noindex|none)\b", v.lower()))
    noindex = [blocks(p["page"].meta.get("robots", "")) or blocks(p["page"].meta.get("googlebot", ""))
               or blocks(p["x_robots"]) for p in ok]
    res["indexable"] = (1.0, "voorbeeldsite: wordt aangezet bij livegang") if assume_indexable else (
        1 - frac(noindex) if ok else 0.0, f"{sum(noindex)} pagina's met noindex")
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(c["robots"].splitlines())
    paths = [urlparse(p["url"]).path or "/" for p in ok][:10]
    allowed = {a: frac(rp.can_fetch(a, c["base"] + pth) for pth in paths) for a in ROBOTS_AGENTS}
    blocked = [a for a, v in allowed.items() if v < 1]
    if assume_indexable and all(v == 0 for v in allowed.values()):
        res["robots"] = (1.0, "voorbeeldsite: robots.txt gaat open bij livegang")
    else:
        res["robots"] = (sum(allowed.values()) / len(allowed), "geblokkeerd: " + ", ".join(blocked) if blocked else "")
    res["ai_fetch"] = (frac(s == 200 for s in c["bots"].values()), ", ".join(f"{k} {v}" for k, v in c["bots"].items()))
    res["sitemap"] = (1.0 if c["sitemap_ok"] else 0.0, "")
    res["server_text"] = (frac(len(p.words) >= 80 for p in pp), "")
    objs, bad = [], 0
    for p in pp:
        o, b = ld_objects(p)
        objs += o
        bad += b
    biz = [o for o in ld_objects(home)[0] if types(o) & BUSINESS_TYPES]
    res["schema"] = (1.0 if biz else 0.0, ", ".join(sorted(types(biz[0]))) if biz else "")
    fields = set().union(*(o.keys() for o in biz)) if biz else set()
    if "openingHours" in fields:
        fields.add("openingHoursSpecification")
    if "hasMap" in fields:
        fields.add("geo")
    res["schema_fields"] = (len(fields & set(BUSINESS_FIELDS)) / len(BUSINESS_FIELDS),
                            "ontbreekt: " + ", ".join(f for f in BUSINESS_FIELDS if f not in fields) if biz else "")
    n_ld = sum(len(p.ld) for p in pp)
    res["schema_valid"] = ((n_ld - bad) / n_ld if n_ld else 0.0, f"{n_ld} blokken, {bad} fout")
    phone = next((str(o.get("telephone")) for o in biz if o.get("telephone")), "") or next(
        (lnk[4:] for p in pp for lnk in p.links if lnk.startswith("tel:")), "")
    if not phone:  # no schema, no tel: link: the most frequent phone-like number in the site's text
        found = re.findall(r"(?:\+\d{2}[\s.]?|\b0)\d{1,3}(?:[\s./-]?\d{2,3}){3}\b", " ".join(t for p in pp for t in p.text))
        phone = max(set(found), key=found.count) if found else ""
    digits = re.sub(r"\D", "", phone)[-8:]
    res["nap"] = (frac(digits and digits in re.sub(r"\D", "", " ".join(p.text)) for p in pp) if digits else 0.0,
                  f"telefoon …{digits}" if digits else "geen telefoonnummer gevonden")
    res["contact_links"] = ((any(lnk.startswith("tel:") for lnk in home.links) +
                             any(lnk.startswith("mailto:") for p in pp for lnk in p.links)) / 2, "")
    has_faq = any(p.summaries >= 3 or p.accordions >= 3 or sum(h.endswith("?") for h in p.headings) >= 3 for p in pp)
    res["faq"] = (1.0 if has_faq else 0.0, "")
    res["faq_schema"] = (1.0 if any("FAQPage" in types(o) for o in objs) else 0.0, "")
    res["depth"] = (frac(len(p.words) >= 200 for p in pp), f"gem. {sum(len(p.words) for p in pp) // max(len(pp), 1)} woorden")
    res["headings"] = (frac(len(p.headings) - p.h1 >= 2 for p in pp), "")
    city = city or next((str(o.get("address", {}).get("addressLocality", "")) for o in biz
                         if isinstance(o.get("address"), dict)), "")
    first = (home.title + " " + " ".join(home.headings[:1]) + " " + " ".join(home.words[:120])).lower()
    res["place"] = (1.0 if city and city.lower() in first else 0.0, city)
    multi = any(len(p.hreflang) >= 2 for p in pp) or len({p.lang[:2] for p in pp if p.lang}) > 1 or any(
        "/en" in urlparse(p["url"]).path for p in ok)
    if multi:
        linked = sum(1 for p in pp if len(p.hreflang) >= 2)
        res["hreflang"] = (linked / len(pp) if pp else 0.0, f"{linked}/{len(pp)}")
    if speed:
        res["speed"] = (speed["score"], speed["detail"])
    return {"url": c["base"], "pages": len(c["pages"]), "checks": {k: {"score": round(v[0], 3), "detail": v[1]}
                                                                    for k, v in res.items()},
            "speed": speed, "assume_indexable": assume_indexable, "date": date.today().isoformat()}


def totals(s: dict) -> dict:
    def avg(keys):
        ws = [(CHECKS[k][1], s["checks"][k]["score"]) for k in keys]
        return round(100 * sum(w * v for w, v in ws) / sum(w for w, _ in ws)) if ws else None
    keys = list(s["checks"])
    parts = {pt: avg([k for k in keys if CHECKS[k][0] == pt]) for pt in PARTS}
    google, ai = avg([k for k in keys if "g" in CHECKS[k][2]]), avg([k for k in keys if "a" in CHECKS[k][2]])
    # headline = the mean of the two channels a reader sees next to it, never outside their range
    return {"overall": round((google + ai) / 2), "google": google, "ai": ai,
            "parts": {k: v for k, v in parts.items() if v is not None}}


def lighthouse(url: str, runs: int) -> dict | None:
    """Median mobile Lighthouse performance over `runs` runs (local Chrome, simulated 4G throttling)."""
    got = []
    for _ in range(runs):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "lh.json"
            cmd = ["pnpm", "dlx", "lighthouse@12.8.2", url, "--quiet", "--only-categories=performance",
                   "--output=json", f"--output-path={out}", "--chrome-flags=--headless=new --no-sandbox"]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
                lh = json.loads(out.read_text())
                got.append((float(lh["categories"]["performance"]["score"]),
                            lh["audits"]["largest-contentful-paint"]["numericValue"] / 1000,
                            lh["audits"]["total-byte-weight"]["numericValue"] / 1e6))
            except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
                sys.stderr.write(f"lighthouse failed for {url}: {exc} {locals().get('r') and r.stderr[-200:]}\n")
                return None
    got.sort()
    perf, lcp, mb = got[len(got) // 2]
    return {"score": perf, "lcp_s": round(lcp, 1), "mb": round(mb, 2), "source": "lighthouse",
            "detail": f"Lighthouse mobiel {round(perf * 100)}, grootste beeld na {lcp:.1f}s, {mb:.1f} MB"}


def weight_speed(c: dict) -> dict:
    """Fallback without Chrome: homepage weight (HTML + images/CSS/JS it references) and server response time."""
    home = c["pages"][0]
    if home["status"] != 200:  # an unreachable homepage is not a fast one
        return {"score": 0.0, "mb": None, "ttfb_s": None, "source": "weight", "detail": "homepage niet bereikbaar"}
    p = home["page"]
    refs = [urljoin(home["url"], i.get("src", "")) for i in p.imgs if i.get("src") and not i["src"].startswith("data:")]
    refs += re.findall(r'(?:href|src)=["\']([^"\']+\.(?:css|js)(?:\?[^"\']*)?)', c["home"]["body"])
    refs = [urljoin(home["url"], r) for r in refs][:40]
    with ThreadPoolExecutor(8) as ex:
        sizes = list(ex.map(lambda u: fetch(u)["bytes"], refs))
    mb = (home["bytes"] + sum(sizes)) / 1e6
    score = max(0.0, min(1.0, 1 - (mb - 1) / 4)) * 0.7 + max(0.0, min(1.0, 1 - (home["ttfb"] - 0.2) / 1.3)) * 0.3
    return {"score": round(score, 2), "mb": round(mb, 2), "ttfb_s": round(home["ttfb"], 2), "source": "weight",
            "detail": f"{mb:.1f} MB, server antwoordt na {home['ttfb']:.2f}s"}


def run_score(url: str, assume_indexable: bool, use_lh: bool, runs: int, city: str) -> dict:
    return finish(crawl(url), assume_indexable, use_lh, runs, city)


def finish(c: dict, assume_indexable: bool, use_lh: bool, runs: int, city: str) -> dict:
    speed = (lighthouse(c["base"] + "/", runs) if use_lh else None) or weight_speed(c)
    s = score_site(c, assume_indexable, city, speed)
    s["totals"] = totals(s)
    return s


# --- report ---------------------------------------------------------------------------------------------------------

MONTHS = {"nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
                 "november", "december"],
          "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December"]}

T = {
    "nl": {"title": "Je nieuwe website is klaar om veel beter gevonden te worden",
           "title_up": "Je nieuwe website wordt beter gevonden", "title_flat": "Hoe goed word je gevonden?",
           "sub": "In Google én in AI-assistenten zoals ChatGPT, Perplexity en Google AI.",
           "old": "Huidige website", "new": "Nieuwe website", "now": "nu", "new_short": "nieuw", "live": "bij livegang",
           "google": "Google", "ai": "AI-assistenten", "overall": "Vindbaarheidsscore", "speed": "Laadtijd op gsm",
           "faster": "{x}× sneller", "where": "Waar het verschil zit", "ok": "Al in orde",
           "today": "Vandaag, met je huidige website", "measured": "Gemeten op {date}.", "term": "Zoekterm",
           "web": "Google", "maps": "Google Maps", "out": "> 20", "out_legend": "> 20 = niet bij de eerste 20 resultaten",
           "ai_today": "Wat AI-assistenten vandaag antwoorden", "mentioned": "noemt je", "not_mentioned": "noemt je niet",
           "ai_sum": "Genoemd in {n} van de {m} antwoorden.", "ideas": "Dit kan je nog verbeteren",
           "how": "Hoe we meten", "honest": "Eerlijke verwachting", "preview": "Voorbeeldversie",
           "method": "Score op 100 uit {n} automatische controles van wat Google en AI-assistenten op elke pagina lezen. "
                     "Geen inschatting: dezelfde site geeft dezelfde score.",
           "promise": "Een hogere score maakt goed gevonden worden waarschijnlijker; een plaats in Google of een "
                      "vermelding in een AI-antwoord kan niemand beloven.",
           "prelaunch": "De nieuwe website houdt zoekmachines nog bewust buiten. Die ene instelling gaat aan bij de "
                        "verhuis naar je eigen domein; de score toont de site vanaf dat moment.",
           "lang_note": "{k} van de {n} pagina's zijn al aan hun vertaling gekoppeld."},
    "en": {"title": "Your new website is ready to be found much better",
           "title_up": "Your new website will be found better", "title_flat": "How well will you be found?",
           "sub": "In Google and in AI assistants such as ChatGPT, Perplexity and Google AI.",
           "old": "Current website", "new": "New website", "now": "now", "new_short": "new", "live": "at go-live",
           "google": "Google", "ai": "AI assistants", "overall": "Findability score", "speed": "Load time on a phone",
           "faster": "{x}× faster", "where": "Where the difference is", "ok": "Already fine",
           "today": "Today, with your current website", "measured": "Measured on {date}.", "term": "Search term",
           "web": "Google", "maps": "Google Maps", "out": "> 20", "out_legend": "> 20 = not in the first 20 results",
           "ai_today": "What AI assistants answer today", "mentioned": "mentions you",
           "not_mentioned": "does not mention you", "ai_sum": "Mentioned in {n} of {m} answers.",
           "ideas": "What you can still improve", "how": "How we measure", "honest": "Honest expectation",
           "preview": "Preview version",
           "method": "Score out of 100 from {n} automatic checks of what Google and AI assistants read on every page. "
                     "No guesswork: the same site gives the same score.",
           "promise": "A higher score makes being found more likely; nobody can promise a Google position or a "
                      "mention in an AI answer.",
           "prelaunch": "The new website still keeps search engines out on purpose. That one setting is switched on "
                        "when it moves to your own domain; the score shows the site from that moment.",
           "lang_note": "{k} of {n} pages are already linked to their translation."},
}
L = {"nl": 0, "en": 1}
# One plain sentence per part (the part titles live in PARTS).
PART_WHY = {
    "pages": ("Elke pagina heeft een eigen titel en een korte samenvatting die Google in de zoekresultaten toont.",
              "Every page has its own title and a short summary that Google shows in its results."),
    "access": ("Google en AI-assistenten mogen elke pagina lezen en krijgen de tekst meteen te zien.",
               "Google and AI assistants may read every page and get the text straight away."),
    "facts": ("Naam, adres, telefoon, ligging en team staan zo in de code dat machines ze zeker juist overnemen.",
              "Name, address, phone, location and team are in the code so machines copy them correctly."),
    "answers": ("De vragen die mensen stellen staan met hun antwoord op de site, met duidelijke tussenkoppen.",
                "The questions people ask are answered on the site, under clear headings."),
    "languages": ("Google weet welke Engelse pagina bij welke Nederlandse hoort.",
                  "Google knows which English page belongs to which Dutch one."),
}

CSS = """
:root{color-scheme:light;--ink:#14212b;--muted:#4f5d6a;--line:#e3e8ed;--old:#9aa7b2;--new:#0f7b5f;--new-soft:#e3f4ee;
--warn:#b42318;--warn-soft:#fdecea;--card:#f6f8fa;--amber:#8a5500;--amber-soft:#fff4e0}
*{box-sizing:border-box}html{background:#fff}body{margin:0;background:#fff;color:var(--ink);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
main{max-width:920px;margin:0 auto;padding:40px 24px 56px}
.eyebrow{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
h1{font-size:34px;line-height:1.15;margin:0 0 8px;letter-spacing:-.01em}h2{font-size:21px;margin:44px 0 6px}
.sub{color:var(--muted);margin:0 0 24px;font-size:17px}.cap{color:var(--muted);font-size:14px;margin:0 0 12px}
.channels{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.ch{border:1px solid var(--line);border-radius:18px;padding:20px 22px}
.ch .k{font-weight:700;font-size:17px}
.ch .nums{display:flex;align-items:baseline;gap:10px;margin:6px 0 12px;flex-wrap:wrap}
.ch .o{font-size:26px;font-weight:700;color:var(--old)}.ch .n{font-size:52px;line-height:1;font-weight:800;color:var(--new)}
.ch .of{color:var(--muted);font-size:15px}.ch .ar{color:var(--new);font-size:24px;font-weight:700}
.pair{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;align-items:center;font-size:13px;color:var(--muted)}
.bar{position:relative;height:10px;border-radius:6px;background:#eef1f4}
.bar i{position:absolute;left:0;top:0;bottom:0;border-radius:6px}.bar.o i{background:var(--old)}.bar.n i{background:var(--new)}
.strip{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:center;background:var(--card);border-radius:14px;
padding:12px 18px;margin-top:12px;font-size:15px}
.strip b{font-size:17px}.strip .old{color:var(--muted);font-weight:600}
.pill{display:inline-block;text-align:center;border-radius:999px;padding:2px 10px;font-weight:700;font-size:14px;white-space:nowrap}
.top3{background:var(--new-soft);color:var(--new)}.mid{background:var(--amber-soft);color:var(--amber)}
.no{background:#f1f3f5;color:var(--muted)}.bad{background:var(--warn-soft);color:var(--warn)}
.part{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:18px;align-items:center;padding:14px 0;
border-top:1px solid var(--line)}
.part:first-child{border-top:0}.part .name{font-weight:650;font-size:17px}.part .why{font-size:14px;color:var(--muted)}
.part .note2{font-size:13px;color:var(--amber);margin-top:3px}
.bars{display:grid;grid-template-columns:auto 1fr 30px;gap:4px 8px;align-items:center;font-size:13px;color:var(--muted)}
.bars .num{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}
.gain{grid-column:1/-1;justify-self:end}
table{width:100%;border-collapse:collapse;font-size:15px}th,td{text-align:left;padding:9px 8px;border-top:1px solid var(--line)}
th{font-size:13px;color:var(--muted);font-weight:600;border-top:0}td.r,th.r{text-align:right}
.scroll{overflow-x:auto}.legend{font-size:13px;color:var(--muted);margin:8px 0 0}
.lang{font-size:11px;font-weight:700;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 4px;margin-left:4px}
.ai{display:grid;gap:8px}.ai>div{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:11px 14px;
background:var(--card);border-radius:12px;font-size:15px}
.engines{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.ideas{counter-reset:i;list-style:none;padding:0;margin:10px 0 0;display:grid;gap:10px}
.ideas li{counter-increment:i;background:var(--card);border-radius:14px;padding:14px 16px 14px 56px;position:relative}
.ideas li:before{content:counter(i);position:absolute;left:16px;top:13px;width:28px;height:28px;border-radius:50%;
background:var(--new);color:#fff;font-weight:700;display:grid;place-items:center;font-size:15px}
.ideas b{display:block}.ideas span{font-size:14px;color:var(--muted)}
.notes{margin-top:44px;border-top:1px solid var(--line);padding-top:14px;display:grid;gap:6px;font-size:14px;color:var(--muted)}
.callout{background:#fffbeb;border:1px solid #fcd34d;border-radius:10px;padding:10px 14px;font-size:14px;margin:0 0 18px}
.minis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.mini{background:var(--card);border-radius:14px;padding:14px 16px}.mini .k{font-size:13px;color:var(--muted)}
.mini .v{font-size:24px;font-weight:800;color:var(--new)}.mini .s{font-size:13px;color:var(--muted)}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.chart{border:1px solid var(--line);border-radius:14px;padding:12px 14px}.chart .k{font-weight:700;font-size:15px}
.chart svg{display:block;width:100%;height:auto}
@media (max-width:640px){main{padding:28px 16px 44px}h1{font-size:26px}.channels,.charts{grid-template-columns:1fr 1fr;gap:10px}
.ch{padding:14px}.ch .n{font-size:38px}.ch .o{font-size:20px}.part{grid-template-columns:1fr;gap:8px}
.ai>div{flex-direction:column;align-items:flex-start;gap:6px}.charts{grid-template-columns:1fr}.engines{justify-content:flex-start}
.minis{grid-template-columns:1fr}.mid-month{display:none}}
@media (max-width:380px){.channels,.charts{grid-template-columns:1fr}}
@media print{main{padding:0}}
"""


def num(x: float, lang: str) -> str:
    s = f"{x:.1f}"
    return s.replace(".", ",") if lang == "nl" else s


def long_date(iso: str, lang: str) -> str:
    y, m, d = (int(p) for p in iso.split("-"))
    return f"{d} {MONTHS[lang][m - 1]} {y}" if lang == "nl" else f"{MONTHS[lang][m - 1]} {d}, {y}"


def pick_ideas(new: dict, lang: str, extra: list[dict], limit: int = 4) -> list[tuple[str, str]]:
    """Practice-specific ideas first (from --ideas), then the heaviest checks the new site still misses."""
    out = [(i["title"], i.get("why", "")) for i in extra if i.get("lang", lang) == lang]
    misses = sorted(((CHECKS[k][1] * (1 - v["score"]), k) for k, v in new["checks"].items() if v["score"] < 0.9),
                    reverse=True)
    for _, k in misses:
        out.append((CHECKS[k][4][L[lang]], ""))
    return out[:limit]


def bar_pair(old_v: int, new_v: int, t: dict, nums: bool = False) -> str:
    """Two labelled bars (current grey, new green); with `nums` a value column (grid of 3)."""
    def row(label, cls, v):
        return (f'<span>{label}</span><div class="bar {cls}"><i style="width:{v}%"></i></div>'
                + (f'<span class="num">{v}</span>' if nums else ""))
    return row(t["now"], "o", old_v) + row(t["new_short"], "n", new_v)


def render_compare(old: dict, new: dict, lang: str, name: str, rankings: dict | None, ai: list | None,
                   ideas: list[dict]) -> str:
    t, i, e = T[lang], L[lang], html.escape

    def ints(tt: dict) -> dict:  # scores may come from a reused JSON file: numbers only into the HTML
        return {"overall": int(tt["overall"]), "google": int(tt["google"]), "ai": int(tt["ai"]),
                "parts": {k: int(v) for k, v in tt["parts"].items()}}
    to, tn = ints(old["totals"]), ints(new["totals"])
    gain = tn["overall"] - to["overall"]
    title = t["title"] if gain >= 10 else t["title_up"] if gain > 0 else t["title_flat"]
    live = f' <span class="of">{t["live"]}</span>' if new.get("assume_indexable") else ""

    def channel(key: str) -> str:
        return (f'<div class="ch"><div class="k">{t[key]}</div><div class="nums"><span class="o">{to[key]}</span>'
                f'<span class="ar">→</span><span class="n">{tn[key]}</span><span class="of">/100</span>{live}</div>'
                f'<div class="pair">{bar_pair(to[key], tn[key], t)}</div></div>')
    so, sn = old.get("speed") or {}, new.get("speed") or {}
    speed = ""
    if so.get("lcp_s") and sn.get("lcp_s"):
        so, sn = {"lcp_s": float(so["lcp_s"])}, {"lcp_s": float(sn["lcp_s"])}
        x = so["lcp_s"] / sn["lcp_s"]
        fast = f' <span class="pill top3">{t["faster"].format(x=round(x))}</span>' if x >= 1.5 else ""
        speed = (f'<span>{t["speed"]}: <span class="old">{num(so["lcp_s"], lang)} s</span> → '
                 f'<b>{num(sn["lcp_s"], lang)} s</b>{fast}</span>')
    strip = (f'<div class="strip"><span>{t["overall"]}: <span class="old">{to["overall"]}</span> → '
             f'<b>{tn["overall"]}</b>/100</span>{speed}</div>')

    rows = []
    for pt, label in PARTS.items():
        if pt not in tn["parts"] or pt == "speed":
            continue
        ov, nv = to["parts"].get(pt, 0), tn["parts"][pt]
        note = ""
        if nv < ov and pt == "languages" and "hreflang" in new["checks"]:
            k, n = new["checks"]["hreflang"]["detail"].split("/") if "/" in new["checks"]["hreflang"]["detail"] else ("", "")
            note = f'<div class="note2">{e(t["lang_note"].format(k=k, n=n))}</div>' if k else ""
        gain = (f'<span class="pill top3 gain">+{nv - ov}</span>' if nv - ov > 0 else
                f'<span class="pill no gain">{t["ok"]}</span>' if nv >= 95 else "")
        rows.append((nv - ov, f'<div class="part"><div><div class="name">{e(label[i])}</div>'
                              f'<div class="why">{e(PART_WHY[pt][i])}</div>{note}</div>'
                              f'<div class="bars">{bar_pair(ov, nv, t, nums=True)}{gain}</div></div>'))
    parts_html = "".join(h for _, h in sorted(rows, key=lambda r: -r[0]))

    measured = t["measured"].format(date=long_date(old["date"], lang))
    rank_html = ""
    if rankings and rankings.get("rows"):
        terms: dict[tuple, dict] = {}
        for r in rankings["rows"]:
            terms.setdefault((r["term"], r.get("lang", "")), {})[r["where"]] = r.get("position")

        def pill(p):
            if not p:
                return f'<span class="pill no">{t["out"]}</span>'
            return f'<span class="pill {"top3" if int(p) <= 3 else "mid"}">#{int(p)}</span>'

        def tag(tl):  # a term searched in the other language gets a small language tag
            return f' <span class="lang">{e(tl.upper())}</span>' if tl and tl != lang else ""
        body = "".join(f'<tr><td>{e(term)}{tag(tl)}</td><td class="r">{pill(w.get("google"))}</td>'
                       f'<td class="r">{pill(w.get("maps"))}</td></tr>' for (term, tl), w in terms.items())
        rank_html = (f'<h2>{t["today"]}</h2><p class="cap">{measured}</p><div class="scroll"><table><tr>'
                     f'<th>{t["term"]}</th><th class="r">{t["web"]}</th><th class="r">{t["maps"]}</th></tr>{body}</table>'
                     f'</div><p class="legend">{t["out_legend"]}</p>')
    ai_html = ""
    if ai:
        by_q: dict[str, list] = {}
        for a in ai:
            by_q.setdefault(a["question"], []).append(a)
        body = "".join(
            f'<div><span>“{e(q)}”</span><span class="engines">' + "".join(
                f'<span class="pill {"top3" if a["mentioned"] else "bad"}">{"✓" if a["mentioned"] else "✗"} '
                f'{e(a["engine"])}</span>' for a in answers) + "</span></div>" for q, answers in by_q.items())
        hits = sum(1 for a in ai if a["mentioned"])
        ai_html = (f'<h2>{t["ai_today"]}</h2><p class="cap">{t["ai_sum"].format(n=hits, m=len(ai))} '
                   f'✓ {t["mentioned"]} · ✗ {t["not_mentioned"]}</p><div class="ai">{body}</div>')
    ideas_html = "".join(f'<li><b>{e(a)}</b>{f"<span>{e(b)}</span>" if b else ""}</li>'
                         for a, b in pick_ideas(new, lang, ideas))
    notes = [(t["how"], t["method"].format(n=len(new["checks"])) + " " + measured), (t["honest"], t["promise"])]
    if new.get("assume_indexable"):
        notes.append((t["preview"], t["prelaunch"]))
    notes_html = "".join(f"<div><b>{e(a)}.</b> {e(b)}</div>" for a, b in notes)
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(name)} · {e(title)}</title>
<style>{CSS}</style></head><body><main>
<p class="eyebrow">{e(name)}</p><h1>{e(title)}</h1><p class="sub">{e(t["sub"])}</p>
<section class="channels">{channel("google")}{channel("ai")}</section>{strip}
<h2>{t["where"]}</h2><section>{parts_html}</section>
{rank_html}{ai_html}
<h2>{t["ideas"]}</h2><ol class="ideas">{ideas_html}</ol>
<div class="notes">{notes_html}</div></main></body></html>"""


def render_monthly(h: dict, lang: str) -> str:
    """Monthly report from a history file (format in ../SKILL.md)."""
    t, e = T[lang], html.escape
    if not h.get("months"):
        raise SystemExit("history: 'months' is empty")
    months = [{**m, "google": int(m["google"]), "ai": int(m["ai"]),
               "rankings": {str(term): int(v) if v else None for term, v in m.get("rankings", {}).items()},
               "ai_mentions": [int(x) for x in m.get("ai_mentions", [0, 0])]} for m in h["months"]]
    last, first = months[-1], months[0]
    terms = list(dict.fromkeys(term for m in months for term in m["rankings"]))  # every term ever tracked
    k = {"nl": ("Maandrapport", "Je vindbaarheid deze maand", "Vermeld door AI-assistenten", "antwoorden",
                "Je plaats in Google per zoekterm", "sinds", "Wat we deze maand deden", "Volgende maand",
                "Voorbeeld met fictieve cijfers", "nieuw in top 20", "– = niet bij de eerste 20 resultaten",
                "Nieuwe website live"),
         "en": ("Monthly report", "Your findability this month", "Mentioned by AI assistants", "answers",
                "Your Google position per search term", "since", "What we did this month", "Next month",
                "Example with fictional figures", "new in top 20", "– = not in the first 20 results",
                "New website live")}[lang]
    W, H, P, LP = 300, 180, 24, 34  # LP: left padding for the 0/50/100 scale

    def chart(key: str, color: str, dash: str = "") -> str:
        xs = [LP + (W - LP - P) * j / max(len(months) - 1, 1) for j in range(len(months))]
        y = lambda v: H - 2 * P - (H - 3 * P) * v / 100  # noqa: E731 - bottom 2*P holds the month labels
        grid = "".join(f'<line x1="{LP}" x2="{W - P}" y1="{y(g):.0f}" y2="{y(g):.0f}" stroke="#eef1f4"/>'
                       f'<text x="{LP - 8}" y="{y(g) + 4:.0f}" font-size="10" text-anchor="end" fill="#8a96a3">{g}</text>'
                       for g in (0, 50, 100))
        launch = ""
        if h.get("launch_after") is not None and 0 <= int(h["launch_after"]) < len(months) - 1:
            j = int(h["launch_after"])
            lx = (xs[j] + xs[j + 1]) / 2
            launch = (f'<line x1="{lx:.0f}" x2="{lx:.0f}" y1="{P - 6}" y2="{y(0):.0f}" stroke="#0f7b5f" stroke-dasharray="3 3"/>'
                      f'<text x="{lx + 4:.0f}" y="{y(0) - 6:.0f}" font-size="10" fill="#0f7b5f">{e(k[11])}</text>')
        pts = " ".join(f"{x:.0f},{y(m[key]):.0f}" for x, m in zip(xs, months))
        dots = "".join(f'<circle cx="{x:.0f}" cy="{y(m[key]):.0f}" r="4" fill="{color}"/>'
                       f'<text x="{x:.0f}" y="{y(m[key]) - 9:.0f}" font-size="12" font-weight="700" text-anchor="middle" '
                       f'fill="#14212b">{m[key]}</text>' for x, m in zip(xs, months))
        labels = "".join(f'<text x="{x:.0f}" y="{H - 8}" font-size="13" text-anchor="middle" fill="#4f5d6a">{e(m["label"])}</text>'
                         for x, m in zip(xs, months))
        return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{e(t[key])}">{grid}{launch}{labels}'
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3" stroke-dasharray="{dash}"/>'
                f'{dots}</svg>')
    charts = "".join(f'<div class="chart"><div class="k">{t[key]}</div>{chart(key, col)}</div>'
                     for key, col in (("google", "#2f6fb0"), ("ai", "#0f7b5f")))
    mid = range(1, len(months) - 1)

    def cell(p, j):
        cls = ' class="r mid-month"' if j in mid else ' class="r"'
        inner = '<span class="pill no">–</span>' if not p else f'<span class="pill {"top3" if p <= 3 else "mid"}">#{p}</span>'
        return f"<td{cls}>{inner}</td>"

    def move(term):
        a, b = first["rankings"].get(term), last["rankings"].get(term)
        if b and not a:
            return f'<span class="pill top3">{k[9]}</span>'
        if a and not b:
            return f'<span class="pill bad">{"uit top 20" if lang == "nl" else "out of top 20"}</span>'
        if a and b and b < a:
            return f'<span class="pill top3">▲ {a - b}</span>'
        if a and b and b > a:
            return f'<span class="pill bad">▼ {b - a}</span>'
        return '<span class="pill no">=</span>'
    head = "".join(f'<th class="r{" mid-month" if j in mid else ""}">{e(m["label"])}</th>' for j, m in enumerate(months))
    rows = "".join(f'<tr><td>{e(term)}</td><td class="r">{move(term)}</td>'
                   f'{"".join(cell(m["rankings"].get(term), j) for j, m in enumerate(months))}</tr>'
                   for term in terms)
    am = [m.get("ai_mentions", [0, 0]) for m in months]
    ai_cells = "".join(f'<span><b>{a[0]}</b>/{a[1]} <span class="s">{e(m["label"])}</span></span>'
                       for a, m in zip(am, months))
    wins = "".join(f"<li><b>{e(x)}</b></li>" for x in last.get("done", []))
    nexts = "".join(f"<li><b>{e(x)}</b></li>" for x in last.get("next", []))
    callout = f'<div class="callout"><b>{k[8]}.</b> {e(h.get("note", ""))}</div>' if h.get("sample") else ""
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(h["name"])} · {k[0]}</title>
<style>{CSS}</style></head><body><main>
<p class="eyebrow">{e(h["name"])} · {k[0]} {e(last["label"])}</p><h1>{k[1]}</h1>{callout}
<div class="minis"><div class="mini"><div class="k">{t["google"]}</div><div class="v">{last["google"]}<span class="s">/100</span></div>
<div class="s">{e(first["label"])} {first["google"]} → {e(last["label"])} {last["google"]}</div></div>
<div class="mini"><div class="k">{t["ai"]}</div><div class="v">{last["ai"]}<span class="s">/100</span></div>
<div class="s">{e(first["label"])} {first["ai"]} → {e(last["label"])} {last["ai"]}</div></div>
<div class="mini"><div class="k">{k[2]}</div><div class="v">{am[-1][0]}<span class="s"> / {am[-1][1]} {k[3]}</span></div>
<div class="s" style="display:flex;gap:10px;flex-wrap:wrap">{ai_cells}</div></div></div>
<section class="charts">{charts}</section>
<h2>{k[4]}</h2><div class="scroll"><table><tr><th>{t["term"]}</th><th class="r">{k[5]} {e(first["label"])}</th>{head}</tr>{rows}</table></div>
<p class="legend">{k[10]}</p>
<h2>{k[6]}</h2><ol class="ideas">{wins}</ol><h2>{k[7]}</h2><ol class="ideas">{nexts}</ol>
{"" if h.get("sample") else f'<div class="notes">{e(h.get("note", ""))}</div>'}</main></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("compare", "score"):
        p = sub.add_parser(name)
        p.add_argument("urls", nargs=2 if name == "compare" else 1)
        p.add_argument("--lighthouse", action="store_true", help="mobile speed via pnpm dlx lighthouse + local Chrome")
        p.add_argument("--runs", type=int, default=3, choices=range(1, 8), metavar="1-7",
                       help="Lighthouse runs per site (median)")
        p.add_argument("--city", default="", help="town to look for in title/first lines (default: from schema)")
        p.add_argument("--json", help="write the raw scores here")
        if name == "compare":
            p.add_argument("--lang", choices=["nl", "en"], default="nl")
            p.add_argument("--name", required=True)
            p.add_argument("--out", required=True)
            p.add_argument("--assume-indexable", choices=["old", "new", "both"], help="treat a preview's noindex as off")
            p.add_argument("--rankings", help='{"rows":[{"term","where":"google|maps","position"}]}')
            p.add_argument("--ai-answers", help='[{"question","engine","mentioned":bool}]')
            p.add_argument("--ideas", help='[{"title","why","lang"}] practice-specific ideas, shown first')
            p.add_argument("--reuse", action="store_true", help="reuse --json scores instead of re-crawling")
        else:
            p.add_argument("--assume-indexable", action="store_true")
    m = sub.add_parser("monthly")
    m.add_argument("history")
    m.add_argument("--lang", choices=["nl", "en"], default="nl")
    m.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.cmd == "monthly":
        Path(a.out).write_text(render_monthly(json.loads(Path(a.history).read_text()), a.lang))
        print(a.out)
        return
    if a.cmd == "score":
        s = run_score(a.urls[0], a.assume_indexable, a.lighthouse, a.runs, a.city)
        out = json.dumps(s, indent=1, ensure_ascii=False)
        Path(a.json).write_text(out) if a.json else print(out)
        return
    if a.reuse and a.json and Path(a.json).exists():
        old, new = json.loads(Path(a.json).read_text())
    else:
        ai_flag = a.assume_indexable or ""
        c_new, c_old = crawl(a.urls[1]), crawl(a.urls[0])
        new = finish(c_new, ai_flag in ("new", "both"), a.lighthouse, a.runs, a.city)
        city = a.city or new["checks"]["place"]["detail"]  # same town for both sites
        old = finish(c_old, ai_flag in ("old", "both"), a.lighthouse, a.runs, city)
        if old["speed"]["source"] != new["speed"]["source"]:  # Lighthouse failed for one: same method for both
            sys.stderr.write("speed: Lighthouse missing for one site, both measured by page weight\n")
            new = finish(c_new, ai_flag in ("new", "both"), False, 1, a.city)
            old = finish(c_old, ai_flag in ("old", "both"), False, 1, city)
        if a.json:
            Path(a.json).write_text(json.dumps([old, new], indent=1, ensure_ascii=False))
    load = lambda f: json.loads(Path(f).read_text()) if f else None  # noqa: E731
    page = render_compare(old, new, a.lang, a.name, load(a.rankings), load(a.ai_answers), load(a.ideas) or [])
    Path(a.out).write_text(page)
    for label, s in (("old", old), ("new", new)):
        tt = s["totals"]
        print(f"{label}: overall {tt['overall']} · google {tt['google']} · ai {tt['ai']} · parts {tt['parts']}")
    print(a.out)


if __name__ == "__main__":
    main()
