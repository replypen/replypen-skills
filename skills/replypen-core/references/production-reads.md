# Narrow production reads

For when the trace shows what the agent saw, but you need a fact it didn't fetch.

## Order of preference

1. **Local source + run artifacts first.** Read the product source for intended behaviour and the
   run's debug JSONL (`stdout` of the relevant steps) for observed state, before touching live data.
2. **The wrapper's preferred authorized production read surface.** Verify profile, project, tenant
   and principal scope before querying; the wrapper grants policy, the server grants access.
3. **Other local tools** (console scripts, admin views, log search) only as the wrapper permits.

## Not a read

- `rp ask "<question>"` **creates a production run**: it costs, is journaled, and under the project's
  configured gates it can place output or execute actions. Use it only to reproduce agent behaviour,
  and prefer `--simulation` (nothing placed, no action, no journal; it still reads real production
  data) when the wrapper allows `rp ask` at all.
- `rp run retry` re-runs a run. Same caution.

## Never

- Ad-hoc production writes (SQL, consoles, scripts). Writes go through the project's action or
  policy path per the wrapper, with the required human approval.
- Pasting secrets, DSNs, tokens or share URLs into prompts, tickets, logs or commits.
- Committing `.replypen/` output; it contains customer data.
