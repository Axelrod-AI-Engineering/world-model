# Export desk

`axelrod-desk`: upload documents, and out come the world-model files (Nov 2). A small web app and a reader command. People
add documents; the reader reads them with the person's own Claude Code; every figure is checked against its page; copies
of one figure become one fact with all its citations; a person picks the companies, sector groups and source classes; and
a build writes the v4.1.4 upload set, the evaluation export, the corpus and one zip, with the world model's own export
scripts.

<!-- toc -->
**Contents**

- [Run it](#run-it)
- [From document to files](#from-document-to-files)
- [Reading on a Claude plan](#reading-on-a-claude-plan)
- [Duplicates and facts](#duplicates-and-facts)
- [What a build writes](#what-a-build-writes)
- [Settings](#settings)
- [Not yet](#not-yet)
<!-- /toc -->

## Run it

The desk keeps its state in one folder, `DESK_HOME` (default `data/desk`), which holds `desk.toml` ([Settings](#settings))
and is gitignored. Client documents and figures never enter the repository.

```bash
uv sync
DESK_HOME=data/desk uv run axelrod-desk serve --port 8765
```

Open `http://127.0.0.1:8765`. The first visit makes the first admin account; an admin adds the others on the Accounts
page (or `axelrod-desk account EMAIL NAME [--admin]` in a terminal). Then:

1. **Library.** Drop files or a folder. A `MANIFEST.md` in the folder labels its files (publisher, date, section, link)
   and is not itself stored.
2. **Reader.** Make a reader token and run the command the page shows, on a computer with Claude Code signed in:
   `uv run axelrod-desk reader --url http://127.0.0.1:8765 --token TOKEN`. It reads until stopped (`--drain` stops when
   no document is left).
3. **Facts.** Review a company's facts: approve, reject, or leave them. Conflicts can be shown alone.
4. **World models.** Pick companies, sector groups and source classes, set the switch, save, and build. A finished
   build is a zip to download.

The same steps from a terminal: `axelrod-desk add FILE_OR_FOLDER... --as EMAIL [--company ID] [--class CLASS]` and
`axelrod-desk build WORLD_MODEL_ID --as EMAIL`. `axelrod-desk import-records` loads figures read before the desk existed
(the Oct 31 to Nov 2 records files).

## From document to files

```text
add        stored once by SHA-256, page text kept; type, language, dates and period from ingestion's parser;
           company and class detected (or set); copies of one disclosure linked, and only the primary is read
read       the reader claims the oldest unread document of a known company, reads it with Claude Code, and submits
check      every figure again on the desk: kind allowed for the class, metric in the company's catalog, closed period,
           page in range, quote found verbatim on the page, value and unit present, printed figure in the quote
resolve    figures become facts (one per figure, every citation kept, conflicts flagged); people approve or reject
build      the selection's facts beside the base model, bundles, both exports, the corpus, a summary, one zip
```

A document's class decides which kinds it may report: `company` (filings, results, presentations), `sell_side` (broker
notes: the broker's actuals, estimates, revisions, targets, ratings, quoted consensus), and `other`.

## Reading on a Claude plan

The reader is a command that runs on the person's own computer and calls their own Claude Code
(`claude -p --output-format json --json-schema ...`), signed in with their own Claude account. It runs in a temporary
folder that holds only the document's text and the company's catalog, with file-reading tools only (`Read`, `Grep`,
`Glob`; anything else is refused without asking), returns figures in a fixed schema, and is asked again with the
problems the desk found, up to three rounds.

The desk never sees, stores or passes on a Claude sign-in. Anthropic's terms for Claude Code allow a person to use their
own subscription in Claude Code; they do not allow an application to offer Claude sign-in, hold Claude.ai credentials or
session tokens, or route requests through them. The desk's own accounts (email and password, scrypt-hashed) are separate
from Claude, and a reader token (stored hashed) only lets a reader claim and submit documents.

## Duplicates and facts

- **Files.** A file is stored once, by its SHA-256; adding it again records the upload and nothing more.
- **Copies of one disclosure** (the Chinese and English reports of one quarter) are linked by their figures, with
  ingestion's dedupe; the English primary is read and the others are marked copies.
- **Figures.** Figures are grouped by company, metric (or label), period, unit, the class of claim, the speaker (the
  company, or the publishing broker), and, for a view held as of a date (an estimate, target, rating, consensus or
  guidance), that date. Values within 0.5% of each other are one fact with every citation. Different values in one group
  stay apart and are flagged as conflicts. A company's figure and a broker's never merge, and a later note's revised
  estimate is a new view, not a conflict.
- **The base model.** A fact equal to a base model figure adds its documents as further citations of that figure.

## What a build writes

`DESK_HOME/builds/NNNN/`:

| Path | Is |
|---|---|
| `construction/<company>/` | the base construction's `sources.json`, `citations.json` and `repair.json`, with each new fact added beside the baseline as a `DESK_…` observation (never the selected baseline) |
| `bundles/` | one import bundle per included document, dated by its publication |
| `world_model_v4_1_4_axelrod_…/` | the v4.1.4 upload set (`world_model/scripts/imports/export_context.py`) |
| `wm-export.json` | the evaluation export (`world_model/scripts/imports/export_wm.py snapshot`) |
| `corpus.json` | every page of every included document |
| `summary.json`, `*.zip` | what went in and what was held out, and all of it in one file |

**The switch.** Off (the default), new figures travel beside the baseline and the model's estimates do not move. On,
each approved company-reported figure on a metric, in the metric's own unit, is applied to the model when the bundles
are folded. The summary counts each figure that was not applied, with the reason.

## Settings

`DESK_HOME/desk.toml`. Paths may be relative to the file's folder.

| Key | Is |
|---|---|
| `repo` | the checkout whose export scripts run a build |
| `data`, `clients` | `WORLD_MODEL_DATA_DIR` and `WORLD_MODEL_CLIENT_DIR` for those scripts |
| `base_scenario` | the scenario every build narrows (default `unified`) |
| `construction` | the base model's construction: `<company>/sources.json`, `citations.json`, `repair.json` |
| `world_view` | the base scenario's world view (`world_model/scripts/export_world_view.py`): companies, values, links |
| `client_core` | the client's v4.1.4 folder of 000, 010 and 020, copied beside each export (optional) |
| `remaps` | `OLD=NEW` path prefixes that let the exporters find the base construction's documents; `data/` always maps to `data` |
| `[groups]` | named lists of companies, offered beside the sector and focus groups |

## Not yet

- **Hosted.** The desk runs on one machine. Hosting it on dev beside the ingestion service needs the service's variables
  (a Railway admin), and a hosted reader would need Anthropic's agreement first; the local reader works against a hosted
  desk as it does against a local one.
- **Companies without a construction.** A company with no `repair.json` has no baseline; its new figures are held out
  of the construction and reach the model only through the switch.
