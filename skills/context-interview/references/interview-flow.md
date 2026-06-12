# Interview Flow

The question script for each stage. These are starting points, not a rigid form —
follow the analyst's lead, but make sure each stage's *goal* is met before moving
on. Ask one question at a time. When you can draft and ask "is this right?",
prefer that over an open question.

Throughout: when the analyst confirms a disambiguation, immediately write the eval
seed (see `eval-seed-harvesting.md`). Don't batch them to the end — you'll lose the
exact phrasing that makes a seed useful.

---

## §1 — Company

**Goal:** `company/overview.md` and `company/terminology.md`, both confirmed.

If given a company URL, fetch it first, draft `overview.md`, and open with:
> "I read your site and drafted a one-paragraph description of what the business
> does and how it makes money. Correct anything that's off — especially the revenue
> model, because that's what most metric questions trace back to."

Then:

1. "In one sentence, what does the business actually sell, and who pays?"
2. "What's the unit of value you count most — a session, an order, a seat, a
   policy? That's usually the grain of your most important fact table."
3. "Name the 5–10 terms a new analyst always gets wrong in their first month."
   For each: "What does it mean here, and what do people *think* it means?"
   → each of these is a terminology entry **and** an eval seed.
4. "Are there terms that two teams define differently?" (These are high-value —
   they're a guaranteed silent-failure source.)

Write `terminology.md` as a glossary. Mark anything you drafted but didn't confirm
`status: draft` in a trailing comment.

---

## §2 — Domains (from dashboards)

**Goal:** for each domain — `domain.yaml`, `context.md`, `reference.md`.

Open with the dashboard question, because the dashboard catalog *is* the company's
own decomposition of itself:
> "List the dashboards your team maintains and who owns each. I'll group them — each
> group is usually a 'domain' the agent should know about."

Cluster the dashboards. For each cluster (domain):

1. "What business question is this cluster of dashboards really answering?"
   → the domain's `summary`.
2. "Which tables feed these dashboards? Which one is *the* table for this domain?"
   → `tables`, and flag the canonical one.
3. "What does one row of that table represent?" → **grain**. Probe hard here;
   wrong grain is the most common wrong-answer mode. ("Is it one row per session,
   or one row per session × service?")
4. "Where do these models live — which dbt project / repo?" → the **lineage
   pointer** in `domain.yaml` and `context.config.yaml`. Do not skip this; it's
   what lets drift detection protect the domain later.
5. Now build `reference.md` using `reference-doc-skeleton.md`. This is the file the
   agent reads at query time, so write it for retrieval: routing triggers, grain,
   standard hygiene filter, gotchas — not narrative.

For each dashboard, ask: "What's the canonical question this dashboard answers, and
what's the right answer as of a fixed date?" → a `dashboard`-provenance eval seed
with a `value_at_snapshot` expectation.

---

## §3 — Entities

**Goal:** the ambiguous terms that map to data values, captured and disambiguated.

For each domain, hunt for three patterns:

1. **Status/lifecycle terms** — "active", "new", "churned", "dormant". For each:
   "What exactly makes a row count as 'active'? What's the lookback? What's
   excluded?" → entity `mappings` + `important`, and an eval seed per term.
2. **One word, two entities** — the classic "provider could mean the individual
   or the company." Ask: "Are there words your stakeholders use that map to more
   than one thing in the data?" → entity `important:` with the disambiguation, and
   an eval seed whose `intent` records which entity wins by default.
3. **Looks-atomic-but-isn't** — "Cigna" that's really "Cigna-TX" vs "Cigna-FL";
   blank-but-meaningful values. Ask: "Are there values that look like one thing but
   are really several, or blanks that change the answer if you filter them out?"

Placement: cross-domain (lives in a `dim_*` table or spans facts) → `entities/`;
single-fact-table status/type → `domains/<domain>/entities.yaml`. (See `SPEC.md`.)

---

## §4 — Caveats

**Goal:** `known-issues.md` per domain, and `IF … DO NOT …` routing in
`reference.md`. These produce the most valuable eval seeds — the silent failures.

The framing question:
> "If I gave a brand-new analyst this data and they wrote the most obvious query,
> where would they get an answer that looks completely plausible and is wrong?"

Follow-ups:
1. "Which filter does every correct query in this domain apply that a newcomer
   would forget?" → the **standard hygiene filter** in `reference.md`.
2. "Is there a timing effect — does the data look different if you query it too
   soon?" (e.g., claims that haven't adjudicated.) → a caveat + a parameterized
   metric.
3. "Are there two similarly-named tables that report the same metric at different
   grains? Which is canonical?" → `reference.md` routing trigger.
4. "What's a question stakeholders ask that the data *cannot* actually answer?"

For each, write the caveat as a routing trigger the agent will read, and an eval
seed whose `expected` encodes the *correct* handling (right filter, right table, or
"clarify before answering").

---

## When the analyst doesn't know

That's a finding, not a failure. Write `_To be confirmed by [owner]._`, mark
`status: draft`, add a `# REVIEW:` comment, and move on. Drafted-but-unconfirmed
context is excluded from the "perfect" eval baseline, so it won't silently corrupt
the delta.
