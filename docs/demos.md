# The demos

There are four demos. All four serve the same interface ([interface.md](interface.md)) over the same engine.

| Demo | Command | What it is |
|---|---|---|
| **Small demo** | `uv run axelrod small_demo` | A blank canvas. The 24 examples build a world model from nothing, one feature at a time. Start here. |
| **Production demo** | `uv run axelrod prod_demo` | The same 24 examples in the oil-shock world, after three years of synthetic history, with a deeper hierarchy: superentities of superentities, three levels deep (Global tightening › Stagflation squeeze › Energy price shock; Tech decoupling › Semiconductor complex › AI chip supply chain; Oil to airlines) |
| **Full demo** | `uv run axelrod demo` | The oil-shock scenario: 53 real actors and ideas and 18 scripted steps. The [hosted demo](deployment.md) runs this one. |
| **Emily's demo** | `uv run axelrod demo --scenario emily_demo` | The ordinary use case: a PM's world model brought up to date by importing research, then forecasts of her book. See [below](#emilys-demo). |

The small and production demos serve http://127.0.0.1:8765. The full demo serves http://127.0.0.1:8000 unless you pass `--port`.

## Switching demos

You don't need to restart the server to change demos. The **demo menu** beside the name in the top bar lists all four. Choosing one switches the running server to it, and the page reloads into the new demo.

- **A demo opened before comes back as you left it**, with its reviews, examples, and versions. Each demo keeps its own storage (next to the first one's, for example `var/axelrod/demo-prod_demo`) and its own trace stream. To start a demo over, use **Reset**, or Admin › Scenario.
- **A demo opened for the first time is built in the background.** The demo you're on keeps working, and a card under the menu shows the progress. The production and full demos replay three years of synthetic history the first time they open on a machine, which takes about two and a half minutes. The card counts the days as they're replayed, and the menu marks those demos *First open replays its history: a few minutes*. After that the history is cached in `var/oil_shock_demo/` (the two demos share it), and opening either one takes seconds.
- **On the hosted demo, each login switches only its own engine.** Switching under Emily's login never changes what the main login sees, and the other way round. `WORLD_MODEL_SCENARIO` and `WORLD_MODEL_LOGINS` still choose the demo each login opens on ([deployment.md](deployment.md)).
- **In Emily's demo, Tutorial** switches to the small demo and opens its examples. **Back to your model** switches back, and her model is as she left it.

The API behind the menu: `GET /api/demos` returns the demos, the current one, and the switch under way (its phase and, during the history replay, the days done). `POST /api/demos/{id}` switches. Every page on the same engine receives a `switched` message on `/ws` and reloads. `POST /api/sim/load` still reloads a demo from its start.

## Emily's demo

What an ordinary week with the product looks like for a cross-asset PM. The model starts with her view of the chain (oil → inflation and growth → the Fed and the BoJ → the US–Japan rate gap → USD/JPY → her names: Tokio Marine, Zurich, Toyota, Komatsu, SoftBank Corp, JPMorgan, Citi, Morgan Stanley, UniCredit), in six superentities. It has no synthetic history.

1. **Import** (`I`, Learn) opens a bundle: research a collection agent has read and categorized, as dated items. Choose a JSON file, or one from the server's imports folder when it has one. The dialog shows the items as a timeline by day, with each item's source, category, relevance, and what it would change (a level, a move, a new link, or evidence for or against one), and what does not map onto the model.
2. **Importing** folds the chosen items in on their own dates through one update, which stops at each item for review, oldest first. The review highlights the phrases each change comes from. When the last one is decided, the caption says the model is up to date.
3. **Predict** opens on a blank canvas. Ask a question, or pick one of her four ready-made scenarios (from her Fed-versus-BoJ table and her yen simulator). The forecast brings forward only what it reaches, with the forecast's effect on each value; **Show the whole model** shows everything, as of the version the forecast used.
4. **Tutorial** opens the small demo in place of the model, and **Back to your model** returns.

The bundle format (`axelrod.import/v1`) is in `src/axelrod_wm/intake/bundle.py`; a synthetic sample is `tests/fixtures/import_bundle_sample.json`. Emily's own bundle is built from client research and lives in `data/emily_data/`, which is never committed or uploaded: on the hosted demo, import it with the file picker.

## The tutorial (small and production demos)

```bash
uv run axelrod small_demo              # a blank canvas
uv run axelrod small_demo 9            # open at example 9: examples 1–8 are played first, and 9 waits for review
uv run axelrod prod_demo ripple        # an example's id works as well as its number
uv run axelrod small_demo --list       # the examples, and how many "more like this" events each has
uv run axelrod small_demo --headless   # every example's review, printed in the terminal
```

**Tutorial** (`E`) in the top bar lists 24 steps, called examples below. Most show one feature of the framework through one or more sample articles. Two show a backend user adding what they know with no article at all. Each title names the idea it tests, for example "Analogy: a new shock recalls an old one".

| Memory | Examples |
|---|---|
| Working memory | 1 create an entity · 2 links inside an entity · 4 a shock and its ripple, by order · 7 an observation teaches an effect · 14 evidence weakens a link · 23 delete a link |
| Your own knowledge (no article) | 5 add an entity, its value, and an interaction from experience · 9 connect your idea to the rest, at half confidence (example 10's ripple then runs through it) |
| Intake | 3 a fuzzy mention, refined to one value · 12 an ambiguous mention stays fuzzy |
| Long-term memory | 8 a new member inherits its kind's priors · 10 an actor's decision goes into its entity memory · 11 a later shock recalls an earlier one · 13 later evidence settles a fuzzy end · 15 a recurring group is proposed as a superentity · 16 a correlation gains strength · 17 a co-movement is proposed as a link · 18 a crowded kind splits · 19 collapse · 20 nest two superentities in one · 21 expand · 22 delete a superentity the model provided |
| Review | 6 many new items: keep only some |
| Inference | 24 a what-if question |

How the examples run:

- **They form one chain.** Running example *n* plays examples 1 to *n* − 1 first. Running an earlier example rewinds to it and replays the decisions you made on the earlier ones.
- **More like this.** Under an example, **More like this** adds further articles of the same kind to the current state.
- **Every example stops at Review.** Nothing in either memory changes until you approve. [The review](#the-review) explains what it shows.

The examples, their articles, and the "more like this" events are in `src/axelrod_wm/sim/examples/`.

## The full demo

```bash
uv run axelrod demo --port 8765
```

In the full demo, **Update** (`U`) reads news and data up to a date, and **Step ▸** (`→`) and **Play** (`Space`) follow the scripted story. A run pauses whenever something needs review. The first start replays three years of synthetic history (about two and a half minutes) and caches it in `var/oil_shock_demo/`. Later starts take a few seconds. The cache rebuilds itself when the data, config, or engine code changes.

## The review

Every change that needs a person is staged first: the event's whole learning runs on a copy of the model, and **Review** shows everything the copy would commit. It is grouped by stage, each in its stage's color:

- **Intake:** the article, with the phrases that asked for each change marked.
- **Working memory:** every change, with one checkbox each; what recall brought back; the ripple, by order and path; what the fold learns. Each value's ripple can be deselected or given the probability that it arrives.
- **Long-term memory:** what it learns, and any proposals it raises.
- **Your review:** approve all, some, or none. Deselecting a change stages the event again without it.

While a review is open, the canvas shows the staged graph. Staged items have a dashed outline, retired ones a red outline, and moved values are tinted by order. A banner at the bottom of the canvas holds the key.

Three more inputs feed the review:

- **Your confidence.** A slider sets your confidence in the article (100% takes it as stated), and any change can have its own. It goes into the data the approval writes: an interaction's existence and evidence, a report's weight, a move's expected size, and a record on each new entity and value.
- **Your own knowledge.** ☰ → **Add from your own knowledge** opens a form for an entity, its values (a typical level and spread set the prior), interactions (sign, size, timing), why you believe it, and your confidence. It is staged and reviewed like an article. Your reason is kept as the evidence on what it adds. Examples 5 and 9 open it prefilled.
- **Fuzzy ends stay fuzzy.** A mention binds only when the article names its target. Otherwise it is hedged across its candidates, with a share for one not in the graph yet, and drawn as soft interactions as strong as they are probable. Later articles move the odds, and a resolution comes back for review once one candidate passes the bound.
