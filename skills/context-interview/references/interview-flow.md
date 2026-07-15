# Interview Flow

The question script for each stage. These are starting points, not a rigid form —
follow the analyst's lead, but make sure each stage's *goal* is met before moving
on. Ask one question at a time. When you can draft and ask "is this right?",
prefer that over an open question.

Throughout: when the analyst confirms a disambiguation, immediately write the eval
seed (see `eval-seed-harvesting.md`). Don't batch them to the end — you'll lose the
exact phrasing that makes a seed useful.

---

## Working a long list: elicit, then batch

Several stages produce *many* items — terminology terms (§1), entity
disambiguations (§3), caveats (§4). Do **not** ask the analyst to name **and** define
them all in one turn; that's a wall of line items no one can react to. Instead:

1. **Elicit the list first (cheap, breadth-first).** Ask the analyst to just *name*
   the candidates — "List them; don't define them yet. We'll go through them together
   a couple at a time." Write each as a `status: draft` stub in the stage's output
   file, using the no-invented-definitions placeholder: `_To be confirmed._` with a
   trailing `<!-- status: draft -->`. These stubs are your scratchpad **and** your
   progress tracker.
2. **Confirm 1–3 at a time.** Take one to three stubs, ask that stage's probe (meaning
   + misconception, or the disambiguation), draft it, confirm with the analyst, then
   flip `draft → confirmed`. Start with one or two; go up to three only if the analyst
   is moving fast.
3. **Write the seed right then.** Each confirmed item emits its eval seed *at the
   moment of confirmation* — small batches don't defer seeds, they make it natural to
   capture each one immediately (this is the same "don't batch seeds to the end" rule
   above, not an exception to it).
4. **Show progress every round.** One line: "Terminology: 3 of 8 confirmed, 5 to go.
   Next: <item>." The count is just confirmed stubs vs remaining `draft` stubs.
5. **The list isn't frozen.** Let the analyst add or drop candidates as you go; delete
   a stub that turns out irrelevant.
6. **Resume for free.** If the session is interrupted, the remaining `draft` stubs
   *are* the queue — on return, count them and pick up where you left off (see
   "Updating an existing repo" in `repo-scaffold.md`).

§1, §3, and §4 below each invoke this pattern.

---

## §1 — Company

**Goal:** `company/overview.md` and `company/terminology.md`, both confirmed.

**First, get the company's name right — and never infer it.** Take the name from the
analyst or their website. Do NOT derive it from a database, schema, warehouse, or
table name you queried: those are warehouse identifiers, frequently codenames,
acquisitions, or internal project names that differ from the company. If you don't have the
name yet, ask plainly: *"What's the company's name?"* The name anchors `overview.md`
and the repo, so a wrong guess propagates everywhere.

If given a company URL, fetch it first, draft `overview.md`, and open with:
> "I read your site and drafted a one-paragraph description of what the business
> does and how it makes money. Correct anything that's off — especially the revenue
> model, because that's what most metric questions trace back to."

Then:

1. "In one sentence, what does the business actually sell, and who pays?"
2. "What's the unit of value you count most — a session, an order, a seat, a
   policy? That's usually the grain of your most important fact table."
3. "Name the 5–10 terms a new analyst always gets wrong in their first month — just
   *name* them, we'll define them together." Then run the **elicit-then-batch**
   pattern (above): write each named term as a `status: draft` stub in
   `terminology.md`, then work them 1–3 at a time — for each, "What does it mean here,
   and what do people *think* it means?" → a terminology entry **and** an eval seed —
   showing the progress line each round.
