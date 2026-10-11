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
| **Transmission** (`G`) | Appears when a staged review has a ripple, or a forecast has paths: opens and closes the transmission grid |
| **Briefs** (`B`, Predict) | Appears once a forecast has a brief |
| **Ask** (`Q`, Predict) | Pose a thesis: a what-if question |
| **Review** | Appears when something waits. Opens the staged review ([demos.md](demos.md#the-review)). |
| **☰** | Everything else: News, Briefs, Add from your own knowledge, Ask a what-if, Checks, Long-term memory, the Console, Admin and settings, Keyboard shortcuts |

In Predict, the caption shows only when it is about a question; a Learn example's caption stays in Learn.

**Notifications.** A toast appears for an error, for work that finished out of sight (an update, with its **Report**), or for a result nothing else on screen shows. Tips that explain a view or a shortcut show once per browser. A toast that repeats one still on screen is dropped, and at most two show at once. The first-visit hint sits above the canvas controls, never over them, and goes after the first click, zoom, or pan, or after 20 seconds.

## The canvas

**Nodes.** An entity is a pill. Open it (double-click) to see its subentities as rows, each with a distribution glyph and its latest move. Superentities are outlines around their members, with a tab naming them. Closed, they become cards.

**Interacting with nodes.** Hover to see what something is, click to inspect it, double-click to open it, and right-click for every option. In Learn, right-click offers **Group into a superentity**, **Dissolve it**, and **Retire** for entities and interactions. Each is staged and waits for review. **Draw** (`D`) proposes an edge: drag from one node to another. A subentity gives a concrete end; an entity or a superentity gives an abstract end that intake refines.

**Layout.** The gravity layout places the graph the way its superentities nest: each superentity is a region, its parts are regions inside it, and inside a region causes sit left of their effects, ordered so links cross as little as possible. Nothing overlaps. Regions are packed into a block shaped like the screen. Later changes keep everything near its place.

**Zoom, like a map.** The first view shows the whole graph, folded to the top of the hierarchy. Zooming in unfolds it a level at a time: superentities of superentities first, then their parts, then the entities. Past a threshold, the few entities near the middle of the view open into their values. The threshold is learned: opening an entity by hand while zoomed further out lowers it, and closing one raises it. The wheel and the trackpad glide toward a target zoom about the cursor. The **zoom slider** (bottom right) is logarithmic; its round ticks are the zooms you keep settling at (learned in this browser for each world), and clicking one returns to what you looked at there. The slider is one color; Admin › Settings can color it by what each zoom shows. `F` fits everything. While the view moves, nothing under the still cursor pops a tooltip or dims the rest; a superentity's tab keeps to its spot and glides when its outline shifts; an interaction's label keeps its place, and a hidden one returns only once it has had room for a moment; values wipe in at full strength as an entity opens. Zooming and panning are buffered, like map tiles: while the view moves, the drawing already on screen slides and scales as one layer, and the graph is redrawn once when the view rests (or sooner, if the drawing has been scaled far enough to blur). A layout still settling holds still while the view moves. Changes of detail wait until the view rests, and only outlines in or near the view are retraced while the layout settles, so a zoomed-in view pans smoothly.

**Detail.** The **Superentities · Entities · Subentities** buttons (`1 2 3`) set how much is open everywhere. **Auto** (`0`) turns detail-follows-zoom back on.

**Isolate** (`X`, or right-click › Isolate). Shows only what drives the selected entity and what it moves, up to a chosen number of interactions away, laid out on its own with their values open. The banner switches between both directions, drivers only, and effects only, and **Show all** (or `Esc`) brings back the full graph where it was.

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
| **Transmission grid** | Opens with each review and forecast that has a ripple (Admin › Settings turns this off); **As a grid**, or `G` | Only what is relevant to a shock, as a grid. Columns are the input, each order the shock reaches (as deep as its effects matter), and the output; rows are entities, ordered so links cross as little as possible. Each value's effect moves day by day, with its band, and each interaction lights once the effect reaches its source. The default, **Relevant**, keeps what carries the most effect, counting each further order 40% less, so a distant effect shows only if it is strong; the output column holds where each kept chain ends, tagged with its order. An asked-about value that the grid follows further stays in its order's column, tagged and in bold, so every link runs left to right. While the grid is open, the canvas isolates its entities and places them the way the grid does (each in the column where it is first reached), with the grid's interactions lit, framed in the room below the grid; **Isolated on the canvas** switches that off, and closing the grid brings the whole graph back. The grid sits between the open side panels when about 900px fit, and covers the left one otherwise. Four more views: by order, the largest effects, toward the outputs, and the strongest paths. |
| **Walkthrough** | `W` | How the model learned the latest news, or inferred the latest answer, step by step. Each step frames what it touched; `←` and `→` move between steps. |
| **Admin and settings** | ☰ or `,` | Story (every scripted step), Map (the categories, superentities, actors, and the key of symbols), View, and Settings |

Side panels can be enlarged to full screen (⤢) and closed (✕).

## Shortcuts

| Group | Keys |
|---|---|
| Canvas | `X` isolate the selection · `⌘Z` undo a view change · `⇧⌘Z` redo · `1 2 3` superentities, entities, subentities · `0` Auto · `K` color · `[ ]` levels · `+ − F` zoom and fit · `/` or `⌘K` find · `D` draw · `Esc` close the top thing |
| Demo | `E` examples · `→` next scripted step · `Space` play or pause · `⇧← ⇧→` step through the timeline · `U` request an update |
| Walkthrough | `W` open · `← →` previous and next step |
| Panels | `I` console · `N` news · `B` briefs · `Q` ask · `M` long-term memory · `C` checks · `G` transmission grid · `H` how it works · `,` admin · `A R` approve or reject · `?` every shortcut |

On Windows and Linux, `Ctrl` replaces `⌘`, and redo is `Ctrl-Y`.
