"""Offline checks of the scorer and both renderers: python3 -m unittest discover -s skills/findability-score/scripts"""

import json
import re
import unittest

import score_site as s

GOOD = """<!doctype html><html lang="nl"><head><title>Orthodontist in Teststad · Praktijk X</title>
<meta name="description" content="Praktijk X in Teststad: orthodontisch advies en beugels voor kinderen en volwassenen.">
<link rel="canonical" href="https://x.example/"><meta property="og:title" content="X"><meta property="og:image" content="/a.jpg">
<link rel="alternate" hreflang="nl" href="/"><link rel="alternate" hreflang="en" href="/en">
<script type="application/ld+json">{"@type":"Dentist","name":"X","telephone":"+3216000000","url":"https://x.example",
"address":{"addressLocality":"Teststad"},"image":"/a.jpg","hasMap":"https://maps","sameAs":["https://g"]}</script>
<script type="application/ld+json">{"@type":"FAQPage","mainEntity":[]}</script></head><body><h1>Praktijk X</h1>
<p>Orthodontie in Teststad. Bel 016 00 00 00.</p><h2>Wat we doen</h2><h2>Waar</h2>
<details><summary>Vraag 1?</summary>a</details><details><summary>Vraag 2?</summary>b</details>
<details><summary>Vraag 3?</summary>c</details><a href="tel:+3216000000">bel</a><a href="mailto:a@x">mail</a>
<img src="/a.jpg" alt="Wachtzaal">""" + "woord " * 250 + "</body></html>"
BAD = """<html><head><title>Home</title><meta name="robots" content="noindex"></head><body><img src="/a.jpg">
<div id="app"></div></body></html>"""


def crawl_of(body: str, robots: str = "") -> dict:
    page = {"url": "https://x.example/", "status": 200, "page": s.parse(body), "x_robots": "", "bytes": 1000, "ttfb": 0.1}
    return {"base": "https://x.example", "home": {"body": body}, "robots": robots, "sitemap_ok": True,
            "pages": [page], "bots": {b: 200 for b in s.AI_FETCHERS}}


def scored(body: str, **kw) -> dict:
    res = s.score_site(crawl_of(body, kw.pop("robots", "")), **kw)
    res["totals"] = s.totals(res)
    return res


class ScoreTest(unittest.TestCase):
    def test_good_beats_bad(self):
        good, bad = scored(GOOD), scored(BAD)
        self.assertGreater(good["totals"]["overall"], 85)
        self.assertLess(bad["totals"]["overall"], 50)
        self.assertEqual(good["checks"]["faq_schema"]["score"], 1.0)
        self.assertEqual(good["checks"]["place"]["detail"], "Teststad")

    def test_headline_between_channels(self):
        for t in (scored(GOOD)["totals"], scored(BAD)["totals"]):
            self.assertLessEqual(min(t["google"], t["ai"]), t["overall"])
            self.assertLessEqual(t["overall"], max(t["google"], t["ai"]))

    def test_preview_noindex_neutralised_only_when_asked(self):
        preview = GOOD.replace("<head>", '<head><meta name="robots" content="noindex">')
        disallow = "User-agent: *\nDisallow: /"
        self.assertEqual(scored(preview, robots=disallow)["checks"]["indexable"]["score"], 0.0)
        self.assertEqual(scored(preview, robots=disallow)["checks"]["robots"]["score"], 0.0)
        live = scored(preview, robots=disallow, assume_indexable=True)
        self.assertEqual(live["checks"]["indexable"]["score"], 1.0)
        self.assertEqual(live["checks"]["robots"]["score"], 1.0)

    def test_robots_blocking_one_ai_bot_costs_points(self):
        blocked = scored(GOOD, robots="User-agent: GPTBot\nDisallow: /")
        self.assertLess(blocked["checks"]["robots"]["score"], 1.0)
        self.assertIn("GPTBot", blocked["checks"]["robots"]["detail"])


class RobustnessTest(unittest.TestCase):
    def test_graph_once_and_odd_types(self):
        page = s.parse('<script type="application/ld+json">{"@graph":[{"@type":{"x":1}},{"@type":"Dentist",'
                       '"@graph":[{"@type":"Person"}]}]}</script>')
        objs, bad = s.ld_objects(page)
        self.assertEqual(bad, 0)
        self.assertEqual(sorted(t for o in objs for t in s.types(o)), ["Dentist", "Person"])

    def test_non_http_and_malformed_urls_do_not_raise(self):
        self.assertEqual(s.fetch("file:///etc/passwd")["status"], 0)
        self.assertEqual(s.fetch("http://[bad")["status"], 0)


class RenderTest(unittest.TestCase):
    def test_headline_follows_the_measurement(self):
        good, bad = scored(GOOD), scored(BAD)
        worse = s.render_compare(good, bad, "en", "X", None, None, [])
        self.assertIn("How well will you be found?", worse)
        self.assertIn("much better", s.render_compare(bad, good, "en", "X", None, None, []))

    def test_monthly_keeps_terms_that_drop_out(self):
        months = [{"label": "a", "google": 1, "ai": 1, "rankings": {"gone": 4}},
                  {"label": "b", "google": 2, "ai": 2, "rankings": {}}]
        page = s.render_monthly({"name": "X", "months": months, "launch_after": 5}, "en")
        self.assertIn("gone", page)


    def test_compare_and_monthly_render_plain_words(self):
        old, new = scored(BAD), scored(GOOD, assume_indexable=True)
        old["speed"] = {"lcp_s": 5.2}
        new["speed"] = {"lcp_s": 1.8}
        ranks = {"rows": [{"term": "beugel", "where": "google", "position": 3}, {"term": "beugel", "where": "maps"}]}
        ai = [{"question": "Wie?", "engine": "ChatGPT", "mentioned": True}]
        months = [{"label": m, "google": g, "ai": g, "rankings": {"beugel": p}, "ai_mentions": [1, 2]}
                  for m, g, p in (("nov", 60, None), ("dec", 90, 5))]
        for lang in ("nl", "en"):
            page = s.render_compare(old, new, lang, "X", ranks, ai, [])
            visible = re.sub(r"<style>.*?</style>|<[^>]+>", " ", page, flags=re.S)
            for jargon in ("SEO", "GEO", "schema", "hreflang", "JSON-LD"):
                self.assertNotIn(jargon, visible)
            self.assertIn("5,2 s" if lang == "nl" else "5.2 s", visible)
            monthly = s.render_monthly(json.loads(json.dumps({"name": "X", "sample": True, "months": months,
                                                              "launch_after": 0})), lang)
            self.assertIn("<svg", monthly)


if __name__ == "__main__":
    unittest.main()
