# Settlement Feasibility & Fee Engine — Take-home

Welcome, and thanks for taking the time. The full problem is in
[`ASSIGNMENT.md`](./ASSIGNMENT.md). This README is just orientation.

## The task in one line

Given a client's escrow account, a settlement offer, and a creditor's rules,
decide whether the offer is affordable (and schedule it, collecting our fee as
early as allowed) or — if not — compute the minimum extra funding needed.

## Problem context

This section restates the problem in full so the README stands on its own;
`ASSIGNMENT.md` remains the authoritative spec for exact wording and edge
cases.

A debt-settlement client saves a fixed amount every month into a single
escrow account (the **SDA**). Those deposits (**drafts**) are already
recorded in the account's **ledger** as `credit` entries; anything else in
the ledger — a `debit` — is a previously-committed payment on some *other*
debt and is fixed, never to be touched. Out of the same account, the company
negotiates and pays down one specific debt (the **offer**) in monthly
installments (**creditor payments**), while also collecting its own
**program fee** and a small flat **bank fee** on every date it actually pays
the creditor.

The creditor payments recur on their own monthly **cadence** — independent of
the draft schedule — starting at the offer's `first_payment_date` and never
past the **horizon** (`last_draft_date`). Each creditor sends its own **rules**
governing that cadence: how many payments are allowed, a minimum payment size
that can step up over time (**tiers**), how many payments are allowed to sit
at the bare minimum (**token pays**), and whether payments must be perfectly
even, may **balloon** into one large final payment, or may step up through a
bounded number of distinct levels (a **staircase**).

Two things have to be computed from this:

