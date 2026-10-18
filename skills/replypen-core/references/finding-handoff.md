# Hand a finding back

Classify first, then route. Always cite the run by UUID (never the `?t=` URL outside the ticket
it came in).

| Class | Signal | Do |
| --- | --- | --- |
| **Product defect** | Your app did the wrong thing; the agent described it correctly | Fix in your product repo. Link the run UUID in the PR/ticket. Close the ticket with the cause and the fix. |
| **Brain gap** | Agent reasoned wrongly from a confirmed stale fact, missing knowledge, script misread data, or a playbook that steered it wrong | Route per the wrapper: hand to the brain owner, or open a brain PR. Name the step `#` and the file it read. A host/platform failure (timeout, blocked egress, tool error) is not a brain gap: report it to ReplyPen. |
| **Expected behaviour** | Product works as designed; agent escalated needlessly | Close with the expected behaviour and reason. If this should change future answers, also route the correction through the wrapper's brain owner or the supported run-feedback path; a ticket comment alone teaches nothing. |
| **Missing access** | The agent (or you) couldn't reach the data needed to decide | Say which data, for which question. Route per the wrapper; never widen a credential yourself. |

A ticket can be two classes (e.g. a product bug the agent also explained wrongly): handle each.

## Rules

- A tenant-specific fact (one customer's setup) is not a brain edit, unless the wrapper says so.
  The brain holds what recurs.
- Keep the closing comment terse: cause, evidence (step `#` or query), fix or reason.
- Brain authoring itself (layout, scripts, publishing) is documented in
  [replypen-brain-skills](https://github.com/replypen/replypen-brain-skills): see
  `docs/brain-model.md` and the `local-brain-work` / `brain-publish` skills. Don't duplicate it.
