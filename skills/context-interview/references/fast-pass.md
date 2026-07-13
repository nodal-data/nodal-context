# Fast Pass — the 30-minute traversal

One domain, five confirmed answers, 3–6 seeds, a live delta, and an **honest depth
stamp**. The fast pass is not a different product or a different artifact — it is
the full interview's state machine traversed on a hard question budget, stopping
early on purpose. Everything unasked becomes a `status: draft` stub, which is
already the resume queue: a deep pass later is just normal Stage-0 resume.

Every operating principle still applies unchanged: the analyst owns every
definition, no statistics in context, SQL only as pattern-not-paste query
patterns, one question at a time, every confirmed disambiguation emits a seed
immediately (`eval-seed-harvesting.md`).

## When to enter

- **Offer it at the start.** Right after Stage 0 setup, ask: *"Full interview for
  this domain, or a 30-minute fast pass — five core questions, a live check, and
  the rest drafted for later?"*
- **Time-pressure signals**, any time: "I've got half an hour", "quick version",
  "just the essentials", a calendar the analyst keeps checking.
- **Mid-session conversion.** A full interview running out of time doesn't just
  stop — jump to the fast-pass close-out ritual below so the session still ends
  with a delta and a depth stamp instead of a trailing question.

Stage 0 is **not skippable**: repo scaffold / resume discovery, the warehouse
probe, and the platform question run as usual (silently where possible). One
budget adjustment: run the dbt extraction only if a manifest is already reachable
on disk — don't spend fast-pass minutes waiting for a clone; note it as deferred
and move on.

## Company minimum (~2 minutes)

- **The company name — same rule, never inferred** from a database, schema, or
  table name. If you don't have it from the analyst or a URL, ask.
- One sentence for `overview.md`: *"What does the business sell, and who pays?"*
  Mark the rest of the overview draft.
- **Skip the terminology sweep.** Terms that surface incidentally while you work
  become `status: draft` stubs in `terminology.md` — captured, not chased.

## The five questions (the analyst picks the domain)

Ask which domain (or dashboard) matters most right now; that's the one you do.
Each confirmed answer is written to its ACF home **and emits its seed at the
moment of confirmation** — same rule as the full interview, no batching.

1. **Grain.** *"Which table is THE table for this, and what does one row
   represent?"* Probe hard — wrong grain is the #1 wrong-answer mode ("one row
   per session, or per session × service?"). → `domain.yaml` (canonical table,
   grain), `reference.md` Quick Reference.
2. **The one ambiguous entity.** *"When someone asks about this domain, which
   word could mean two different things in the data?"* Disambiguate just that
   one. → entity file + seed.
3. **Top metrics (2–3, cap it).** *"What are the two or three numbers people ask
   for most — and for each, what's the definition and the single biggest way to
   get it wrong?"* One caveat per metric is the budget; further caveats become
   draft stubs. → `metrics.yaml` + a seed per metric.
4. **The standard hygiene filter.** *"Which filter does every correct query here
   apply that a newcomer would forget?"* → `reference.md` Quick Reference +
   seed.
5. **The one silent failure.** *"If a new analyst wrote the obvious query, where
   would the answer look plausible and be wrong?"* → `known-issues.md`, an
   `IF … DO NOT …` routing trigger in `reference.md`, and a seed — the
   highest-value one of the session.

**Budget discipline:** one follow-up per question, then write and move on. When
the analyst opens a rich vein (they will), capture the items as draft stubs with
a one-line note and keep going — the stubs are the deep-pass agenda, and chasing
them now is how a fast pass fails the analyst.

## Mini live verification (~2–3 questions)

Run `live-verification.md` as written, at reduced n: the silent-failure question
plus one or two dashboard questions. Same off/on/truth flow, same seed upgrades,
same mismatch harvesting. One honesty requirement in the summary: **say the n** —
*"3 questions is a smoke test, not a measurement"* — small-n deltas are swingy
and must not print as false precision.

## Close-out ritual (mandatory — this is what makes fast pass safe)

The strategic risk of a fast pass is shallow context masquerading as coverage.
The close-out prices the shallowness visibly. Never skip it, even when time ran
out — especially when time ran out.

1. **Depth-stamp the domain** in its `context.md` (narrative file, no schema
   impact): `_Fast-pass capture (YYYY-MM-DD): five core questions confirmed;
   N drafts open._`
2. **Note it on the roster** in `company/org-structure.md`: the row's `Status`
   column keeps its normal meaning (owner draft/confirmed — don't overload it);
   add the depth to the **Notes** section instead:
   `<domain>: fast-pass capture (YYYY-MM-DD), N drafts open.`
3. **Print the close:** the live delta (with its n), the confirmed count, the
   open-draft count, and the punch list (anything still wrong with context on,
   plus the deferred stubs).
4. **Offer the next step, punch-list-first:** *"The deep pass on this domain
   starts from exactly this list — want to book it, or fast-pass another domain
   first?"* Depth goes where the measurement says it pays, not everywhere by
   default.
5. **Commit** per the "Pausing a session" rules in `SKILL.md` — drafts included,
   message naming where work stopped (e.g. `wip: billing fast pass — 5 confirmed,
   7 drafts open`).

## Guardrails

- **The budget is hard.** A fast pass that becomes a two-hour interview has
  failed the analyst's trust; if there is genuinely more appetite, close the fast
  pass properly first, then continue as a normal full-interview session.
- **Never present a fast-passed domain as covered.** The depth stamp and draft
  count travel with every summary, resume message, and PR description.
- **Don't invent to fill the gaps** the budget leaves — `_To be confirmed by
  [owner]._` + `status: draft`, as always. A fast pass changes how much you ask,
  never how much you assume.