1. **Feasibility** — does *any* valid payment schedule exist such that the
   escrow balance never goes negative, on any date, all the way to the
   horizon? If so, produce one (`evaluate_offer`'s "Part 1").
2. **The minimum fix** — if no schedule exists, how much *additional* money —
   either as a single lump sum on one date, or as a uniform bump to every
   future draft — would be the smallest amount that makes one exist?
   (`evaluate_offer`'s "Part 2"), each checked against a guardrail cap beyond
   which the fix is reported but flagged as impractical.

The genuinely open-ended part of the problem is the payment **shape**: the
spec deliberately does not prescribe whether payments should be flat,
staircased, or balloon into a final lump — it hands over one economic
objective (front-load the program fee — collect it as early as the cash flow
allows) and expects the shape to fall out of pursuing that objective under
whatever flags a given creditor sets, not to be hard-coded per flag. That
objective, and how each shape expresses it, is the crux of the design
discussed below.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Layout

```
hiring_takehome/
├── ASSIGNMENT.md            # full specification — read this
├── feasibility/
│   ├── models.py            # data models, JSON loaders, date/EOM helpers (provided, hardened)
│   ├── money.py             # round-half-up, percentage-of-cents
│   ├── cadence.py           # payment cadence dates, horizon filtering
│   ├── constraints.py       # per-position floors, non-decreasing/token-pay checks
│   ├── shapes.py            # candidate generators: even / balloon / staircase
│   ├── simulate.py          # chronological ledger walk, greedy fee front-loading
│   ├── funds.py             # Part 2: lump-sum & monthly-increment minima
│   └── engine.py            # evaluate_offer — orchestrates the above
├── cases/                   # four example cases (client.json / offer.json / creditor_rules.json)
│   ├── case1_feasible_even
│   ├── case2_infeasible_minima
│   ├── case3_balloon
│   └── case4_tiers
├── tests/                   # test_smoke.py / test_cases.py (provided) + one file per module above
├── run.py                   # python run.py cases/<case>
└── requirements.txt
```

## Run

```bash
# evaluate a single case (prints the Result as JSON)
python run.py cases/case1_feasible_even

# tests
pytest -q
```

`pytest -q` runs 52 tests: the provided smoke tests and case expectations,
plus one file per module in `feasibility/` (money, cadence, constraints,
shapes, simulation, funds, loaders).

---

# Implementation notes

## A worked example first: `case3_balloon`

This case is the clearest illustration of the whole pipeline, so start here
instead of the abstract description. `BalloonCo` allows ballooning, charges no
program fee, and offers a $600 balance settled for 50% ($300) over up to 6
monthly payments with a $25 floor. The client deposits $100/month, but a
$150 committed debit lands on Feb 1 — a previously-settled payment on another
debt that the engine must respect but never touch.

The engine's answer: four payments of $25 (the floor), then a final payment
of $200 that absorbs everything left. Why not fewer, larger early payments?
Because the objective (§ below) says keep early creditor payments as small as
the rules allow — here that just happens to be visible directly in the
schedule, since there's no fee to front-load. Why does the balloon land on the
5th payment rather than the 6th? Because that's the earliest point at which
`total - 4×floor` is both fundable (given the Feb 1 debit) and a genuine
balloon (strictly larger than the payment before it) — the solver tries every
`k` from 1 upward and keeps the most front-loaded feasible one, so it isn't
hand-tuned for this case; it falls out of trying `k=2,3,4` and rejecting each
because the ledger dips negative or the balloon degenerates into a flat tail.

## Approach

Four stages, mirroring the four hard requirements in `ASSIGNMENT.md` §5 that
aren't already covered by data validation:

1. **Cadence** (`cadence.py`) — monthly dates from `first_payment_date` (or
   the provided EOM default), truncated to the horizon. `k` is capped at
   `min(max_payments, max_terms, |cadence|)`.
2. **Candidate generation** (`shapes.py`) — for each `k`, produce payment
   vectors that already sum exactly to the offer total (constraint 2), one
   generator per shape. See "Shape interpretation" below for how each one
   embodies the front-loading objective.
3. **Hard-constraint check** (`constraints.py`) — non-decreasing, per-position
   floors (base min, raised by tiers), and the token-pay count cap. Exact sum
   is already guaranteed by construction, so it's asserted rather than
   re-derived.
4. **Simulation** (`simulate.py`) — one chronological pass over the committed
   ledger plus the candidate's scheduled debits, crediting before debiting on
   each date, asserting the balance never dips below zero. The program fee is
   collected **greedily**: at every cadence date, take `min(remaining_fee,
   current_balance)`. For a fixed payment vector this is provably the most
   front-loaded possible fee collection, so no search is needed at this
   layer — only across candidates.

`engine.find_best_schedule` ties these together: for each shape the creditor
flags make eligible (in priority order — see below), across every `k`, every
generated-and-validated candidate is simulated, and the one with the largest
cumulative-fee-by-date tuple (compared lexicographically) wins. Because the
committed ledger and the full cadence-date list don't depend on `k` or the
candidate, the per-date timeline is built **once per solve** and every
candidate's fee tuple has the same length — so "most front-loaded" is always
an apples-to-apples comparison, not accidentally biased toward a larger or
smaller `k`.

Part 2 (`funds.py`) reuses `find_best_schedule` as a black box. Feasibility is
monotone in added cash (more money on a date that already has activity can
only help a balance-≥-0 simulation), so both minima are binary searches over
"does adding this much extra cash make it feasible" — no separate feasibility
math to get right twice.

## Alternatives considered

| Decision | Chosen | Alternatives rejected | Why |
|---|---|---|---|
| Core solver | Structured candidate generation per shape, then validate + simulate, keep the best by a fee-earliness score | (a) formulate as an ILP/MILP (e.g. OR-Tools, PuLP) and let a solver directly maximize fee-earliness subject to all constraints; (b) dynamic programming over (cadence position × cumulative amount paid); (c) brute-force enumeration of every non-decreasing integer vector summing to the total | Zero third-party dependencies for a financial calculation that has to be auditable line-by-line; an ILP is provably optimal but turns "why did it pick this schedule" into a black box, and pulls in a heavy solver dependency for a problem whose shapes are already well understood analytically. DP's state space (amount paid, up to the offer total in cents) is needlessly large versus the closed-form-ish structure of each shape. Brute force is exponential in `k` and pointless once floors/tiers/segments are known to constrain the search this tightly. |
| Program-fee timing | **Greedy**: take `min(remaining_fee, balance)` at every cadence date, earliest first | Formulate fee-splitting across dates as its own small LP or search | For a *fixed* payment vector, the total fee collected is constant and feasibility is monotone in how early each dollar of it is taken (taking it later can only ever tie, never help, since it just delays a debit that has to happen anyway before the horizon) — so greedy is provably the most front-loaded split possible. No search needed at this layer; the actual search happens one level up, across payment vectors. |
| Part 2 minima | **Binary search** over added cash, re-running the exact same solver as a black box | A closed-form deficit formula (e.g. "sum the shortfalls and report their max") | Feasibility depends on the *entire* schedule search (shape, floors, segments, fee timing all interact), not one inequality — there is no clean closed form that doesn't essentially re-derive the solver. Binary search is `O(log(upper_bound))` calls to a solver that already exists, so it's both correct by construction and doesn't duplicate any solver logic (the two minima can never silently disagree with what Part 1 would actually schedule). |
| Shape dispatch | A plain dict of generator functions (`shapes.SHAPE_GENERATORS`), selected by `engine._eligible_shapes` from the creditor flags | A `Strategy`-pattern class hierarchy (one subclass per shape, each declaring its own `applies()`/`priority()`) | Three shapes with simple, stable eligibility rules don't need runtime polymorphism — a dict lookup plus one small ordering function reads the same info more directly, with less indirection to trace through when auditing "why did this shape get tried." Either approach is easy to extend with a fourth shape; the class hierarchy earns its complexity once shapes need per-instance state or configuration, which none of these do. |
| Money | Integer cents everywhere, `Decimal` + explicit round-half-up only at the few points the spec calls for rounding | Floats throughout, or `Decimal` for every intermediate value | Floats risk binary-representation drift in a monetary calculation and Python's native `round()` breaks ties toward even, not away from zero, which the spec explicitly forbids. `Decimal` everywhere is safer still but adds friction for no benefit once every stored amount is already an integer — rounding only ever happens at the two derived quantities (`offer_total`, `program_fee`) and the two guardrail caps. |
| Staircase segment search | Pin every segment but one at its floor; search a bounded window on the remaining one for exact divisibility | An exhaustive search over every integer level assignment per segment, or an LP/ILP for the segment levels directly | The pin-and-flex approach is a direct generalization of the two-segment case (which only ever needs one free variable to hit an exact integer total) and stays linear in `k` per partition tried; a full multi-variable integer search is combinatorially worse for a benefit that, per "Known limitations" below, only matters for adversarially-shaped floors that didn't appear in any provided or constructed test case. |

## Shape interpretation

The shape is an **outcome** of one objective, not a hard-coded form:

- **Even** (`even_pays`): forced equal, remainder cents pushed onto the
  *latest* payments to preserve non-decreasing order (§5.7 is explicit about
  this). The only freedom is `k`, chosen for maximum front-loading.
- **Balloon** (`is_ballooning_allowed`): the purest expression of the
  objective — every payment but the last sits at its position's floor
  (including any tier or token-pay pressure), and the last absorbs the
  remainder. It's only emitted as a candidate when it's a *real* balloon (the
  last payment strictly exceeds the one before it); a degenerate case falls
  through to the staircase generator instead of silently failing.
- **Staircase** (neither flag, or ballooning allowed but no balloon is
  feasible): non-decreasing payments using at most `max_segments` distinct
  levels. All segments but one are pinned at their own floor (the lowest the
  objective would ever want); the remaining segment is searched over a
  bounded window to find one that divides the leftover total evenly, and the
  final segment absorbs what's left. This generalizes cleanly to any segment
  count — see "Known limitations" for the one place it's still not
  exhaustive.

**Tiers and token pays interact with a balloon or staircase only through the
per-position floor.** A tier raises the floor from a given position onward; a
token pay is any payment sitting exactly at the *base* minimum, capped in
count — so a staircase whose low segment sits at the base floor is
automatically token-limited by the same validation pass that checks every
other candidate, rather than needing special-case logic.

**Shape priority when a creditor allows more than one:** `even_pays` forces
even outright (ballooning is irrelevant per §5.7). Otherwise, if ballooning is
allowed it's tried first — and used whenever any `k` produces a feasible real
balloon — with staircase as the fallback. This matches the intuition that a
balloon is the most aggressive form of front-loading available.

## Assumptions

- **Offer balance field.** ASSIGNMENT.md §3 describes a rename to
  `creditor_balance_cents`, but every case file and the provided `models.py`
  loader still use `current_balance_cents` on the offer. I followed the data
  and code as given rather than the prose, and `offer_total_cents` /
  `program_fee_cents` in the smoke tests confirm this.
- **Round-half-up** is implemented explicitly (`money.round_half_up`, via
  `Decimal`) for the offer total, the program fee, and both Part 2 guardrail
  caps — Python's builtin `round()` rounds half-to-even and is never used for
  a monetary calculation.
- A **fee-only cadence date** (fee collected, no creditor payment) never
  carries a bank fee; the bank fee is tied strictly to dates that carry a
  creditor payment.
- The simulation only requires the balance to stay `≥ 0`; it does **not**
  require the account to end at exactly zero. `case1`'s schedule, for
  example, ends at a positive balance.
- **Every future ledger credit is a draft** (per the glossary), so the
  monthly-increment count `N` is simply the number of ledger credits dated
  after `as_of_date` — including any that land too late in the horizon to
  actually help, which is why the lump and the increment can imply different
  totals (ASSIGNMENT.md §8 calls this out explicitly).
- **Lump-sum placement.** An earlier lump is weakly more useful than a later
  one (more of the simulation gets to benefit from it), so it's placed on the
  earliest date anything already happens on the timeline — the first future
  draft or the first cadence date, whichever comes first. This also covers
  the edge case where a creditor's cadence starts before the client's first
  draft.

## Known limitations

- **Staircase candidate generation is structured, not exhaustive.** For
  partitions of 3+ segments, only the second-to-last segment is searched for
  a value that makes the total divide evenly — every other segment is pinned
  exactly at its own floor. This covers every case in `cases/` (including a
  synthetic 3-tier, 3-segment case added in `tests/test_shapes.py` to prove
  segment counts beyond 2 actually work) and is consistent with the
  front-loading objective, but a creditor whose floors are shaped so that
  *no* single-segment adjustment can hit the exact total — while some
  multi-segment adjustment could — would be reported as having no staircase
  candidate for that `k`, even though one technically exists. The hard
  constraints are always re-validated on whatever is generated, so this can
  only under-produce candidates, never accept an invalid one.
- **Selection is best-of-generated, not a proven global optimum.** The chosen
  schedule is the most front-loaded *among the candidates the generators
  produce*, which is provably optimal for `even` and `balloon` (each shape
  has essentially one canonical candidate per `k`) but only a strong heuristic
  for `staircase`.
- **Part 2's binary-search upper bound** is a deliberately generous but finite
  estimate (`funds.deficit_upper_bound`) — the full offer, program fee, every
  possible bank fee, and every committed debit. If that bound were somehow
  still infeasible (a horizon far too short for even one payment, for
  instance), the reported minimum would be the bound itself rather than a
  true infinity; this is a bound-tightness issue, not a correctness one, since
  such an input would already fail every provided guardrail.
