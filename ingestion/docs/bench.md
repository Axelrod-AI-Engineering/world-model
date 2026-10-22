# The ingestion benchmark

How ingestion is measured on a corpus: speed per stage, and extraction against a gold set. The scoring code is
`ingestion/src/axelrod_ingest/bench.py`; the runner is `ingestion/scripts/ingest_bench.py`. A client's corpus, gold set,
and reports stay in that client's gitignored folder under `data/`.

<!-- toc -->
**Contents**

- [What it measures](#what-it-measures)
- [Guarding against overfitting](#guarding-against-overfitting)
- [Results](#results)
<!-- /toc -->

## What it measures

Two things, the way uploads arrive (each file's bytes and name, nothing else).

**Speed, per stage.** Every result carries seconds per stage (`IngestResult.timings`: store, parse, chunk, index,
embed, extract, llm, bundle). The report gives each stage's total, share, mean, p50, and p95, and throughput in
documents, pages, and megabytes per second.

**Extraction, against a gold set.** A gold signal is a claim a careful reader took from one source file. It is
annotated with the file, the page, the verbatim evidence, a verdict (supported or partly), and where it lives:

- a sentence or a table row, which counts toward recall;
- an inference across sentences or a chart, which is reported but not counted.

A prediction agrees with a gold signal from the same file in these cases:

| Gold signal | Agrees when |
|---|---|
| Observe | Same value, level within 2% or 0.05 |
| Move | Same value, same direction |
| Support or link | Same two ends |

The report gives these measures:

- **Recall**, overall, by signal type, and by verdict.
- **Located**: the right value was found, however it was read.
- **Precision**: from gold matches plus a labels file, since the gold set is a selection, not every claim.
- **Misses**, each with what was read instead.

## Guarding against overfitting

Documents are split by the hash of their path:

| Split | Share | Use |
|---|---|---|
| dev | two thirds | For tuning |
| test | one third | For checking (`--split`) |

A blind set, annotated independently from documents the gold never used, gives the final number. The first round of
tuning showed why: recall on the tuning split rose threefold while the held-out split did not move.

```bash
uv run python ingestion/scripts/ingest_bench.py --corpus data/<client>_data --world-view <world_view.json> --dirs <folders> \
    --items <gold items folder> --gold <gold annotations> --labels <labels> --split dev --out data/<client>_data/bench/run
```

## Results

**Results on the first client corpus (Oct 17, aggregates only).**

| Set | Recall | What it measures |
|---|---|---|
| Gold, dev split | 49% | the tuning split |
| Gold, test split | 44% | held out from the first tuning round |
| Blind half A | 79% | tuned on in the third round, so no longer a held-out measure |
| Blind half B | 35% (6 of 17) | the final number; never tuned on |

On half B, observed levels read from tables are recalled two times in three. Causal claims (links, support, and moves)
were not recalled at all. Every prediction that matched a labelled claim was correct, and there were no false
positives on negative controls. Precision is measured separately, on the gold files (below).

**A round on causal claims (Oct 18).** The rules above for connectors, sectors, bare yields, entity ends, and reported
channels were written from sentence structure, with invented test sentences, and checked on the gold set: recall did
not move on either split (49% dev, 44% test), because the gold's causal claims mostly sit in sentences that name their
ends by words the model has no name for, or are the annotator's inference. The round added 10 predictions across both
splits (9 judged correct by hand; the error is a past episode's move read as current), and none on negative controls.
Its effect is for the next blind set to show.

**Precision, now measured (Oct 18).** An independent labeler judged every prediction on the 67 gold files (a
prediction is correct when the document states it, with the right value and basis, the right direction, and as a
current level, neither past nor forecast). Precision was 61% (dev 62%, test 58%). The incorrect ones were mostly
forecasts or guidance read as observations (about half), a value or entity taken wrongly (a quarter: a peer's figure
on the next line, one component for an aggregate, a check row or a share row of a workbook), and history read as
current. A round of rules, tuned on the dev split only, raised precision without losing a gold match on either split:

| Split | Recall | Predicted | Precision (shared labels) | Precision (with the new predictions labelled too) |
|---|---|---|---|---|
| dev, before | 49% (48 of 98) | 138 | 62% | 62% |
| dev, after | 50% (49 of 98) | 102 | 90% (6 unlabelled) | 87% |
| test, before | 44% (19 of 43) | 74 | 58% | 58% |
| test, after | 44% (19 of 43) | 62 | 77% (6 unlabelled) | 76% |

The rules:

- **An observation is a reported current level.** A level is read in the latest actual column, never an estimate
  column ("9/26E", "2027E"), never a year-end half a year before the document (a later quarter has been reported), and
  a market price only on a date or a "Current" column (not at a quarter's end or as a fiscal year's average).
- **A workbook's model is not a report.** A row's columns from its first computed figure on (decimals after whole
  numbers) are a projection; a year at least half reported is still read, with less confidence than a figure stated
  for the year. Check rows ("A = B"), rows of zeros, share rows ("mix, %"), a balance repeated in its year's column, a
  value named only in a label's parenthetical, and a level whose figures run past the dated columns are not read.
- **A forecast is not a move.** Previews ("is seen up", "incoming"), base cases, projections, the market's pricing of
  moves to come, assumptions ("based on"), another's expectation or guidance ("management expects", "guided to"),
  predictions ("will grow by 13%"), and changes over estimated years are no claim, read in the mention's own part of
  the sentence (up to a semicolon or a sub-bullet). A revision of a forecast or of guidance (from A to B, "raised our
  forecasts") is news and stays a move.
- **The right value.** A value named without its entity is not taken after an acronym the model does not know on the
  same line (another bank's ticker, another central bank), nor after "its" when the last sentence named a stranger
  in the possessive. A part in a list of labelled parts that moved both ways is not the whole; a figure stripped of
  something is on another basis; a value as the object of someone's aim ("buybacks to improve returns") does not move.
- **The right period and direction.** A quarter's sequential change does not move a year's flow, nor does a month's
  print or a sequential change move a year-on-year rate; a pause ("unchanged", "on hold") is no move; a flow's figure
  after its change ("rose 16% to ¥22bn") is a period's result unless the year is named; an uncalibrated link is
  supported or contradicted by the sign its mechanism states.
- **History and scenarios.** Bullets under a scenario's heading ("Upside Scenario") are supposed until prose resumes;
  an episode dated by day and month only, right after a sentence about an earlier year, is history; so are "past
  episodes".

What remains is mostly a disagreement between the gold and the labeler, not a reading error: the gold takes a
current fiscal year's estimate of an annual figure (a research table's "03/27E" column, a workbook's forward row, a
year the model completes) as the value's level, while the labeler calls the same reading a forecast. The rules keep
those readings, so as not to lose gold matches; reading them strictly would raise precision further and lower recall.

Half B was partly exposed before scoring: a bench run read three of its files and showed some predicted values to the
tuner, although no rule was tuned on them. Without those files, half B has only 6 claims, too few to report on their
own. The next blind set should be annotated from fresh documents, and runs should name their files explicitly
(`--files`), never whole folders.

A client's corpus, gold, and reports stay in that client's gitignored folder. The scoring is tested on invented
examples (`ingestion/tests/ingest/test_bench.py`).

