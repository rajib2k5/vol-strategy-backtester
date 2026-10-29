# Learning log

One row per milestone. Each milestone stops at a checkpoint in the session: short lessons, each
followed at once by its quiz question (with the reason every option is right or wrong, and a link
back to the lesson if you miss it), then the "explain it back" questions. Ungraded "guess first"
prompts come before the lessons they belong to. The walkthrough is the long form behind the
lessons. Results are graded when you send them, and the gaps are filled in the docs.

Learning mode: queued

## Milestones

| # | Topic | Walkthrough | Concepts | Checkpoint | Pairs | Re-asks | Explain-it-back |
|---|---|---|---|---|---|---|---|
| 00 | Foundations: scaffold, contract, design, decisions | [00-foundations](docs/milestones/00-foundations.md) | [00-background](docs/concepts/00-background.md), [01-ssvi-surface](docs/concepts/01-ssvi-surface.md) | queued, 0 of 16 answered | | | |
| 01 | Option-chain data layer and quality filters | [01-data-layer](docs/milestones/01-data-layer.md) | [02-quality-flags-bitmask](docs/concepts/02-quality-flags-bitmask.md), [03-put-call-parity-forward-and-spot](docs/concepts/03-put-call-parity-forward-and-spot.md), [04-osi-symbol](docs/concepts/04-osi-symbol.md), [05-sampling-mask](docs/concepts/05-sampling-mask.md), [06-private-dolt-mirror](docs/concepts/06-private-dolt-mirror.md) | not started | | | |
| 02 | Pricing core: Black-76 on a parity forward, greeks, IV solver, de-Americanisation | — | — | not started | | | |
| 03 | Event-driven engine: marks, fills, expiry, hedging | — | — | not started | | | |
| 04 | Strategies and the VRP signal | — | — | not started | | | |
| 05 | Risk: greek budgets and sizing | — | — | not started | | | |
| 06 | Performance, attribution and stress | — | — | not started | | | |

Answers are recorded as they arrive in `.learning/milestones/NN-checkpoint.md`. That folder stays out of git.

## Missed topics

| Topic | Lesson | Missed on | Re-asked | Cleared |
|---|---|---|---|---|

## Queued checkpoints

- Milestone 00 (queued, 0 of 16 answered). Answer in its quiz widget, or say "quiz me on milestone 0" to resume it.

## Owed checkpoints

None.

## Decisions recorded

See [docs/adr/](docs/adr/). The milestone-0 adversarial reviews and what they changed are in
[docs/validation/](docs/validation/) and §1.6 of the [milestone-0 walkthrough](docs/milestones/00-foundations.md).

## Defaults taken

The owner can override any of these. Each was an open question in `docs/prfaq.md`.

| # | Question | Default taken | Date |
|---|---|---|---|
| 1 | Primary audience | The author, for an interview-ready explanation. The README reports results and links to the docs that teach. | 2026-10-29 |
| 2 | Headline strategy | The short straddle is the headline baseline. The signal-gated strangle is the challenger, reported beside it. | 2026-10-29 |
| 3 | Author quote | Replaced with a plain design statement, so no words are put in the author's mouth. | 2026-10-29 |
| 4 | Bar for "pays" | Two tiers: "pays" is a positive after-cost excess return over T-bills; "pays beyond luck" also needs a headline DSR of at least 0.95. | 2026-10-29 |
| 5 | Where M1 writes downloads and built tables | Inside the repo, in the git-ignored `data/` folder, because this project writes only inside its repo. Vendor sources are still read from `$VOL_DATA_DIR`. | 2026-10-29 |
| 6 | How to read the shared DoltHub clone without writing to it (even `dolt status` rewrites files in `.dolt/`) | Run every `dolt` call in a private mirror, a `cp -a` copy of the clone at `$VOL_DATA_DIR/vol-strategy-backtester/cache/dolt_mirror/options` (the project-wide rule of 2026-10-29). dolt's housekeeping writes land in the mirror. `volbt.data.dolthub` refuses a target, or a work folder, inside the shared clone. This replaced the first default, an `unshare` overlay of the clone. | 2026-10-29 |
| 7 | Relabel DoltHub's 11 closure-dated snapshot dates (2020–24) by parity spot? | No. They are dropped, as M1 does now, because DoltHub has no underlying column to check against the SPY close. | 2026-10-29 |
| 8 | Relabel OptionsDX's 2022-06-20 snapshot to 2022-06-17, as ADR-0009's relabel rule did (06-17 has no snapshot, and the 06-20 underlying equals the 06-17 close)? | No. The rule is removed: all 12 closure-dated vendor dates are dropped, and 2022-06-17 is served as a session without a snapshot. The 06-20 file has 06-17's prices but 06-20's contract list (first expiry 06-21, none of the 516 contracts expiring 06-17, 1,142 not listed on 06-16), so a relabel would leak contracts first listed on 06-20. The underlying-equals-previous-close check stays as a diagnostic in the quality report. Found in round 2 of the M1 review. | 2026-10-29 |