4. While eliciting, also ask "Are there terms that two teams define differently?" Add
   these to the same list (they're high-value — a guaranteed silent-failure source).

Write `terminology.md` as a glossary. Anything still unconfirmed stays `status: draft`
in a trailing comment until the analyst confirms it.

---

## §2 — Domains (from dashboards)

**Goal:** for each domain — `domain.yaml`, `context.md`, `reference.md`.

Open with the dashboard question, because the dashboard catalog *is* the company's
own decomposition of itself:
> "List the dashboards your team maintains and who owns each. I'll group them — each
> group is usually a 'domain' the agent should know about."

If Stage 0's dbt extraction found **exposures** (`dbt-findings.json` `exposures[]`),
use them as the dashboard catalog — each exposure is a dashboard plus its dependency
models, which also seeds the domain boundary. Confirm the clustering with the analyst
rather than asking them to list from scratch. If `unavailable` includes `exposures`
(many dbt projects, including ones with no `exposures:` blocks), ask the question
above instead.

If Stage 0 also produced `.query-findings.json` (query-history mining), its
admitted `bi_service` clusters are a **parallel draft catalog** — each recurring
cluster is a dashboard-shaped unit: a recurring question plus the tables it
reads. Merge them with the exposures (or use them alone when `unavailable`
includes `exposures`) and confirm the clustering with the analyst. When a
`conflict_groups[]` entry touches the domain you're capturing, ask it as the
disambiguation question — the analyst's resolution becomes the metric's
`expression:` and a seed with `ir:` (see
`query-history-extraction.md` for the phrasing).

Cluster the dashboards. For each cluster (domain):

1. "What business question is this cluster of dashboards really answering?"
   → the domain's `summary`.
2. "Which tables feed these dashboards? Which one is *the* table for this domain?"
   → `tables`, and flag the canonical one.
3. "What does one row of that table represent?" → **grain**. Probe hard here;
   wrong grain is the most common wrong-answer mode. ("Is it one row per session,
   or one row per session × service?")
4. "Where do these models live — which dbt project / repo, and on which platform
   (Snowflake / BigQuery / Postgres)?" → the **lineage pointer** in `domain.yaml`
   and `context.config.yaml`. Point the domain at a `lineage_sources` entry by `id`;
   create that entry now if Stage 0 only captured the platform list. If the source's
   platform differs from the repo-wide default, set `warehouse:` on the source entry;
   if it matches, add nothing — it inherits. A domain on two platforms just lists a
   lineage entry per source. Do not skip this; it's what lets drift detection protect
   the domain later.
5. Now build `reference.md` using `reference-doc-skeleton.md`. This is the file the
   agent reads at query time, so write it for retrieval: routing triggers, grain,
   standard hygiene filter, gotchas — not narrative.
6. **Record ownership in two places, together.** You already asked who owns each
   dashboard at the top of this stage. When a domain's owner is confirmed, set
   `owner:` in its `domain.yaml` **and** add/update that domain's row in
   `company/org-structure.md` (Domain | Owner | Team | Status). These must stay in
   sync — `org-structure.md` is the routing roster, `domain.yaml` is the per-domain
   record. If the owner isn't known yet, write `_To be confirmed._` and leave the
   row's status `draft`; don't guess.

For each dashboard, ask: "What's the canonical question this dashboard answers, and
what's the right answer as of a fixed date?" → a `dashboard`-provenance eval seed
with a `value_at_snapshot` expectation.

---

## §3 — Entities

**Goal:** the ambiguous terms that map to data values, captured and disambiguated.

For each domain, run the **elicit-then-batch** pattern (above): first surface the
candidate ambiguous terms across the three patterns below as `status: draft` stubs in
`entities/*.yaml` (cross-domain) or `domains/<domain>/entities.yaml`, then disambiguate
them 1–3 at a time with a progress line — a seed per confirmed term. Hunt for three
patterns:

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

Run the **elicit-then-batch** pattern (above) here too. Open with the framing
question to surface the candidate failure modes, capture each as a `status: draft`
stub in `known-issues.md`, then work them 1–3 at a time with a progress line —
writing the routing trigger + seed as each is confirmed. The follow-ups below are
prompts for surfacing more candidates, not a checklist to answer in one pass.

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
5. "Is there a query whose exact *form* is the hard part — a dedup, join path, or
   clause that even careful analysts get wrong?" → a confirmed **Common query
   pattern** in `reference.md` (pattern-not-paste; rules in
   `reference-doc-skeleton.md`), plus a `sql_shape` seed encoding the same form.
   (A high-count query-history cluster the analyst recognizes as "the query
   everyone gets wrong" is a ready-made candidate.)

For each, write the caveat as a routing trigger the agent will read, and an eval
seed whose `expected` encodes the *correct* handling (right filter, right table, or
"clarify before answering").

**When a metric is confirmed, draft its `expression:` too.** Once the analyst has
confirmed a metric's measure, its must-have filters (follow-ups 1–2), and what it
may be sliced by, assemble them into the metric's structured `expression:` block in
`metrics.yaml` — `measure` + `mandatory_filters` (each with a `reason` naming the
failure it prevents) + `allowed_dimensions` — and read it back for confirmation
like any other draft (see SPEC.md "Deterministic anchor"). The schema requires
`grain` and `lineage` on any metric carrying an expression, so confirm those at the
same moment (§2 steps 3–4 usually already captured them). Later edits to a
confirmed metric's expression reset it to `status: draft` until re-confirmed.

---

## §5 — Live Verification

**Goal:** show the context working on this domain and harvest dashboard-anchored
seeds. At domain close, answer a handful of the domain's questions against the live
warehouse twice — context off vs on — with parallel in-session subagents, then have
the analyst confirm the on-answer against their dashboard. Matches become
`value_at_snapshot` / `dashboard` seeds whose blessed SQL is written to a gitignored
sidecar (`evals/verified/`) and referenced by `verified_query_file`; mismatches feed
a caveat + a `correction` seed. This stage has its own reference —
read `live-verification.md` when you enter it.

---

## When the analyst doesn't know

That's a finding, not a failure. Write `_To be confirmed by [owner]._`, mark
`status: draft`, add a `# REVIEW:` comment, and move on. Drafted-but-unconfirmed
context is excluded from the "perfect" eval baseline, so it won't silently corrupt
the delta.
