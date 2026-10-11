# The demos

There are three demos. All three serve the same interface ([interface.md](interface.md)) over the same engine.

| Demo | Command | What it is |
|---|---|---|
| **Small demo** | `uv run axelrod small_demo` | A blank canvas. The 24 examples build a world model from nothing, one feature at a time. Start here. |
| **Production demo** | `uv run axelrod prod_demo` | The same 24 examples in the oil-shock world, after three years of synthetic history, with a deeper hierarchy: superentities of superentities, three levels deep (Global tightening › Stagflation squeeze › Energy price shock; Tech decoupling › Semiconductor complex › AI chip supply chain; Oil to airlines) |
| **Full demo** | `uv run axelrod demo` | The oil-shock scenario: 53 real actors and ideas and 18 scripted steps. The [hosted demo](deployment.md) runs this one. |

The small and production demos serve http://127.0.0.1:8765. The full demo serves http://127.0.0.1:8000 unless you pass `--port`.

## The examples (small and production demos)

```bash
uv run axelrod small_demo              # a blank canvas
uv run axelrod small_demo 9            # open at example 9: examples 1–8 are played first, and 9 waits for review
uv run axelrod prod_demo ripple        # an example's id works as well as its number
uv run axelrod small_demo --list       # the examples, and how many "more like this" events each has
uv run axelrod small_demo --headless   # every example's review, printed in the terminal
```

**Examples** (`E`) in the top bar lists 24 examples. Most show one feature of the framework through one or more sample articles. Two show a backend user adding what they know with no article at all. Each title names the idea it tests, for example "Analogy: a new shock recalls an old one".

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
