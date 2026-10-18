# Working here

Public MIT skill source for developers who work WITH ReplyPen from their own repos. Each
`skills/<name>/SKILL.md` has `name` + `description` frontmatter and links its `references/`.
Consumers vendor a copy with `pnpm dlx skills add replypen/replypen-skills -s <name> -y`.

Rules:
- Generic only. Project names, tenants, list ids and routing belong in the consumer's `replypen`
  wrapper, never here.
- `rp <cmd> --help` is command truth. Verify every command you write against it; keep examples
  few and link `--help` instead of copying flag lists.
- Never put a real share token, run URL with `?t=`, customer data or secret in an example.
- `SKILL.md` ≤ 80 lines, README ≤ 40; terse, no marketing.
- Link check before committing: every relative Markdown link resolves, external links open:
  `for f in $(git ls-files '*.md'); do grep -oE '\]\([^)#]+' "$f" | cut -c3- | grep -v '://' | while read -r l; do [ -e "$(dirname "$f")/$l" ] || echo "BROKEN $f -> $l"; done; done`
- Install check: `pnpm dlx skills add replypen/replypen-skills -s replypen-core -y` in a scratch
  dir yields `.agents/skills/replypen-core/` and a `skills-lock.json` entry.

Commit logical changes to `main`.
