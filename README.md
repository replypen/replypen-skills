# ReplyPen skills

Agent skills for developers working with [ReplyPen](https://replypen.com) from their own product
repositories: investigating a run the ReplyPen agent handled, reading an auto-filed escalation
ticket, and handing a finding back. MIT licensed.

**Holding only a ticket and a run link?** No install needed: read
[run-investigation.md](skills/replypen-core/references/run-investigation.md).

## Install

Repo-local (tracked copy under `.agents/skills/replypen-core` plus `skills-lock.json`):

```sh
pnpm dlx skills add replypen/replypen-skills -s replypen-core -y
```

Then add a thin project wrapper skill `replypen` next to it that owns your local config: project
and tenant names, ticket list ids, who owns the brain, which writes are allowed. The core is
replaced on update, so nothing project-specific lives in it.

The `rp` CLI (`rc` is an alias): `brew install --cask replypen/tap/rp` (macOS) or see
[replypen-cli](https://github.com/replypen/replypen-cli#install).

| Skill | Use when |
| --- | --- |
| [replypen-core](skills/replypen-core/SKILL.md) | you got a run link / escalation ticket, need a narrow production read, or must route a finding |

Brain authoring (the agent's own knowledge repo) is documented in
[replypen-brain-skills](https://github.com/replypen/replypen-brain-skills).
