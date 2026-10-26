---
name: website-dev
description: >-
  Coding-agent workflow for a public website repo that ReplyPen chat also edits (Eleventy or Jekyll,
  Cloudflare Workers static assets + Workers Builds, root AGENTS.md with the site map). Use for ANY
  change in such a repo: run it locally, build, look at the changed pages on phone and desktop width,
  check links/images, push a branch preview, wait for the deploy check. Not for provisioning a new site.
---

# website-dev

**The site's root `AGENTS.md` comes first**: where things live, recipes, URL style, form contract and
site exceptions (other build steps, a separate production config). Where it differs from this file,
it wins. ReplyPen's chat agent reads only that `AGENTS.md`; it cannot build, you can and must.

> [!IMPORTANT]
> **`main` is the live website.** Never commit a visitor-visible change on `main` or push it there,
> whatever a global "push to main / no feature branches" habit says: branch → pull request → preview
> → the site owner's OK on that preview → merge. Only tooling with a byte-identical `_site` (step 8)
> may go straight to `main`.

## The loop

1. **Fresh start:** `git pull --no-rebase`, then a branch: `git switch -c <name>`. The name becomes the
   preview hostname, so lowercase letters, digits and dashes only, short (`openingsuren-zomer`).
2. **Tools:** Node comes from `mise.toml` (`mise install`). No `pnpm` on PATH? Prefix every command with
   `mise exec pnpm@10 --` (e.g. `mise exec pnpm@10 -- bash build.sh`). Then `pnpm install`.
3. **Edit** the smallest change that does the ask.
4. **Build = the CI gate:** `bash build.sh`, the exact command Workers Builds runs (site tests and
   contract checks run inside it). It must pass before you push.
5. **Serve like Cloudflare:** `pnpm dlx wrangler@4 dev --port 8787` serves `_site` with the real
   redirects, headers (CSP) and trailing-slash handling (use the `--config` AGENTS.md names, if any).
   It serves the last build: rebuild after every edit. `pnpm serve` (live reload, :8080) is for quick
   looks only; its URL handling differs.
6. **Look at it:** open every changed page in a browser at 390 px and 1280 px wide (screenshot when
   your harness can) and compare with the ask: text right, layout intact, nothing else moved.
   A `_data/` or `_includes/` edit shows on many pages: look at two of them.
7. **Check it:** `python3 .agents/skills/website-dev/scripts/check_page.py http://localhost:8787/<page> …`
   (same checker the ReplyPen chat agent runs on its preview: HTTP 200, `<img>` and root-relative
   links resolve; `--expect-selector "#id"` for a section that must exist). Exit 1 = fix it.
8. **Tooling-only change** (AGENTS.md, skills, scripts, CI): prove the site did not change. Build
   before and after, `diff -r` the two `_site` copies: identical, or explain every difference.
9. **Preview:** commit, `git push -u origin <branch>`, `gh pr create --fill`, then
   `gh pr checks --watch` until **Workers Builds: <worker>** passes (`name` in `wrangler.jsonc`).
   Preview URL: `https://<branch>-<worker>.rootcause-sites.workers.dev` unless AGENTS.md says otherwise.
   Run `check_page.py` on the preview pages too.
10. **Stop at the preview.** Report the preview URL and ask. Merge (`gh pr merge --squash
    --delete-branch`) only after the site owner's OK on that preview (a green build is not approval),
    then confirm the change on the live URL.

## Rules (the same ones the ReplyPen chat agent follows)

- **Never invent facts:** hours, prices, names, phone numbers, quotes, figures. Missing value: ask.
- Copy is the customer's: keep its language, tone and wording; no new marketing claims.
- Facts live in `_data/site.yml` (or what AGENTS.md names), never hardcoded in a page.
- Minimal diffs: reuse existing classes, no inline styles or scripts (the CSP blocks them), no
  reformatting of files you were not asked to change. One ask, one branch.
- Never hand-edit generated output: `_site/`, sitemap, robots, generated listings and indexes.
- A content ask touches content files only (AGENTS.md lists the off-limits ones). Build files
  (`package.json`, lockfile, `.eleventy.js`, `build.sh`, `wrangler.*`, `_headers`, `_redirects`,
  `.github/`) change only when the task is about them, then step 8 applies.
- Contact form: never rename fields or the endpoint. Do not submit the real form to test layout: it
  mails the customer's inbox.
- Learned something durable about this site (a new recipe, a page type)? Add it to its AGENTS.md,
  concise: it is pasted into every chat edit (cap ~16 KB).

## Gotchas

- Cloudflare Turnstile (the form's bot check) never issues a token in headless Chromium: bot
  detection, not a bug. A disabled send button there is expected; check the widget in a real browser.
- `check_page.py` checks the first 30 images and 30 root-relative links per page, not relative links,
  CSS assets or JavaScript behaviour: the browser look in step 6 stays required.
- Build passes but the page 404s locally: check the page's `permalink` against the site's URL style
  (with or without trailing slash) in AGENTS.md.
