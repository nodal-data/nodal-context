# Session progress

Show one bold text line above each user-facing interview question in both modes.
Update it after each answer and at stage transitions; it is ordinary conversation
text, with no host-specific UI dependency. Keep the existing one-thing-at-a-time
question style.

## Before each question

Use this loop for every analyst response: **process answer → update agenda and
counts → display progress → ask next question**. On the first question, initialize
the agenda and display progress before asking. This applies to setup, follow-ups,
confirmations, selection dialogs, and verification prompts, even when the stage
and estimate have not changed.

For a question or selection tool, send the bold line in a separate visible
assistant message immediately before invoking the tool. Do not put it only in
internal reasoning, tool arguments, or an earlier status update. For a prose
question, place it immediately above the question in the same message. Immediately
before sending either kind of question, check that its progress line is present;
if absent, emit it first. No extra analyst acknowledgment is needed.

If the agenda or previous count is unavailable, still display the current scope
and stage with `Re-estimating questions remaining`. Rebuild from the conversation
and remaining drafts without inventing historical counts. Preserve any known
counts and resume numeric estimates once grounded; uncertainty never means omit
the line. After an interruption or conversation compaction, restore this loop
before the next question.

## Count the user's remaining effort

Maintain a session agenda in conversation state: current scope and stage, answered
questions, known remaining questions, likely follow-ups, and topics deferred for
later. Do not add ACF fields or write `.nodal.local.json` for progress.

- Count each answered user-facing question once, including answered follow-ups;
  tool calls, generated seeds, and background warehouse queries are not questions
  answered by the user. Skips/deferred items leave the active queue without becoming
  answered or confirmed. An answer is not automatically a confirmed definition.
- Remaining estimates include the question being displayed. Base the lower end on
  known queued questions and the upper end on plausible follow-ups. Recalculate
  after each answer; remove questions already resolved incidentally. Do not invent
  questions to fill an estimate or equate draft-item counts with question counts.
- During setup/discovery, use **Setup · Estimating remaining questions** until
  enough scope is known. Do not manufacture a total or a percentage. Include any
  outstanding setup/company prompts once an estimate is possible.
- Keep answered counts monotonic within the session. On resume, rebuild the agenda
  from existing drafts and the conversation; if prior counts are unavailable, label
  the count `answered this session` rather than inventing historical progress.

## Full interview

Scope the indicator to the current domain round, with verification shown separately:

> **Billing · Metrics · 8 answered · ~6–9 interview questions left · live check afterward**

Explain at the first estimate that it covers this domain round, not every domain
in the company. When necessary discoveries increase the remaining estimate, add
one short reason, for example: “The regional revenue rules add about three
follow-ups.” Reflect resolved or deferred questions in the next estimate too.
Keep new domains in the later agenda until the user chooses to continue to them.
Moving between stages changes the stage label, not the estimate's scope: questions
left always covers the current domain round, not just the current stage. Do not
reset the answered count at stage boundaries. Before a domain is chosen, retain
the setup/discovery fallback rather than inventing a stage-only total.

For long lists, incorporate the local item count into the same line when useful,
explicitly labeled (for example, `Terminology: 3/8 terms confirmed`). It does not
replace the remaining-question estimate.

## Test drive

Use the five core topics as the fixed anchor, while estimating actual prompts:

> **Test drive · Filters · 3/5 core topics complete · ~2–4 interview questions left · live check afterward**

The five core topics are the numbered prompts in `test-drive.md`; setup, company
questions, follow-ups, and live verification are additional user effort, not extra
core topics. Mark a topic complete only once its required answers are confirmed;
identify a deferred topic as deferred rather than claiming 5/5 complete.

Keep the existing one-follow-up-per-core-question cap and time budget. Extra
discoveries normally become draft stubs, with a brief note such as “Saved three
additional topics for the full interview.” Do not expand the quick test to make
the counter reach completion. If converting from a full interview mid-session,
follow its existing close-out rule instead of starting five new topics.

## Verification and close-out

At the transition, use **Billing · Interview complete · Live check next**, or
`Interview stopped · Live check next` if capture ended early. During verification,
show **Billing · Live check · 1/3 cases reviewed** (prefix `Test drive` in that mode).
A reviewed case has been checked with the analyst, even if it mismatches; progress
does not imply a passing result. Background execution does not advance this count.
Show additional user prompts or discrepancy follow-ups as estimated questions left
when needed; explain added cases. If verification is unavailable or deferred, say
so instead of marking it complete.

Close with **This round complete · 7 topics saved for later**, using actual counts
and naming any deferred verification. This marks the session stopping point,
not complete domain coverage; retain the test drive's mandatory depth stamp.
