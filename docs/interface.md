# The interface

The first screen is the graph, a caption, and one row of controls. Everything else opens on demand, and `Esc` closes the top thing. Press `?` in the demo for every shortcut; [the table at the end](#shortcuts) lists them too.

<!-- toc -->
**Contents**

- [Two views](#two-views)
- [The top bar](#the-top-bar)
- [The canvas](#the-canvas)
- [The bottom bar](#the-bottom-bar)
- [Panels](#panels)
- [Shortcuts](#shortcuts)
<!-- /toc -->

## Two views

**Learn** and **Predict** (top left) are two views of the same model. They differ only in their controls.

- **Learn** is for backend users, who update the model. Every change is staged, reviewed, and committed.
- **Predict** is for everyone else. It hides everything that learns, and **Ask** becomes the main action. Nothing done in Predict is learned. Predict opens on a blank canvas: a forecast brings forward the actors and ideas it reaches, each value showing the forecast's effect (in italics), and **Show the whole model** shows the rest. Going back to Learn closes Predict's windows.

**When a forecast lands** (Predict), one thing takes the stage: the transmission path, as the [transmission grid](#panels), with the canvas isolated under it, and the **Forecast** panel on the right. Nothing else opens by itself. One small prompt, **Feel free to view the brief**, offers the brief and goes away on its own after a few seconds. The guide stays out of forecasts in Predict, where it would compete with the grid; it still walks a first forecast in Learn.

## The top bar

The bar shows only what the moment needs. Left to right:

| Control | What it does |
|---|---|
| **Demo menu** (beside the name) | Switch the running server to the small, production, full, Emily's, or Sally's demo. A demo comes back as you left it, and the first open of a demo shows its progress ([demos.md](demos.md#switching-demos)). |
| **Learn / Predict** | Switch views |
| Date and `v` number | The simulated date and the state version. The version goes up by one with each commit. |
| **Import** (`I`) | In a model fed by imports (Emily's and Sally's demos): bring in a bundle of research, each item reviewed on its date. When the bundles are one per day, **Next day** and **Any day…** pick them; the file picker takes several days at once ([demos.md](demos.md#sallys-demo)) |
| **Tutorial** (`E`) | In the small and production demos: the chain of examples, each with its articles and **More like this** ([demos.md](demos.md)). In Emily's demo it opens the small demo, with **Back to your model** |
| **Update** (`U`), **Step ▸** (`→`), **Play** (`Space`) | In the full demo: read news and data up to a date, or follow the scripted story |
| **How it works** (`H`) | Learning and inference, each stage with its flowchart; the literature review; the implementation and every component's contract |
| **Transmission** (`G`) | Appears when a staged review has a ripple, or a forecast has paths: opens and closes the transmission grid |
| **Briefs** (`B`, Predict) | Appears once a forecast has a brief |
| **Ask** (`Q`, Predict) | Pose a thesis: a what-if question |
| **Review** | Appears when something waits. Opens the staged review ([demos.md](demos.md#the-review)). |
| **☰** | Everything else: News, Briefs, Add from your own knowledge, Ask a what-if, Checks, Long-term memory, the Console, Admin and settings, Keyboard shortcuts |

In Predict, the caption shows only when it is about a question; a Learn example's caption stays in Learn.

**Notifications.** A toast appears for an error, for work that finished out of sight (an update, with its **Report**), or for a result nothing else on screen shows. A forecast makes no toast (see [when a forecast lands](#two-views)). Tips that explain a view or a shortcut show once per browser. A toast that repeats one still on screen is dropped, and at most two show at once. The first-visit hint sits above the canvas controls, never over them, and goes after the first click, zoom, or pan, or after 20 seconds.

## The canvas

**Nodes.** An entity is a pill. Open it (double-click) to see its subentities as rows, each with a small picture of its distribution and its mean, both in the value's own unit ("3.88%", "¥156.0 per $", "$109.7bn/yr"). The move from normal, in sd, is in the hover card. In Predict, a value a forecast reaches shows the forecast's move instead, in its unit where it can (a percent change for a value that moves in logs, a change in points for a rate). Anywhere a subentity appears away from its entity (a tooltip, the review, find, checks, a forecast), it is named with its entity, as in "Tokio Marine · share price". Superentities are not drawn on the canvas (Oct 17); they stay in the model, in long-term memory, in forecasts, and in the panels (the inspector, Admin › Map, find).

**Interacting with nodes.** Hover to see what something is, click to inspect it, double-click to open it, and right-click for every option. In Learn, right-click offers **Group into a superentity** and **Retire** for entities and interactions; a superentity's inspector offers **Dissolve…**. Each is staged and waits for review. **Draw** (`D`) proposes an edge: drag from one node to another. A subentity gives a concrete end; an entity gives an abstract end that intake refines.

**Layout.** The gravity layout places the graph by the static taxonomy's concepts: each concept (Actor, Firm, Bank) is an undrawn region, narrower concepts are regions inside it, and inside a region causes sit left of their effects, ordered so links cross as little as possible. So banks sit with banks and economies with economies. Nothing overlaps. Regions are packed into a block shaped like the screen. Later changes keep everything near its place.

**Zoom, like a map.** The first view shows the whole graph, every entity closed. Past a threshold, the few entities near the middle of the view open into their values. The threshold is learned: opening an entity by hand while zoomed further out lowers it, and closing one raises it. The wheel and the trackpad glide toward a target zoom about the cursor. The **zoom slider** (bottom right) is logarithmic; its round ticks are the zooms you keep settling at (learned in this browser for each world), and clicking one returns to what you looked at there. The slider is one color; Admin › Settings can color it by what each zoom shows. `F` fits everything. While the view moves, nothing under the still cursor pops a tooltip or dims the rest; an interaction's label keeps its place, and a hidden one returns only once it has had room for a moment; values wipe in at full strength as an entity opens. Zooming and panning are buffered, like map tiles: while the view moves, the drawing already on screen slides and scales as one layer, and the graph is redrawn once when the view rests (or sooner, if the drawing has been scaled far enough to blur). A layout still settling holds still while the view moves. Changes of detail wait until the view rests, so a zoomed-in view pans smoothly.

**Detail.** The **Entities · Subentities** buttons (`1 2`) close or open every entity. **Outlines.** Each entity's outline is its concept in long-term memory (a central bank, a bank, an insurer, a yield curve): each concept has a hue of its own, and institutions (central banks and companies) have a heavier line. The color key lists the concepts in the world. **Auto** (`0`) turns detail-follows-zoom back on. An entity that opens makes room where it is: what lies beneath it moves down and what sits beside it moves aside, so open entities never overlap; everything else stays where it was.

**Isolate** (`X`, or right-click › Isolate). Shows only what drives the selected entity and what it moves, up to a chosen number of interactions away, laid out on its own with their values open. The banner switches between both directions, drivers only, and effects only, and **Show all** (or `Esc`) brings back the full graph where it was.

**Open nodes.** Every node carries an empty dashed node: what the graph does not explain yet. For a value, it is the share of its recent movement that no interaction explains. For a concept in long-term memory, it is the chance that the next item belongs to a concept not seen yet. Larger rings are blind spots.

**Find** (`/` or `⌘K`). A semantic filter over entities, values, interactions, and superentities. It takes words ("airline", "rates") and filters ("moved", "open>0.8", "learned", "kind:company"), and can widen to neighbors one and two hops out.

**Levels** (`[` and `]`). The path at the top left names the taxonomy's levels: World › Actor › Firm › Bank › AIB Group. The world lists the top concepts; a concept frames its entities, with its narrower concepts and entities as chips. `[` goes up a level; `]` goes down into the first chip.

**Color** (`K`). Colors pills by one question at a time (change, blind spots, or category) and holds the key.

**The lens.** The hover card is a small picture of what the cursor is on.

**Undo and redo** (`⌘Z`, `⇧⌘Z`) apply to view changes: opening, closing, moving, and layout. They never undo a commit.

## The bottom bar

- **The phase** (bottom left) names what the model is doing now. Click it for the pipeline of learning and inference phases.
- **The timeline** has three lanes: news, checks, and commits. In the checks lane, a day's mark is filled if its checks passed and hollow if one failed.
- **The scrubber.** Drag it back to see the model as it was on that day, read-only. **Back to live** returns. `⇧←` and `⇧→` step through it.

## Panels

| Panel | Opens with | What it holds |
|---|---|---|
| **Review** | Review, top bar | The staged review of each waiting change: approve all, some, or none (`A` and `R` approve or reject the focused proposal) |
| **News** | ☰ or `N` | The news and data the model has read |
| **Briefs** | ☰, `B`, or the prompt after a forecast | A concise reading of each forecast: the **Summary** (the two largest expected moves with their 90% intervals, and the base case's scenario weight); **Transmission path**, which points to the canvas (opening a brief lays its path out there; **Show on the canvas** does it again, **As a grid** opens the grid); **Expected timing** as a table (onset → value → peak effect → order and channel); **Exposures**; **Indicators and risks to the view**; **Evidence and subsequent developments**, folded; and **Caveats and assumptions**. **✎ Note** adds a note to any section or timeline line. Notes are kept with the forecast on the server and logged in the ledger as records that change no state, so inference never learns from them. **Edit** reopens Ask with the thesis filled in; **Re-run** poses it again at the latest committed version. Every run of a thesis stays one click away (**runs #1 #2**). |
| **Transmission path on the canvas** | A forecast, or opening its brief | The forecast's path drawn on the canvas in place of the model, laid out as the grid is: the shock on the left, one column per order, the outputs on the right. The values the shock reaches are shown, as chips under their entities' names, each with its peak effect in the value's unit (sd in its title): the relevant ones, the values between them, and where their chains carry on, up to 28 values, joined by the interactions among them (green a positive link, red a negative one, thicker the stronger). Hovering a chip lights its links; clicking it inspects it. An output that drives another output moves to a **Downstream outputs** column, and the link between them is dashed. **As a grid** opens the grid; **Show the whole model** (or `Esc`) brings the model back. |
| **Inspect** | Click a node | The node's values, evidence, and history |
| **Ask, Forecast** | `Q` | Pose a thesis; forecast values, actors, sectors, superentities, or categories, by order and path. Each forecast card draws the outcome at the horizon twice on one axis: **without** the shock (the baseline) above, **with** it below, medians ticked and the shift between them marked, beside the effect's fan over time. **Brief**, **Edit**, **Re-run**, and **Agent context** sit under the question. With a watchlist, the panel opens on **Scenarios for the book**: bull, base, and bear bands of the forecast's draws, with the names each favors and hurts, its mechanism, and what would change the read ([demos.md](demos.md#sallys-demo)). |
| **Agent context** | **Agent context**, on a forecast | The world model as context for a client's agents, in their own world-model format: the card it fills (Scenarios & conviction) beside the pack (manifest, domain pack, baseline, decision context), which card reads which part, and **Download** |
| **Export the world model** | ☰ (Learn) | The world model as it stands now, at the latest committed version, in the same format without a forecast: the 036 domain pack, its 020 registry entry, and the current state as an evidence pack, with its version and state hash, counts, its strongest relationships, and the open questions it passes on. **Download** saves one file (named with its date and version); **As files** saves each part under the file name the agents' load order expects (`036_world_model_domain_pack_…_v4.1.4.json`, `evidence_pack_axelrod_…json`, `020_registry_entry_036_…json`) and the manifest. `GET /api/context/v4` |
| **Hypotheses** | Right panel tab | The hypothesis frontier: hypotheses about interactions and about entities' decisions, sorted by informational value. Each can be marked supported or refuted, and decision hypotheses can be posed as theses. |
| **Decisions** | Right panel tab | Recorded decisions with the forecasts they cite. **Resolve** scores a decision once its review date passes. |
| **Checks** | ☰ or `C` | What the model is testing now (fuzzy ends, co-movements, candidate superentities), each with its progress toward its bound; and when each kind of check runs, how it works, and exactly what it updates |
| **Long-term memory** | ☰ or `M` | A drawer with five tabs: object generalizations, interaction generalizations, entity memories, the correlation frontier, and prior states |
| **Console** | ☰ or `I` (Learn) | The commit log: every commit (process, memory, who vetted it), one commit, a diff, or an old version |
| **Transmission grid** | Opens with each review that has a ripple (Admin › Settings turns this off); for a forecast, **As a grid** or `G` | Only what is relevant to a shock, as a grid. Columns are the input, each order the shock reaches (as deep as its effects matter), and the output; rows are entities, ordered so links cross as little as possible. Each value's effect moves day by day, with its band, and each interaction lights once the effect reaches its source. The default, **Relevant**, keeps what carries the most effect, counting each further order 40% less, so a distant effect shows only if it is strong; the output column holds where each kept chain ends, tagged with its order. An asked-about value that the grid follows further stays in its order's column, tagged and in bold, so every link runs left to right. While the grid is open, the canvas isolates its entities and places them the way the grid does (each in the column where it is first reached), with the grid's interactions lit, framed in the room below the grid; **Isolated on the canvas** switches that off, and closing the grid brings the whole graph back. The grid sits between the open side panels when about 900px fit, and covers the left one otherwise. Four more views: by order, the largest effects, toward the outputs, and the strongest paths. |
| **Walkthrough** | `W` | How the model learned the latest news, or inferred the latest answer, step by step. Each step frames what it touched; `←` and `→` move between steps. |
| **Admin and settings** | ☰ or `,` | Story (every scripted step), Map (the categories, superentities, actors, and the key of symbols), View, and Settings |
| **Reset to the original demo** | ☰ | Every demo under this login back to its original state (imports, reviews, forecasts, briefs, and notes cleared), and the login's first demo served again. Everyone signed in with the login sees the reset. `POST /api/sim/reset-all` |

Side panels can be enlarged to full screen (⤢) and closed (✕).

**Motion.** Movement is quick, between 150 and 350 ms. Side panels slide in from their own side and fade, and so do menus and windows. Toasts rise in and fall away, and a count that changes bumps once. Items new to a list (review sections, news, examples, find results, checks) come in one after another, and a list redrawn with the same items doesn't animate again. Switching between Learn and Predict crossfades the bar's controls and the canvas. On the canvas, nodes and interactions draw in as they appear. Nothing animates while the view moves. The system's reduced-motion setting, or Admin › Settings › Reduced motion, turns all of this off.

**The guide** is a small red panda. The first time the model forecasts or reads news, it hops to whatever the model is working on and says what it does ([Admin › Settings](#panels) turns it off).

## Shortcuts

| Group | Keys |
|---|---|
| Canvas | `X` isolate the selection · `⌘Z` undo a view change · `⇧⌘Z` redo · `1 2` entities, subentities · `0` Auto · `K` color · `[ ]` levels · `+ − F` zoom and fit · `/` or `⌘K` find · `D` draw · `Esc` close the top thing |
| Demo | `E` examples · `→` next scripted step · `Space` play or pause · `⇧← ⇧→` step through the timeline · `U` request an update |
| Walkthrough | `W` open · `← →` previous and next step |
| Panels | `I` console · `N` news · `B` briefs · `Q` ask · `M` long-term memory · `C` checks · `G` transmission grid · `H` how it works · `,` admin · `A R` approve or reject · `?` every shortcut |

On Windows and Linux, `Ctrl` replaces `⌘`, and redo is `Ctrl-Y`.
