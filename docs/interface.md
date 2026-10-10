# The interface

The first screen is the graph, a caption, and one row of controls. Everything else opens on demand, and `Esc` closes the top thing. Press `?` in the demo for every shortcut; [the table at the end](#shortcuts) lists them too.

## Two views

**Learn** and **Predict** (top left) are two views of the same model. They differ only in their controls.

- **Learn** is for backend users, who update the model. Every change is staged, reviewed, and committed.
- **Predict** is for everyone else. It hides everything that learns, and **Ask** becomes the main action. Nothing done in Predict is learned.

## The top bar

The bar shows only what the moment needs. Left to right:

| Control | What it does |
|---|---|
| **Learn / Predict** | Switch views |
| Date and `v` number | The simulated date and the state version. The version goes up by one with each commit. |
| **Examples** (`E`) | In the small and production demos: the chain of examples, each with its articles and **More like this** ([demos.md](demos.md)) |
| **Update** (`U`), **Step ▸** (`→`), **Play** (`Space`) | In the full demo: read news and data up to a date, or follow the scripted story |
| **How it works** (`H`) | Learning and inference, each stage with its flowchart; the literature review; the implementation and every component's contract |
| **Ask** (`Q`, Predict) | Pose a thesis: a what-if question |
| **Review** | Appears when something waits. Opens the staged review ([demos.md](demos.md#the-review)). |
| **☰** | Everything else: News, Briefs, Add from your own knowledge, Ask a what-if, Checks, Long-term memory, the Console, Admin and settings, Keyboard shortcuts |

## The canvas

**Nodes.** An entity is a pill. Open it (double-click) to see its subentities as rows, each with a distribution glyph and its latest move. Superentities are outlines around their members, with a tab naming them. Closed, they become cards.

**Interacting with nodes.** Hover to see what something is, click to inspect it, double-click to open it, and right-click for every option. In Learn, right-click offers **Group into a superentity**, **Dissolve it**, and **Retire** for entities and interactions. Each is staged and waits for review. **Draw** (`D`) proposes an edge: drag from one node to another. A subentity gives a concrete end; an entity or a superentity gives an abstract end that intake refines.

**Detail.** The **Superentities · Entities · Subentities** buttons (`1 2 3`) set how much is open. With **Auto** (`0`) on, detail follows zoom: zoomed out, superentities close into cards; zoomed in, the entities in view open into their values. `+`, `−`, and `F` zoom in, zoom out, and fit.

**Open nodes.** Every node carries an empty dashed node: what the graph does not explain yet. For a value, it is the share of its recent movement that no interaction explains. For a kind in long-term memory, it is the chance that the next item is a kind not seen yet. Larger rings are blind spots.

**Find** (`/` or `⌘K`). A semantic filter over entities, values, interactions, and superentities. It takes words ("airline", "rates") and filters ("moved", "open>0.8", "learned", "kind:company"), and can widen to neighbors one and two hops out.

**Levels** (`[` and `]`). The path above the canvas names each level of superentities within superentities. `[` goes up a level; `]` goes down into the first part. Example 20 nests two superentities.

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
| **Briefs** | ☰ or `B` | A written reading of each forecast |
| **Inspect** | Click a node | The node's values, evidence, and history |
| **Ask, Forecast** | `Q` | Pose a thesis; forecast values, actors, sectors, superentities, or categories, by order and path |
| **Hypotheses** | Right panel tab | The hypothesis frontier: hypotheses about interactions and about entities' decisions, sorted by informational value. Each can be marked supported or refuted, and decision hypotheses can be posed as theses. |
| **Decisions** | Right panel tab | Recorded decisions with the forecasts they cite. **Resolve** scores a decision once its review date passes. |
| **Checks** | ☰ or `C` | What the model is testing now (fuzzy ends, co-movements, candidate superentities), each with its progress toward its bound; and when each kind of check runs, how it works, and exactly what it updates |
| **Long-term memory** | ☰ or `M` | A drawer with five tabs: object generalizations, interaction generalizations, entity memories, the correlation frontier, and prior states |
| **Console** | ☰ or `I` (Learn) | The commit log: every commit (process, memory, who vetted it), one commit, a diff, or an old version |
| **Walkthrough** | `W` | How the model learned the latest news, or inferred the latest answer, step by step. Each step frames what it touched; `←` and `→` move between steps. |
| **Admin and settings** | ☰ or `,` | Story (every scripted step), Map (the categories, superentities, actors, and the key of symbols), View, and Settings |

Side panels can be enlarged to full screen (⤢) and closed (✕).

## Shortcuts

| Group | Keys |
|---|---|
| Canvas | `⌘Z` undo a view change · `⇧⌘Z` redo · `1 2 3` superentities, entities, subentities · `0` Auto · `K` color · `[ ]` levels · `+ − F` zoom and fit · `/` or `⌘K` find · `D` draw · `Esc` close the top thing |
| Demo | `E` examples · `→` next scripted step · `Space` play or pause · `⇧← ⇧→` step through the timeline · `U` request an update |
| Walkthrough | `W` open · `← →` previous and next step |
| Panels | `I` console · `N` news · `B` briefs · `Q` ask · `M` long-term memory · `C` checks · `H` how it works · `,` admin · `A R` approve or reject · `?` every shortcut |

On Windows and Linux, `Ctrl` replaces `⌘`, and redo is `Ctrl-Y`.
