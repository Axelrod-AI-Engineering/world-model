# The ML stack: a formal specification (as built)

This page states, in mathematical terms, what the code computes today: every model, update, test, and constant, with the file that implements it. It describes the implementation, not the intent. Where the implementation is a heuristic, or where it is unsound, the page says so; [ml-roadmap.md](ml-roadmap.md) proposes what replaces it. Paths are relative to `src/axelrod_wm/`. Two sections are plans rather than descriptions: [Small models first](#small-models-first), on which model each step should use, and [§14](#14-fine-tuning-to-own-the-structure), on fine-tuning models on the structure we own.

<!-- toc -->
**Contents**

- [1. Objects and notation](#1-objects-and-notation)
- [2. An interaction](#2-an-interaction)
- [3. The state-space model of working memory](#3-the-state-space-model-of-working-memory)
- [4. Learning in working memory (one vetted event)](#4-learning-in-working-memory-one-vetted-event)
  - [4.1 The fold: a joint Kalman update (`learning/fold.py:89-247`)](#41-the-fold-a-joint-kalman-update-learningfoldpy89-247)
  - [4.2 Existence: a likelihood-ratio pseudo-count (heuristic, and unsound)](#42-existence-a-likelihood-ratio-pseudo-count-heuristic-and-unsound)
  - [4.3 Kernel learning: a three-point grid with a likelihood gate (`learning/kernel_learning.py:77-149`)](#43-kernel-learning-a-three-point-grid-with-a-likelihood-gate-learningkernellearningpy77-149)
  - [4.4 Level noise (`learning/consolidate.py:195-240`)](#44-level-noise-learningconsolidatepy195-240)
- [5. Intake: from article to operations](#5-intake-from-article-to-operations)
- [6. Propagation: the Monte Carlo impulse model (`dynamics/propagation.py:219-464`)](#6-propagation-the-monte-carlo-impulse-model-dynamicspropagationpy219-464)
- [7. Transmission orders and ripple judgments (`inference/transmission.py:53-114`)](#7-transmission-orders-and-ripple-judgments-inferencetransmissionpy53-114)
- [8. Learning in long-term memory](#8-learning-in-long-term-memory)
  - [8.1 Taxonomies: signature descent (not Cobweb)](#81-taxonomies-signature-descent-not-cobweb)
  - [8.2 The correlation frontier (`learning/frontier_test.py`, `memory/frontier.py`)](#82-the-correlation-frontier-learningfrontiertestpy-memoryfrontierpy)
  - [8.3 Superentities: co-activation induction (`learning/abduction.py:149-597`)](#83-superentities-co-activation-induction-learningabductionpy149-597)
  - [8.4 Recall and analogy (`shared/recall.py`)](#84-recall-and-analogy-sharedrecallpy)
- [9. Inference: answering a what-if (`inference/task.py:95-192`)](#9-inference-answering-a-what-if-inferencetaskpy95-192)
- [10. Evaluation (`evaluation/`)](#10-evaluation-evaluation)
- [11. Open-world measures (`memory/open_world.py`): display only](#11-open-world-measures-memoryopenworldpy-display-only)
- [12. Constants](#12-constants)
- [13. Adversarial review](#13-adversarial-review)
  - [What changed on this page](#what-changed-on-this-page)
  - [What the review found wrong with the model](#what-the-review-found-wrong-with-the-model)
<!-- /toc -->

This page went through an adversarial review on fidelity, statistics, and finance (§13). Its corrections are folded in; the review's verdict, summarized there, is that **the forecasting core is a defensible linear-Gaussian design, but the stack is not yet sound for its stated purpose**: its evaluation is circular, two learners partly confirm themselves, several components count the same data more than once, and the design has no layer for what markets have already priced in.

**Scope.** Synthetic data only. Nothing here has been fit to, or validated on, real market data. Every number is a design default, not an estimate.

## Small models first

*This section and [§14](#14-fine-tuning-to-own-the-structure) are a plan, not a description of the code. Every replacement below is planned; the "Today" column is what is built.*

**The principle.** Each tool call or pipeline step uses the smallest model that does the job. A step tries, in order:

1. **Rules and templates**: regular expressions, lookup tables, the operation schema.
2. **Classical ML** over features the model already holds: logistic regression, gradient-boosted trees, conditional random fields (CRFs).
3. **Small embedders** (sentence-transformer class, about 100M parameters), with nearest-neighbour lookup or by sorting down a Cobweb concept tree ([cognition.md F3](design/cognition.md#in-one-table)).
4. **Small finetuned classifiers, taggers, and rankers** (encoders of 100–400M parameters).
5. **Decision models** (Jev-type, "System One"; [below](#decision-models-jev-type)): state in, typed decisions with calibrated probabilities out, in one pass and with no free text. Our own, finetuned on the ledger, or a hosted one such as TypeSafe's Jev where a client allows it.
6. **A large LLM**, only for the long tail, as the last entry of a fallback chain.

In dual-process terms, recognition handles the routine and deliberation only the exceptions. **Every fallback call is logged** with its input, its output, and the reviewer's decision on it, so the long tail becomes training data for steps 2–5 and shrinks over time. The ledger already records each proposal's `produced_by` and its review decision, so a fallback case is a ledger query, not a new store.

**The chain is already the mechanism for translation.** `configs/default.yaml` lists translators per kind, "tried in order until one returns events" (`news: [hand_drawn, template]`). A small extractor goes before `llm`, and `llm` (a stub today) goes last. Other slots are a single choice today; giving a slot an ordered list with a confidence floor per entry is planned.

### Decision models (Jev-type)

**What they are.** TypeSafe AI's Jev is the first public "System One model": "unstructured state in, typed probabilistic decisions out" ([TypeSafe, 2026](https://typesafe.ai/blog/introducing-system-one-models-and-jev)). A caller declares the questions and their possible answers in advance; the model answers every question about one state in parallel, in a single query, and generates no text. There are three answer types ([LangChain, 2026](https://www.langchain.com/blog/building-a-harness-with-jev)):

| Type | Answers | Returns |
|---|---|---|
| **Choice** | one of a declared set of options (Jev caps a set at 255) | a probability per option, and a confidence |
| **Score** | a level on an ordered scale | a continuous score, its distribution, and a confidence |
| **Noul** (yes or no) | whether a statement holds | the probability that it is true |

Jev is trained by *reinforcement learning for calibrated decisions* (RLCD), which rewards "epistemically honest probabilities" rather than human preference (RLHF) or verifiable answers (RLVR). Its architecture, size, and training data are undisclosed, and its speed, cost, and accuracy figures (70–500 ms; 40–200× faster than a frontier LLM on such queries) are the vendor's own. The name is Kahneman's System 1 (fast, automatic judgment) and Jevons's paradox (cheaper intelligence, more of it used).

**The research it draws on**, and what each part tells us:

| Line of work | Finding | What we take |
|---|---|---|
| Small models for agents ([Belcak et al., 2025](https://arxiv.org/abs/2506.02153)) | Most calls an agent makes are narrow and repetitive; small models are sufficient, more suitable, and cheaper for them, with a large model kept for open-ended turns | A heterogeneous system: decision models for the routine calls, a large model for the rest |
| Cascades and routers (FrugalGPT, RouteLLM, AutoMix; [survey, 2026](https://arxiv.org/abs/2603.04445)) | A cheap model answers first and defers when its confidence is low; thresholds on *uncalibrated* scores must be retuned per workload, while thresholds on calibrated error probabilities can be set once | Escalate on a calibrated probability, never on a raw score |
| Calibration audits of a System One model ([Calibrated Decisions at Scale, 2026](https://arxiv.org/abs/2609.24052)) | Jev coded 195,857 police narratives against a 27-question schema at F1 0.908 against blinded human labels, level with one frontier LLM; recalibrating on labels cut calibration error 3.3×; calibration "depends on the model, not the paradigm"; a probability grid has a resolution floor | Audit and recalibrate every decision model on our own labels; spend the review budget where the model is unsure |
| Distilling LLM judgments into small classifiers ([soft-label distillation, 2026](https://arxiv.org/abs/2605.11954)) | A small encoder trained on a large model's soft labels gives better-calibrated probabilities than the teacher's verbalized confidence | Cold-start our decision models from a large model's labels, then train on reviewers' decisions |

**Why they suit this world model.** The engine is probabilistic from end to end, and most of what it asks of text is a choice among options it already knows: which of four candidate ids a mention names, which signal a sentence carries, whether a quote supports or contradicts an interaction, how likely a reviewer is to keep an operation. A decision model answers exactly those questions, in our types, with probabilities that enter where the engine already expects one: the hedge's weights $w_i$ (§5), an operation's confidence, the order of the review queue. A text generator would have to be parsed and its confidence guessed. Typed outputs cannot be malformed, and every answer is one of our ids or labels.

**The decisions, as questions.** Each is a question over one state (the item, its sentence, and the candidates the graph supplies), all answered in one call:

| Step | Question (type) | Where the probability goes |
|---|---|---|
| Triage | "Will this item yield an approved change?" (Noul) | Queue order; nothing is dropped |
| Resolution | "Which of these candidates does the mention name?" (Choice over the top candidate ids, plus "none of these") | The hedge weights $w_i$; binding still needs a named mention |
| Signal type | "What does this sentence claim?" (Choice: observe, move, link, support, contradict, none) | Which signal-to-operation mapping runs |
| Direction and size | "Which way, and how far?" (Choice of sign; Score over the magnitude buckets the templates use) | The operation's delta, as a distribution |
| Conflict | "Does this quote support, contradict, or not bear on the interaction?" (Choice) | Support and contradict signals; a contradiction is flagged in review |
| Review | "Would a reviewer keep this operation unchanged?" (Noul) | Staging's preselection and queue order; never wider auto-apply |
| Thesis subject | "Which value does this question shock?" (Choice over candidate ids) | Pose a thesis, shown before posing |
| Hypothesis worth simulating | "How much would resolving this change the forecast?" (Score) | Which hypotheses the Monte Carlo scores first |
| Agent guardrail | "Is this agent request a write?" (Noul) | Writes go to review (M15) |

**Hosted or owned.** A hosted decision model needs no training but sends the item to its vendor, so it fits synthetic and public data, and clients who allow it. Our own decision models run inside the client's environment and learn our ids from the ledger (§14, P1). Both sit behind one slot, so they can be compared on the same history.

**The audit, for any decision model.**
- **Calibration** on held-out reviewer decisions: expected calibration error, Brier score, and a reliability curve per question.
- **Recalibration** by isotonic regression or temperature on the validation window, rechecked on the test window.
- **Escalation** to the next rung when the calibrated probability of the top answer falls below a threshold set once, from the cost of a review against the cost of an error.
- **Review budget**: the uncertain answers go to a person first.

**What no model does**, at any size:
- compute an effect, a kernel, a forecast, an existence belief, or a scenario weight (the causal engine stays the source of truth). A decision model's calibrated probabilities weigh only *readings* of text: which candidate, which signal, how sure the reading is;
- bind an end the article does not name (M05: it may only weight the hedge's candidates);
- apply a change that the review policy sends to a person (vetted learning).

### Step by step

| Step (tool call) | Today (code) | Small-model replacement (planned) | Training signal we own | Fallback |
|---|---|---|---|---|
| **Market-event triage and relevance** | Deduplication by address, or site and title (`intake/scrapers.py`, `dedup_keys`). An import item's `relevance` is the upstream agent's own number. No triage model. | A decision model's Noul, "will this item yield an approved change?" (or, before there are labels, logistic regression over TF-IDF and small-embedder features). It orders the queue; it never drops an event. | Proposals approved or rejected; events logged as untranslated (`translate.missing`); item relevance against outcome | Translate everything, in arrival order |
| **Entity and value resolution** | `alias_fuzzy`: best `SequenceMatcher` ratio + 0.3 × word Jaccard + 0.2 × constraint fraction (`intake/resolver.py`). The refiner binds only a named mention; otherwise it hedges over up to 4 candidates. | A bi-encoder (about 100M) finetuned contrastively on (mention in context → entity or subentity id) retrieves candidates; a decision model's Choice over the top 4 (plus "none of these") gives calibrated hedge weights $w_i$ (§5); binding still needs a named mention. | Approved bindings; approved resolutions of hedged ends (`REFINEMENT` proposals); reviewer edits (`Proposal.edited_from`); bundle `entities` and `value_of` ids | `alias_fuzzy`; then an LLM choosing among the candidate ids or "open" |
| **Signal extraction** (observe, move, link, support, contradict) | Reviewed fixtures (`hand_drawn`); regular-expression templates at confidence 0.6 (`template`); signals written by the upstream agent (`structured`). The `llm` translator is a stub. | A decision model's Choice for the signal type, direction, and size bucket, and a CRF or small token tagger for the spans (subject, direction, magnitude, unit, timeframe). Spans are assembled into operations deterministically, by the code that already maps signals to operations (`intake/bundle.py`, `signal_ops`). Then P2's small seq2seq model (§14). | Hand-drawn translations (gold operations with phrase spans); template spans; bundle signals with quotes; approved and edited proposals | `llm`, constrained to the schema |
| **Interaction typing** | A link's label goes to a family by a keyword table (`model/taxonomy.py`, `label_family`; unmatched → "other"), then signature descent on the interaction's features (`taxonomy_descent`) | A classifier over the label's embedding and the two ends' attribute kinds, giving the interaction generalization | Approved `add_interaction` operations and the kinds they were sorted into | Keyword table and signature descent |
| **Quote alignment** | Exact substring match (`text.find(quote)` in `translate_item`); an unmatched quote gets no highlight | Rules first: normalize whitespace, case, and punctuation, then fuzzy character alignment. A small embedder matches a paraphrased quote to its sentence. | Bundle quotes that matched exactly (free positives) | Flag "quote not found" in review |
| **Conflict detection** (planned, M05) | Not built; rules are specified (opposite sign on an existing interaction, a value outside a soft bound, a retired item reused) | The rules, plus a decision model's Choice (supports, contradicts, does not bear) on the new quote against the evidence already behind the interaction | `support` and `contradict` signals; review decisions on flagged items | `llm_pairwise` (M05's planned alternative) |
| **Interaction proposal** | The correlation frontier (`residual_comovement`, `threshold`, §8.2) and missing relations from bound patterns | A gradient-boosted link ranker over graph features (kind priors, path distance, co-movement statistics) that orders the candidates the frontier tests; the JEPA prior of P3 later. The statistical test (R2) and review still decide. | Approved and rejected `FRONTIER_PROMOTION` and `MISSING_RELATION` proposals | The frontier alone |
| **Hypothesis ranking** (the hypothesis frontier) | `forecast_sensitivity_voi`: sensitivity × 4p(1 − p) from on/off Monte Carlo runs (§9) | A gradient-boosted surrogate predicting the value of information, used only to choose which hypotheses to simulate. The simulation stays the score. | Every VOI the engine has computed (cheap, exact labels); hypotheses people marked | Simulate all |
| **Actor decisions** (Entity memories) | `DecisionProfile`: empirical action frequencies per bucket (`memory/entity_memory.py`) | An ordered probit or multinomial logistic reaction function on the actor's own inputs (R19) | Decision observations already in each Entity memory | The empirical profile |
| **Superentity and analog recall** | `overlap_attention`: Jaccard of kind signatures, proximity, and support (`shared/recall.py`, §8.4) | Structured vectors (F5) sorted down Cobweb trees (F3); later the P3 state embedding for analogs | Admitted configurations; episodes and their realized responses | Signature Jaccard |
| **Thesis parsing** ("what if…", Pose a thesis) | `thesis_from_question` runs the template parser; with no match it raises "could not translate the question" | The tagger of signal extraction plus the encoder of resolution, for the subject | Posed theses and their operations; scaffolded theses that people edited | An LLM proposes operations, shown to the person before posing |
| **Find** | Lexical: stemming, a hand-written synonym table, kinds and their ancestors, filters (`api/find.py`) | Hybrid: BM25 plus a small embedder over names, aliases, and descriptions, grouped by concept-tree node | Aliases and kinds today; logged queries and the hits opened (planned: find does not log) | Lexical |
| **Brief writing** | Templates over the forecast, its explanation, the folds, and the deviations (`api/brief.py`); no language model | Stays templated. Optionally a small instruction model (≤ 8B) rewrites the prose only, under a check that every number and name it writes appears in the template's facts. | Reader notes on briefs (`ANNOTATION` ledger entries) | The template text |
| **Agent-context export** | Deterministic mapping into a client's format (`context/v4.py`) | No model. A new client format is a new mapping, written and reviewed once. | None needed | None |
| **Review confidence and auto-apply** | `DefaultReviewPolicy` rules: structure, deletions, text translations, large reweightings, and confidence below 0.8 go to a person (`repo/review.py`). Confidence is fixed per translator (template 0.6, data feed 1.0) or is the agent's own. | A decision model's Noul, "would a reviewer keep this operation unchanged?", recalibrated by isotonic regression (gradient-boosted trees as the baseline). It orders the queue and preselects operations in staging. It does not widen what applies without review; that stays a policy decision ([decisions.md](design/decisions.md)). | `REVIEW_DECISION` ledger entries; per-operation keep and confidence from staging; edits | The rules |

### Why

- **Client data stays on the client's premises.** Models of 100M–8B parameters run on a CPU or one GPU inside the client's environment, so articles, positions, and research never go to a third-party API.
- **Determinism and replay.** Fixed weights with greedy or constrained decoding give the same output for the same input, so a version still reproduces from (seed, version) ([design invariant 5](design/README.md#invariants)), and an ablation compares like with like.
- **Auditability.** A tagger's spans and a classifier's features explain each operation in the review; a fallback call is marked as one in the ledger.
- **Cost per import item.** A classical or small-encoder step costs microseconds to milliseconds on a CPU; a large-LLM call costs orders of magnitude more per item. With the LLM only on the tail, the cost of a 50-name daily feed is set by the tail's share, which the logged fallbacks drive down.
- **Owned structure.** Models trained on our ids and our reviewers' decisions encode the graph's schema, which a general model has to be told in every prompt (§14).

## 1. Objects and notation

| Symbol | Meaning | Code |
|---|---|---|
| $`e`$ | an entity (a company, agency, or economic idea) | `model/entity.py` |
| $`j`$ | a subentity: one value an entity holds (a price, a margin, a rate) | `Subentity` |
| $`c = (a \to b)`$ | an interaction (a channel) from source value $`a`$ to target value $`b`$; a bidirectional interaction has a forward channel and a reverse one (`:rev`) | `model/interaction.py` |
| $`t`$ | the day, an integer on a daily grid; day 0 is the world's origin date (UTC) | `memory/working.py:62-140` |
| $`x_j(t)`$ | the value in native units | |
| $`\ell_j(\cdot)`$ | the value's link: identity, log, or logit | `model/distributions.py:102-137` |
| $`z_j(t)`$ | the standardized deviation, $`z_j = (\ell_j(x_j) - m_j)/s_j`$, with anchor $`m_j`$ and scale $`s_j`$ | |
| $`r_j`$ | the value's observation noise, **an sd** in $`z`$ units; its variance is $`r_j^2`$ | `model/taxonomy.py:457-467` |
| $`H`$ | the forecast horizon in days (182 by default) | `configs/default.yaml` |
| $`S`$ | Monte Carlo samples (400 by default) | |

Everything the dynamics touch is in $`z`$ units. **The scale $`s_j`$ is set once**, when the value is created (from its kind's or its peers' mean scale, else 1.0 in link units; `shared/classify.py:194-212`), and never re-estimated from the value's own series. "One sd" is therefore a designer's unit, not a volatility: a 0.05 sd threshold is 0.4% for a share price with an 8% scale but 1.5 bp for CPI with a 0.3 pp scale. Every threshold below inherits this (review S-M9, F-C3).

Every processed day has a point for every value, observed or predicted. $`z`$ reads as 0 only before a value's history starts, or for days pruned below its first kept day.

**Distribution families** (link-space moments):

| Family | Link | Link mean, variance | Refit from moments |
|---|---|---|---|
| $`\mathrm{Gaussian}(\mu,\sigma)`$ | identity | exact | exact |
| $`\mathrm{LogNormal}(\mu,\sigma)`$ | log | exact | exact |
| $`\mathrm{Beta}(\alpha,\beta)`$ | logit | delta method: $`m = \mathrm{logit}(p)`$, $`v = \mathrm{Var}/(p(1-p))^2`$ | concentration $`\kappa = p(1-p)/\mathrm{Var} - 1`$, clipped to $`[0.5, 10^7]`$ |
| $`\mathrm{Gamma}(k,\theta)`$ | log | **approximate**: $`m = \log(k\theta)`$, $`v = 1/k`$ (the exact moments are $`\psi(k) + \log\theta`$ and $`\psi'(k)`$; the error is large for $`k \le 2`$) | $`k = 1/v`$, capped at $`10^9`$ |

Default observation noise $`r`$ (`model/taxonomy.py:457-467`): 0.02 for decision variables, 0.05 for rates and prices, 0.25 for sentiment indices, 0.15 otherwise. It is fixed by kind and never estimated.

## 2. An interaction

Each channel $`c = (a \to b)`$ carries:

- **existence** $`p_c \sim \mathrm{Beta}(\alpha_c, \beta_c)`$, read as the probability that the channel is real (§4.2 explains why the Beta adds no meaning beyond its mean);
- **effect** $`\beta_c \sim \mathcal{N}(\mu_c, \sigma_c^2)`$, in sd of $`b`$ per sd of $`a`$;
- **a kernel**: delay $`d_c`$, lag $`l_c`$, and duration $`D_c`$, each Gamma with coefficient of variation 0.3 (`model/temporal.py:18`);
- **moderators**, optional: a third value $`q`$ that scales or gates the channel.

**The kernel.** On the daily grid, $`d = \max(1, \mathrm{round}(\text{delay}))`$, $`l = \max(1, \mathrm{round}(\text{lag}))`$, $`\lambda = e^{-3/D}`$ ($`\lambda = 1`$ for a permanent effect). The step response is

$$
g(\tau) = \begin{cases} 0 & \tau < d \cr (\tau - d + 1)/l & d \le \tau \le d + l - 1 \cr \lambda^{\tau - (d + l - 1)} & \tau \ge d + l \end{cases}
$$

and the channel's regressor is $`\varphi_c(t) = \sum_{\tau \ge 1} g(\tau)\, \Delta z_a(t - \tau)`$, computed in $`O(1)`$ per day by summation by parts (`dynamics/kernels.py:1-90`): $`\varphi = S/l + T`$ with $`S(t+1) = S + z_a(t+1-d) - z_a(t+1-d-l)`$ and $`T(t+1) = \lambda T - (1-\lambda) z_a(t+1-d-l)`$. For a permanent kernel, $`\varphi`$ is the $`l`$-day moving average of $`z_a`$, lagged $`d`$ days. (The review verified the recursion numerically against the direct sum.)

**Every channel has a delay of at least one day.** No value responds on the day of its source's move. For traded prices this is the wrong default (§13, F-C1).

**Moderators** read $`z_q(t-1)`$: multiplicative, $`m_c \mathrel{*}= \mathrm{clip}(1 + \gamma z_q, 0, 3)`$; threshold, $`m_c \mathrel{*}= \mathbb{1}[z_q > \theta]`$; additive, the target gains $`\gamma z_q`$ (`dynamics/regressors.py:30-43`).

## 3. The state-space model of working memory

For each value $`b`$, the state is $`\theta_b = [a_b, \beta_{c_1}, \dots, \beta_{c_n}]`$ over its in-channels, with covariance $`P_b`$ (`dynamics/daily.py`). The measurement equation is

$$
z_b(t) = a_b(t) + \sum_c m_c(t)\thinspace  \varphi_c(t)\thinspace  \beta_c + u_b(t) + \epsilon_t, \qquad \epsilon_t \sim \mathcal{N}(0, r_b^2)
$$

where $`a_b`$ is a local level (a random walk, $`\mathrm{Var}(\Delta a) = \sigma^2_{\text{level},b}`$) and $`u_b`$ is the additive moderator inputs plus the reviewers' ripple correction (§7). There is no shock term in the filter: a reported change enters as an observation (§4.1).

**Existence is not in the filter at all.** `predict_state` (`dynamics/daily.py:174-181`) puts every channel of every non-retired interaction into $`h`$ at its full mean effect, and the fold's offset uses effect means only. A channel with existence 0.2 (a fuzzy end's soft interaction, or a just-promoted frontier edge) moves its target's daily state as much as one with existence 0.99. The Monte Carlo forecast, by contrast, switches channels off with probability $`1 - \mathbb{E}[p_c]`$ (§6). **The filter and the forecast are therefore different models** (review S-M2): the innovations the frontier reads, and the filtered values the evaluation scores against, come from a predictive the forecast does not use.

**Predict** (`daily.py:298-325`): $`\mathrm{Var}(\beta_c) \mathrel{+}= 0.0075^2`$ per day for every channel (a slow random walk on effects, whether or not the target is observed); $`P_{aa} \mathrel{+}= \sigma^2_{\text{level}}`$. The provisional point is $`\hat z = h^\top\theta + u`$ with $`h = [1, m_c\varphi_c, \dots]`$ and variance $`h^\top P h`$.

**Record** (`daily.py:328-377`): a value not observed today has its posterior refit to $`(m_j + s_j \hat z, s_j^2\, h^\top P h)`$. Off-diagonal covariances persist in `Subentity.state_cov`, clipped to $`0.999\sqrt{P_{aa}P_{bb}}`$.

## 4. Learning in working memory (one vetted event)

### 4.1 The fold: a joint Kalman update (`learning/fold.py:89-247`)

Each observation item gives $`y`$:
- for `observe_value`, $`y = (\ell(x) - m)/s`$ with variance $`r^2`$;
- for a reported change, $`y = z_{\text{now}} + \text{size}`$ with variance $`\max(\text{size}_{sd}, 0.05)^2`$, where $`z_{\text{now}}`$ is today's point (predicted, or already filtered if the value was observed earlier that day).

Channels with $`|m_c\varphi_c| < 0.05`$ leave the state and enter an offset $`o = u + \sum \mu_c m_c \varphi_c`$, where $`u`$ is the additive term of §3. Then

$$
s = h^\top P h + r^2, \quad k = P h / s, \quad \theta^+ = \theta + k\thinspace (y - o - h^\top\theta), \quad P^+ = P - k\thinspace  (P h)^\top
$$

symmetrized. The normalized innovation $`e = (y - o - h^\top\theta)/\sqrt{s}`$ feeds the correlation frontier.

**A reported change trains the effects.** Its innovation is set to 0 for the frontier, but the same update moves the in-channels' effects (gain $`\propto P_{cc} h_c`$), their existence, and the analog accumulators. Part of an exogenous, reported jump is thus attributed to the channels into that value (review S-M7).

### 4.2 Existence: a likelihood-ratio pseudo-count (heuristic, and unsound)

For each channel in the update (`fold.py:190-205`):

$$
L_1 = \mathcal{N}(y'; h^\top\theta, s), \qquad L_0 = \mathcal{N}\big(y'; h_{-c}^\top \tilde\theta_{-c}, h_{-c}^\top \tilde P_{-c} h_{-c} + r^2\big)
$$

where $`L_0`$ conditions the other states on $`\beta_c = 0`$ ($`\tilde\theta_{-c} = \theta_{-c} - P_{-c,c}\mu_c / P_{cc}`$, and so on). With $`p = \mathbb{E}[p_c]`$, the responsibility is $`r_c = pL_1/(pL_1 + (1-p)L_0)`$ and

$$
\alpha_c \mathrel{+}= w\thinspace  r_c, \qquad \beta_c \mathrel{+}= w(1 - r_c), \qquad w = \eta\thinspace \min(1, |m_c\varphi_c|), \quad \eta = 0.5.
$$

Here $`\eta`$ is `learning.existence_learning_rate`. The update runs once per observation item per channel, and both channels of a bidirectional interaction update the same Beta, so there is no daily cap. A fuzzy end's soft interactions have their Beta overwritten at each hedge check (§5), which discards these counts.

**Why it is unsound** (review S-M1):
- $`r_c`$ already contains the prior $`p`$, so prior information re-enters as data every time, and when $`L_1 \approx L_0`$ the Beta's concentration grows with no evidence.
- A channel exists or it does not: the right object is one inclusion probability with sequential odds, not a per-day Bernoulli rate. Under the right model, the odds move geometrically; here the mean moves at most about $`\eta/(\alpha + \beta)`$ per update.
- Once the effect posterior shrinks toward 0 for a channel that is not real, $`L_1 \approx L_0`$, so $`r_c \to p`$: **the model cannot learn absence**.
- Conditioning on $`\beta_c = 0`$ today is not "$`\beta_c \equiv 0`$" under the effect random walk.

In the Monte Carlo, existence is drawn as $`p \sim \mathrm{Beta}`$ then $`u < p`$ (`propagation.py:248-250`), which is marginally Bernoulli($`\mathbb{E}[p]`$): only the mean matters there. The Beta's spread acts only as a learning rate.

### 4.3 Kernel learning: a three-point grid with a likelihood gate (`learning/kernel_learning.py:77-149`)

Weekly, for each target with at least 8 observed days in the last 182, and each channel with at least 8 informative days ($`|\varphi| \ge 0.05`$): for $`\rho \in \lbrace 0.5, 1, 2\rbrace`$, scale delay, lag, and duration together by $`\rho`$ and score first differences between consecutive observed days,

$$
\ell(\rho) = \sum_{(a,b)} -\tfrac12 \frac{(\Delta z - \widehat{\Delta z}_\rho)^2}{v} - \tfrac12\log 2\pi v, \qquad v = \sigma^2_{\text{level}}(b-a) + 2r^2,
$$

with $`r`$ the target's default noise (not the tempered noise of §5). If $`\ell(\rho^{*}) - \ell(1) < 2`$, nothing moves; otherwise the kernel's means are multiplied by $`\sqrt{\rho^{*}}`$. **The CV shrinks by 10% on every eligible run** ($`\mathrm{cv} \leftarrow \max(0.15, 0.9\,\mathrm{cv})`$), whether or not the data moved the kernel, so confidence grows with time rather than with evidence.

Three biases (review S, minor): the $`\Delta z`$ are differences of *filtered* values computed with the current kernel, which favors $`\rho = 1`$; consecutive differences of noisy observations are MA(1), not independent; and the effect is held fixed while the kernel rescales, although the two are confounded.

### 4.4 Level noise (`learning/consolidate.py:195-240`)

Every 7 days, $`\sigma_{\text{level}} = \mathrm{sd}(\text{weekly level changes over} \le 52 \text{ weeks})/\sqrt 7`$ (population sd), clipped to $`[0.02, 1]`$, with at least 8 weeks of data, floored at 0.04 for decision variables. On unobserved days the level stays at its prior mean, which biases the estimate down. Because $`r`$ is fixed by kind and never estimated, only the ratio $`\sigma^2_{\text{level}}/r^2`$ is identified, and it is identified wrongly whenever $`r`$ is wrong.

## 5. Intake: from article to operations

**Translation.** Fixtures; a data feed, where each data point becomes `observe_value` and a decision variable that moves more than half a standardized unit becomes `change_value`; and regular-expression templates at confidence 0.6 (`intake/translators.py`). The LLM translator is a stub; the plan keeps a large LLM as the last fallback only ([Small models first](#small-models-first)). **A data release is read as a level, not as a surprise against a consensus**: there is no expectations field anywhere (review F-C1).

**Binding** (`intake/refiner.py:271-359`). An entity binds only when the article names it (its name, an alias, or a subentity's name of three or more characters). Otherwise the end stays fuzzy.

**Fuzzy ends: a Dirichlet over candidates with an open reserve** (`refiner.py:496-544`, `memory/working.py:210-219`).
- Up to 4 candidates per end, with resolver weights $`w_i`$. Then $`\alpha_i = 1.0\, w_i`$ and an open mass $`\alpha_\varnothing = 0.5`$. A candidate's share is $`p_i = \alpha_i / (\sum\alpha + \alpha_\varnothing)`$.
- Each candidate is drawn as a soft interaction with existence $`\mathrm{Beta}(\kappa p_i c, \kappa(1 - p_i c))`$, where $`\kappa = 2 + \text{support}`$ and $`c`$ is the reviewer's confidence.
- Later articles add $`1.5c`$ for a mention, and $`1.0c`$ for a co-movement of the right sign. A co-movement counts at most once per 14 days per candidate; one of the wrong sign spreads that mass over the rivals and the open reserve.
- A resolution is proposed when $`\max_i p_i \ge 0.75`$ and support $`\ge 3`$.

**These shares are counts, not posteriors** (review S-M8):
- Mentions count news volume, and syndicated articles are not independent.
- A same-sign co-move adds the same amount whatever its size, and happens half the time by chance.
- The same move also updates the soft interaction through the fold, so it is counted twice.
- The candidates are mutually exclusive, but they are sampled as independent Bernoulli interactions. The forecast therefore includes configurations where two candidates are both on.

**Reviewer confidence $`c`$** (`shared/parse.py:191-339`):
- An observation's noise sd is divided by $`\sqrt{\max(c, 0.02)}`$. This is a power likelihood (tempering).
- A reported move of size $`\delta`$ becomes $`c\delta`$, with sd $`\sqrt{c\sigma^2 + c(1-c)\delta^2}`$. These are the moments of a $`c`$-mixture of the move and no move, collapsed to one Gaussian, so "maybe happened" becomes "partly happened".
- A new interaction's Beta pseudo-counts are shrunk toward Beta(1,1) by $`c`$.

None of these is Jeffrey conditioning in the strict sense, and $`c`$ is not calibrated.

## 6. Propagation: the Monte Carlo impulse model (`dynamics/propagation.py:219-464`)

**Per-sample parameters.** For each sample $`s = 1..S`$, parameters are drawn once and held over the horizon:
- existence: $`\mathbb{1}^{(s)}_c`$, as $`p \sim \mathrm{Beta}`$ then $`u < p`$, unless forced;
- $`\beta^{(s)}_c`$, $`d^{(s)}_c`$, $`l^{(s)}_c`$, $`D^{(s)}_c`$, and the moderator coefficients, each drawn from its marginal.

**Effects and kernels are drawn independently**, ignoring the posterior covariance the filter keeps (`state_cov`). Collinear in-channels have negatively correlated posteriors, so independent draws inflate the spread of their sum (review S-M3).

Every sample starts exactly at today's $`z`$, with the level set to $`z_{\text{now}}`$ minus the channels' contributions. **There is no initial-state uncertainty**, so short-horizon intervals are too narrow.

**Each day.** For $`t = 1..H`$:

$$
a^{(s)}(t) = a^{(s)}(t-1) + \delta_b\thinspace  0.985^t + \sigma_{\text{level},b}\thinspace \varepsilon, \qquad
z^{(s)}_b(t) = a^{(s)}(t) + u_b(t) + \sum_c \mathbb{1}^{(s)}_c \beta^{(s)}_c m^{(s)}_c(t)\thinspace  \varphi^{(s)}_c(t)
$$

- $`\delta_b`$ is the 28-day level trend, clipped to $`\pm 0.03`$/day and damped by $`0.985^t`$. The damped sum over 182 days is about 61.5, so the **drift can move a median by up to about 1.85 sd**. Under the model's own random-walk level, the expected drift is 0, so this injects about 0.47 sd of estimation noise at the horizon. For share prices, which tend to reverse over a month rather than continue, it is spurious expected return (review S-M4, F-M4).
- **Shocks**: a STEP shock holds from its start day, a PULSE lasts one day, and each has size $`\sim \mathcal{N}(\text{size}, \text{size}_{sd})`$ per sample. A do()-intervention holds $`z_{\text{now}} + \text{size}`$ and overrides the value's channels and level noise.
- **Soft bounds**: every value, every day, in both runs, passes through $`z \mapsto hi - w\log(1 + e^{(hi - z)/w})`$ (and the mirror for $`lo`$), with $`w = 0.25`$. This applies to all values, not only those past a bound: a value exactly at the bound is pulled $`w\ln 2 \approx 0.17`$ sd below it, and the bend starts about 1 sd before it. The bound acts on the output only; the level state is unbounded.
- **Ripple judgments are not used here** (§7).

**Common random numbers.** Every draw comes from a named substream (`engine/rng.py`):
- per channel: "p", "u", "effect", "delay", "lag", "duration", "mod";
- per value: "level";
- per shock.

Runs with and without a shock, or with different channel sets, share the draws of every channel they have in common, so differences are not Monte Carlo noise. Seeds include the state version, so a forecast is reproducible from (seed, version).

**An effect** is the per-sample difference of two runs on the same draws: $`\Delta^{(s)}_b(t) = z^{(s),\text{shocked}}_b(t) - z^{(s),\text{base}}_b(t)`$. Level noise cancels in it, so **an effect's band shows parameter uncertainty only, not the spread of the outcome**: a reader must not take it as the distribution of the realized move (review F-M7).

**What the model leaves out.**
- Observation noise in forecasts.
- Correlation of level shocks across values: there is no market factor, so a 50-name book's risk is understated several-fold (F-C2).
- Heavy tails, volatility clustering, and regimes.
- Any same-day response.
- An expectations layer.
- Mixed-frequency or vintage handling (§5).

## 7. Transmission orders and ripple judgments (`inference/transmission.py:53-114`)

**Orders and paths.** For a set of shocked values, each pair $`(a, b)`$ keeps its most significant channel, $`\mathrm{sig}_c = \mathbb{E}[p_c]\,\mathbb{E}|\beta_c|`$ (channels forced off are excluded). A value's **order** is its breadth-first hop distance from the nearest shocked value (at most 6). Its **path** is, among the shortest paths only, the one with the largest $`\prod \mathrm{sig}`$.

**Sizes.** Size comes from simulation, not from the path: peak $`= \mathrm{med}_s \Delta(t^{*})`$ at $`t^{*} = \arg\max_t |\mathrm{med}_s\Delta(t)|`$. A value is **material** when $`\max(|\text{peak}|, |\text{effect at } H|) \ge 0.05`$ sd. Its arrival day is the sum of the path's integer mean delays (the lag ramps are ignored).

**In a forecast**, orders and paths come from the top-weighted scenario's channels, while sizes come from the scenario mixture. The list is capped at 240 values; the review shows the material ones, at most 24.

**Caveats** (review S-M10, F-M7):
- An order is a hop count, not an expected effect, and a value reached by two routes is listed once.
- Medians hide low-probability large effects: with $`\mathbb{E}[p] < 0.5`$, the median effect is 0 even when the mean or the 90th percentile is large.
- $`\prod \mathrm{sig}`$ discards sign and is not the path's expected effect.
- "Material" is in designer units (§1).

**Ripple judgments.** A reviewer may say a value's ripple arrives with probability $`w < 1`$. The approval stores the median ripple path times the upstream weights. From the processing day until the path ends, the **daily filter** adds $`(w - 1)\cdot\text{path}(t)`$ to the value's additive term (`memory/working.py:245-251`).

**Limits of ripple judgments:**
- It is a mean shift: variance is not added and the arrive-or-not mixture is not represented.
- $`w`$ multiplies a median that already integrates existence uncertainty, so doubt is counted on top of $`p`$.
- Observing the target never updates $`w`$.
- **The Monte Carlo forecast ignores judgments.** It replays the channels in full, so a reviewer's $`w`$ reaches forecasts only through the recorded history.

**The transmission grid** (`inference/paths.py`, in the app) lays a ripple or a forecast out as input, first, second, third order, and output. It offers four ways of choosing what is relevant:
- by order;
- the largest effects;
- only what lies between the inputs and the outputs;
- the strongest paths by linear path gain $`\prod \mathbb{E}[p]\,\mu`$;
- **relevant** (the default): a value is kept when $`|\text{peak}| \cdot 0.6^{\,\text{order} - 1}`$ is at least 12% of the largest such score, so each further order counts 40% less but a strong distant effect still shows; orders go as deep as six.

All five read the same simulated effects.

## 8. Learning in long-term memory

### 8.1 Taxonomies: signature descent (not Cobweb)

**Kinds and classification.** Each kind (object generalization, interaction generalization, superentity configuration) is a node with a **signature** (required and any-of feature values) and statistics. Classification (`shared/classify.py:62-80`) descends to the child with the highest fraction of signature keys satisfied (ties go to support) and stops below 0.5. A node **supplies priors** once its support exceeds the recall threshold (4).

**Splits.** A node with at least 5 direct instances may split on a feature value shared by at least 4 of them. A first split also needs a second disjoint group of 4, so in practice at least 8. **Only support is divided between the children**, in proportion to their share; the effect, level, scale, and kernel statistics and the existence pseudo-counts are copied unchanged (`classify.py`, `maybe_split`).

**Priors from a kind.** A new value's link-space prior is $`\mathcal{N}(\bar m, \bar v + \bar s^2)`$, from the node's Welford statistics. A new interaction gets:
- an effect prior $`\mathcal{N}(\bar\mu, \bar v + 0.15^2)`$;
- the kind's mean kernel;
- the kind's existence Beta.

**Statistics are pushed per touch, and the priors collapse** (`learning/generalize.py:57-129`; review S-C4). Every event that touches an item, including a routine data release, pushes that item's *current posterior mean* into every node on its classification path, and adds $`0.1p`$ and $`0.1(1-p)`$ to the node's existence Beta. The consequences:
- The same items repeat, so the between-member variance shrinks toward zero, and an effect prior's sd ends near the 0.15 floor whatever the real heterogeneity.
- The mean is weighted by activity.
- After 1,000 touches, a brand-new edge starts with an existence concentration near 100, which the fold barely moves.
- The kind prior feeds new edges, whose posteriors are pushed back into the kind: a feedback loop.

### 8.2 The correlation frontier (`learning/frontier_test.py`, `memory/frontier.py`)

**Finding candidates.** A **mover** $`b`$ has a 14-day window innovation $`|\sum e/\sqrt n| \ge 1.5`$. Candidate sources $`a`$ moved $`|\Delta z_a| \ge 0.5`$ at one of the lags $`\lbrace 0, 1, 2, 3, 5, 7, 10, 14, 21, 28\rbrace`$, with no existing channel between them. The score is $`|\Delta a \cdot \text{innov}_b|`$; the best lag is kept per source, and the top 5 sources per mover.

**Statistics.** A held pair's history is backfilled from non-overlapping 14-day windows over 182 days, including the window that selected it:
- a running Pearson $`r`$ of the source's window change against the target's window innovation;
- an OLS slope of the target's *raw window change* on the source's change.

**Re-checks.** A pair is re-checked at most every 14 days. A consistent sign adds one to support, an inconsistent one subtracts one. The hypothesis probability is support/(support + 4).

**Decay.** A pair unseen for more than 14 days decays with a half-life of 30 days and is dropped below 0.5. A rejected pair is blocked for 60 days.

**Promotion** proposes an edge when support $`> 3`$, $`|r| \ge 0.3`$, and at least 75% of checks were consistent. The proposed edge has:
- effect = the slope, with sd $`\max(0.2, 2\,\mathrm{SE})`$ (0.5 when the SE is undefined);
- existence $`\mathrm{Beta}(1, 3)`$;
- a permanent kernel with delay $`\max(1, \text{lag})`$ and lag 14 days.

**There is no valid inference here** (review S-M6):
- **Selection on the outcome.** The thresholds select extreme windows, which inflates $`r`$ and the slope. The lag and sign are chosen by maximizing over 10 lags and every source, and the backfill reuses the selecting window.
- **The bar is low.** Under the null, three consistent re-checks with none inconsistent happen with probability 1/8 per selected pair. With about 13 windows, $`|r| \ge 0.3`$ corresponds to $`p \approx 0.3`$; the 5% critical value is about 0.55.
- **The slope is biased.** It is fit on the raw change, not the innovation, so it absorbs common drivers and existing parents.
- **A lag-0 pair becomes a one-day lagged edge**, and non-synchronous closes create one-day lead-lags that are not real.

Promotion only proposes: a person must approve.

### 8.3 Superentities: co-activation induction (`learning/abduction.py:149-597`)

**Finding components.**
- Each day, a channel is **active** when its 28-day contribution agreed in sign with its target's 28-day move. Edges tagged `kind_default` are excluded.
- Connected components of at least 2 active channels are scored by the share of their targets' movement they explain, less 0.05 per edge. They are kept greedily, at most one per actor entity per day.
- A component matches an existing configuration when the Jaccard similarity of their relation tuples is at least 0.75, or when the configuration's tuples (at least 2) are contained in it.

**Support and proposals.**
- Unmatched components start candidates.
- Support grows by at most one every 14 days and decays with a half-life of 90 days.
- Candidates above 3 are proposed for admission; admitted ones below 1 are proposed for dissolution.
- Two admitted configurations that co-occur on more than 3 spaced days, with an edge between them, form a composite candidate.
- **Rivals** are configurations over the same members that disagree on a relation's presence or sign. Evidence of absence (a source move of at least 1 with a target move under 0.25) supports the rival that omits the relation.

**This partly confirms itself** (review S-C2). On days the target was not observed, its "move" is the model's prediction, which contains the channel's own contribution, so the sign test passes by construction. Even on observed days, effects were fitted to agree with past moves. There is no null rate and no control over the number of components scanned.

### 8.4 Recall and analogy (`shared/recall.py`)

**Signatures and scores.** An event's signature is the set of kinds on its classification paths.
- A configuration scores $`0.5\,J + 0.3\,\text{prox} + 0.2\,\log(1+\text{support})/\log(1+\max\text{support})`$, with $`J`$ the Jaccard index of signatures.
- An episode scores $`0.5^{\text{age}/365}(0.4J + 0.3\,\text{tags} + 0.3\,\mathbb{1}[\text{type}])`$, boosted by its stored explanations.
- Attention is a softmax with temperature 0.5 over the top $`k`$, dropping weights below 0.02.

**Empirical-Bayes prefill** (`shared/prefill.py`, `engine/interfaces.py:131-162`).
- Recalled episodes carry per-channel response estimates $`(b_E, w_E)`$.
- These pool into a pseudo-observation $`\bar b = \sum a_E w_E b_E / \sum a_E w_E`$, with variance $`\bar v = r^2/\sum a_E w_E + 0.1^2`$.
- The pseudo-observation is combined with the channel's posterior by precision weighting. This feeds the analysis only; it is not committed.
- When the episode lacks the channel, the code pools over same-kind siblings, but only siblings whose effect has the same sign.

**This counts the same data twice or more** (review S-C3):
- $`(b_E, w_E)`$ come from the fold accumulators of observations the posterior has already absorbed.
- A day is pooled into every non-routine episode within 42 days, so one day enters once per overlapping episode.
- The same-sign filter biases the pooled mean away from zero.

## 9. Inference: answering a what-if (`inference/task.py:95-192`)

A thesis runs on a copy-on-write overlay that is never committed.

1. **Isolate** (`inference/isolate.py:167-282`). Candidate networks are the recalled configurations' instances. Relevance $`= 0.5\,\text{attention} + 0.5\,\text{reach}`$, with reach $`= \max \exp(-\text{dist})`$ over a path cost of $`-\log \mathrm{sig}`$. The analysis keeps:
   - networks with relevance $`\ge 0.05`$, at most 8 (the yaml's `isolation.max_networks`);
   - rivals of kept networks with relevance $`\ge 0.025`$;
   - a residual network of significant channels the others miss;
   - when there are shocks, a watch network of paths to the watched entities and targets.
2. **Predict** each network: two Monte Carlo runs, shocked and base, on the same draws.
3. **Unify.** Rival networks become scenarios.
   - Within a scenario, the chosen rival's present relations are **forced on** and its absent ones **forced off**. Branched hypotheses are forced on or off.
   - A rival's weight within its group is prior (support + 1, normalized) × fit (a softmax of log-fit) × track record $`(h+1)/(h+m+2)`$.
   - Each branched open hypothesis contributes $`p`$ or $`1-p`$. A hypothesis is branched when its value of information is $`\ge 0.15`$ and $`p \in [0.15, 0.85]`$.
   - The top 8 scenarios are kept and renormalized; the dropped mass is reported.
   - **The weights reuse overlapping evidence and are near winner-take-all** (review S-M5):
     - fit is $`-\tfrac12\sum(\Delta z - \widehat{\Delta z})^2/v`$ over the last 56 days of filtered values, in sample, with no Occam penalty, and over each network's own targets, so networks with different targets are not compared on equal terms;
     - support comes from the self-confirming induction (§8.3);
     - track records come from backtests on the same history;
     - frontier hypothesis probabilities are count heuristics.
4. **Couple**: the union of a scenario's networks, simulated jointly on shared draws.
5. **Read out.**
   - Samples are split across scenarios by weight (largest remainder; scenarios under about $`1/(2S)`$ get none).
   - Every value's effect is given by order and path (§7).
   - A group forecast is the per-sample mean effect over all its members' values. This mixes signs and units (fuel cost up, margin down, shares down), so it is **not** an investable number (F-C2).

**Value of information** (`inference/voi.py:101-286`): $`\mathrm{VOI} = \text{sens} \times 4p(1-p)`$.
- sens $`= \sum_{\text{watch}} w_j\, |\mathrm{med}_{\text{on}}(H) - \mathrm{med}_{\text{off}}(H)|`$, where "on" and "off" force the hypothesis's interaction.
- It is averaged over up to 3 reference theses, using 100 draws, and recomputed at most weekly.
- It decays with a half-life of 14 days.
- It is a heuristic proxy, not an information measure.

**Explanation** (`shared/explain.py`):
- paths ranked by $`\prod \mathbb{E}[p]\,\mathbb{E}|\beta|`$ along simple paths of at most 5 edges, three per shock and target;
- channel importance by ablation (existence forced off, 100 samples).

## 10. Evaluation (`evaluation/`)

The scorer compares a forecast with what the synthetic world then did.

**Metrics.**
- **Omission**: significant realized moves not predicted.
- **Commission**: predicted moves that did not happen.
- Interval **coverage** at 50/80/90%.
- **CRPS**, approximated as twice the mean pinball loss over seven quantiles. That is proper for the seven-quantile vector, but it overweights the tails and is not comparable with a sample CRPS.

A significant move is a change $`|\Delta z| \ge 0.5`$ from the freeze day to the last observed day within $`H`$. A prediction needs $`|\text{median level change}| \ge 0.5`$ and $`P(\text{sign}) \ge 0.7`$. A backtest freezes the state, replays the later reported changes as a thesis, and updates configurations' track records.

**The evaluation is circular** (review S-C1). The "realized" values are the live engine's *filtered* points (`backtest.py:122-130`), which are pulled toward the model's own predictions. At steady state, the Kalman gain is about 0.15 for sentiment series, 0.23 for the default noise, and 0.54 for prices and rates. The synthetic world holds the true values and its releases carry no measurement noise, so this is unnecessary.

**Further limits.** The backtest:
- conditions on the realized shocks (an oracle);
- scores raw changes rather than moves abnormal to the market;
- uses one event;
- applies one 0.5-sd threshold at every horizon.

The same circularity reaches kernel learning (§4.3) and scenario fit (§9).

## 11. Open-world measures (`memory/open_world.py`): display only

These feed the canvas's open nodes; inference and learning do not read them.

| What | Measure |
|---|---|
| A value | $`(\sum_d (z_d - \sum_c \mu_c\varphi_c(d))^2 + 1)/(\sum_d z_d^2 + 1)`$ over 28 days, clipped to $`[0, 1]`$. It uses levels, not changes, and ignores moderators. |
| An entity | the mean over its values |
| An instance | the same ratio pooled over its members, counting only its own channels |
| A kind | $`\alpha/(\text{support} + \alpha)`$ with $`\alpha = 1`$ |
| A configuration | $`\alpha/(\text{support} + \text{rivals' support} + \alpha)`$ |
| A fuzzy end | its Dirichlet open share |

## 12. Constants

| Constant | Value | Where |
|---|---|---|
| Kernel CV | 0.3; learning step 0.5, gate 2.0, CV shrink 0.9 to a floor of 0.15 | `model/temporal.py:18`, `learning/kernel_learning.py` |
| Default kernel for a new edge | delay 14, lag 30, permanent; effect N(0, 1) when no kind applies | `shared/parse.py:250` |
| Effect prior floor | sd 0.15 | `model/taxonomy.py:28` |
| Effect random walk | 0.0075² per day | `dynamics/daily.py` |
| Existence learning rate | 0.5 | `learning.existence_learning_rate` |
| Regressor floor | 0.05 | `learning/fold.py` |
| Level noise | default 0.04; estimated from ≥ 8 weeks, clipped to [0.02, 1] | `learning/consolidate.py:56-58` |
| Minimum change noise | 0.05 | `shared/parse.py:350-352` |
| Drift | 28-day trend, ±0.03/day, damped 0.985/day | `shared/prefill.py:23-31` |
| Material effect | 0.05 sd; max order 6; 24 shown at review, 240 per forecast | `inference/transmission.py:20, 54` |
| Soft bound width | 0.25 sd; a bound "hit" bends a value by more than 0.1 | `dynamics/propagation.py:79, 455` |
| Recognition / recall thresholds | support > 3 / > 4 | `engine/context.py:115-120` |
| Frontier | mover 1.5; source move 0.5; 10 lags; top 5; spacing 14 d; $`\lvert r\rvert \ge 0.3`$; consistency 0.75; decay half-life 30 d after 14 d unseen; drop below 0.5; block 60 d | `learning/frontier_test.py` |
| Hedge | prior 1.0; open 0.5; mention 1.5; move 1.0; commit 0.75; soft-edge concentration 2.0 | `engine/config.py:136-142` |
| Superentity induction | contribution ≥ 0.2; −0.05 per edge; +1 per 14 d at most; half-life 90 d; admit > 3; dissolve < 1 | `learning/abduction.py` |
| VOI | 100 draws; recomputed weekly; half-life 14 d; branch at VOI ≥ 0.15, $`p \in [0.15, 0.85]`$ | `inference/voi.py`, `engine/config.py:96` |
| Samples, horizon | 400, 182 d | `configs/default.yaml` |

**Mismatches and unused settings.**
- Two settings disagree between `configs/default.yaml` and the code defaults: `attention.top_k_superentities` is 8 vs 6, and `isolation.max_networks` is 8 vs 6. The yaml wins at run time.
- `refinement.bind_score`, `refinement.evidence_bonus`, and `time.step_days` are read nowhere. The same 0.2 as `evidence_bonus` is hard-coded in `intake/refiner.py`.
- The `posterior_updater` slot is registered but never called.

## 13. Adversarial review

Three independent reviewers, each an agent instructed to break this page and the roadmap, read both pages against the code (Oct 11, 2026):
- **Fidelity (V)**: does every claim match the code?
- **Statistics (S)**: are the methods sound?
- **Finance (F)**: would the outputs mislead a portfolio manager or a risk officer?

### What changed on this page

The fidelity review found four claims wrong in the first draft:
- existence in the daily filter (§3);
- a daily cap on existence learning (§4.2);
- "at most 6 networks" (§9);
- how a split divides statistics (§8.1).

It also found misleading or imprecise statements about:
- the soft bound (§6);
- ripple judgments and forecasts (§7);
- scenario forcing (§9);
- noise notation (§1, §4.3);
- the frontier's details (§8.2);
- the evaluation's definitions (§10).

All are corrected above, and its omissions are added: initial-state uncertainty, independent parameter draws, shock semantics, per-touch statistics, prefill double counting, open-world measures, and the missing constants. It verified the kernel recursion numerically and confirmed the rest of the math and the file references.

### What the review found wrong with the model

Each finding has a roadmap item.

| ID | Finding | Severity | Roadmap |
|---|---|---|---|
| S-C1 | Evaluation, kernel learning, and scenario fit score against the model's own filtered values | critical | R0 |
| S-C2 | Superentity induction passes its own sign test on unobserved targets; no null rate | critical | R2, R16 |
| S-C3 | Analog prefill counts the same observations two or more times; sign-filtered siblings | critical | R18 |
| S-C4 | Kind statistics pushed per touch: priors collapse; new edges get near-dogmatic existence priors | critical | R5, R18 |
| F-C1 | No expectations or pricing-in layer: traded prices react late to realized changes, so forecasts claim large post-news drift | critical | R13 |
| F-C2 | No market factor or cross-correlation; group readouts mix signs and units | critical | R9, R14 |
| F-C3, S-M9 | "sd" is a designer's unit: scales never estimated, so every threshold means something different per value | critical | R3 |
| F-C4 | The synthetic world is built from the model's own equations: recovery on it is self-consistency, not evidence | critical | R16 |
| S-M1 | Existence pseudo-count re-adds the prior, cannot learn absence | major | R1 |
| S-M2, V-1 | Filter and forecast are different models (existence) | major | R1 |
| S-M3 | Independent parameter draws and no initial-state uncertainty | major | R9 |
| S-M4, F-M4 | Momentum drift in the baseline, spurious for prices | major | R13 |
| S-M5 | Scenario weights reuse evidence, in-sample, winner-take-all | major | R7 |
| S-M6 | Frontier: selection on the outcome, no valid test, biased slope | major | R2 |
| S-M7 | Reported changes train the in-channel effects | major | R1 |
| S-M8 | Fuzzy-end shares count volume; candidates sampled as independent | major | R18 |
| S-M10, F-M7 | Medians hide low-probability effects; effect bands omit outcome noise | major | R12 |
| F-M1, S-M12 | No point-in-time data: reference periods, release dates, vintages, mixed frequency | major | R15 |
| F-M2, F-M3, F-M5 | Economic structure: the airline chain's timing and hedging, policy reaction functions, regime-dependent signs | major | R19 |
| F-M6 | The evaluation would not convince a desk | major | R10 |

**The reviewers' order of first fixes**, which the roadmap adopts:
1. Score against observations or the true state.
2. Use each observation once.
3. Make the frontier and induction use observed, out-of-sample quantities with error-controlled tests.
4. Make the filter and the forecast one model.
5. Fix the units.
6. Add an expectations and factor layer for traded values.
7. Test everything on misspecified and null synthetic worlds.

## 14. Fine-tuning to own the structure

*A plan; nothing in this section is built.* It sequences as R20 in [ml-roadmap.md](ml-roadmap.md#r20-small-models-first-and-fine-tuning-to-own-the-structure).

### What we own that no general model has

| Structure | Where it lives | What it teaches |
|---|---|---|
| The typed graph: entities, subentities, interactions with existence, effect sizes, and kernels | `model/`, committed versions | Our ids, kinds, units, and which values can move which |
| Superentity patterns, with roles and rivals | long-term memory (`object_generalizations`) | Recurring configurations, by name |
| The review ledger: each proposal, the reviewer's decision, per-operation keep and confidence, and edits (`edited_from`) | `repo/ledger.py`, `repo/review.py` | What a person accepts, and how they correct a machine reading |
| Bundle signals with quotes (`axelrod.import/v1`) and hand-drawn translations with phrase spans | `intake/bundle.py`, `data/scenarios/*/translations/` | Text aligned to operations, span by span |
| Forecasts with their outcomes and evaluations | `FORECAST`, `OUTCOME`, `EVALUATION` ledger entries | Which structure predicted well |
| Daily state: every value's level and spread, every day | working memory, snapshots | State transitions, for P3 |

A general model sees this structure only through a prompt (`LLMTranslator.build_prompt` sends the vocabulary, the taxonomies, the patterns, and every entity on each call). Fine-tuning puts it in the weights of a model we own.

### Phases

| | P0 · Datasets | P1 · Decision models and encoders | P2 · A small structured generator | P3 · A JEPA-style state predictor |
|---|---|---|---|---|
| **Learns** | Nothing: collects and versions | Typed decisions with calibrated probabilities: linking, signal type, direction and size, conflict, triage, review confidence; interaction typing | Market event → `axelrod.import/v1` signals and `GraphUpdateEvent` operations | The embedding of the world model's state at $t + h$ from its state at $t$ |
| **Data** | Ledger, imports, fixtures, snapshots (below) | D1–D4 | D2, D3, with D4 as the reward for preference tuning | D5 |
| **Model** | — | One shared encoder (100–400M) with a head per answer type (Choice, Score, Noul); a bi-encoder for candidate retrieval; CRF; gradient-boosted baselines | An open-weight instruction model of at most 8B, tuned with LoRA or QLoRA, decoded under the JSON schema | A graph or set encoder over values (about 10–50M), a predictor, and an EMA target encoder, trained in embedding space |
| **Metric** | Coverage and leakage audits | Linking recall@4 and accuracy@1; signal-type macro-F1; expected calibration error and Brier score per question | Agreement with reviewers' final operations on held-out reviews; schema validity; dropped-signal rate | Analog hit rate on held-out shocks; anomaly AUROC on worlds with planted breaks; precision@k of proposed interactions |
| **Acceptance bar** | Every example traces to a ledger sequence number; no test example precedes a training one | Linking recall@4 ≥ `alias_fuzzy` + 10 points and accuracy@1 ≥ 0.95 on named mentions; signal-type macro-F1 ≥ 0.85; calibration error ≤ 0.05 after recalibration; every question of an item answered in one pass, under 20 ms on a CPU | Approved-unchanged rate within 2 points of the large-LLM fallback on the held-out period; 100% schema-valid; p95 latency under 2 s on one GPU; cost per item at least 20× lower | Beats signature Jaccard on analog hit rate (cognition.md ablation); anomaly AUROC ≥ 0.8; proposals it ranks first pass R2's test more often than the frontier's own order |
| **Plugs into** | A planned `axelrod dataset export` command | Planned slot `decision_model` (ours, a hosted one, or a large model wrapped to answer typed questions), read by `entity_resolver`, `triage`, `review_ranker`, and the translators; a `label_family` classifier behind `classifier` | A `translator: small_extractor` entry ahead of `llm` in the `translators:` chain | Planned slot `state_encoder`, read by `recaller` (analogs), `frontier` (candidate order), and the open-world display |

The thresholds are starting bars, to be revisited once D1–D4 hold a few thousand reviewed items.

### P0 · Collect and version the datasets

| Set | One example | Source |
|---|---|---|
| D1 · Linking | (mention, its sentence, constraints) → entity or subentity id, or "open" | Bound mentions; approved `REFINEMENT` resolutions; edits that changed a target |
| D2 · Spans and signals | Text → spans with signal type and operation index | Hand-drawn translations, template spans, bundle quotes found in the text |
| D3 · Operations | (market event, model at the version before it) → the operations the reviewer kept, with edits applied | Proposals with `REVIEW_DECISION`, `edited_from`, and staging `keep` |
| D4 · Review outcome | (proposal features, operation) → kept unchanged, edited, or dropped | The same entries, plus `review_reasons` |
| D5 · State transitions | (state at $t$, state at $t + h$), each value's observation where one exists | Snapshots, and raw observations (R0); in synthetic worlds, the true state |

- **Schemas.** Each set is a versioned pydantic schema next to the code; a row records its ledger sequence numbers and the state version it was read at.
- **Splits by time.** Train on items decided before a cutoff, validate on the next window, test on the one after, so no model sees the future of what it is scored on. D1 also has an entity-held-out split, for names first seen after the cutoff. Syndicated copies of one story stay in one split.
- **Leak-free inputs.** An example's input is the model as it stood before the event (`as_of` its version, from the snapshots), never the committed state after it.
- **Client data never leaves the client.** Datasets, weights trained on them, and fallback logs stay in the client's environment and out of this repository. The repository holds only code, schemas, and synthetic examples. Only aggregate metrics leave, and only by agreement.

### P1 · Our own decision models

The open counterpart of a hosted System One model, trained on structure only we hold.

- **Shape.** One encoder reads the state (the item, its sentence, the candidate ids with their names and kinds) once; a head per question answers it: a softmax over a Choice's options, an ordinal head for a Score, a sigmoid for a Noul. Every question of an item is answered in the same pass, as Jev does. Choices over ids are scored against the candidates' own encodings, so a new entity needs no retraining.
- **Objective.** Proper scoring rules (log loss for Choices and Nouls, ranked probability score for Scores), which reward honest probabilities. That is the aim RLCD names; a proper scoring rule reaches it by supervised training, with recalibration on the validation window to finish.
- **Labels.** Reviewers' decisions (D1, D3, D4). Before there are enough, soft labels from a large model or a hosted decision model on synthetic and public items start the heads, and reviewed items replace them as they accrue.
- **Retrieval.** A bi-encoder trained contrastively (each mention against its approved id, hard negatives of the same kind) supplies the top candidates the Choice decides among.
- **Spans.** A CRF or token tagger marks the subject, magnitude, unit, and timeframe (D2); the decision model reads the marked sentence.
- **Interaction typing.** A classifier from a link's label and its ends' attribute kinds to the interaction generalization, replacing `label_family`'s keyword table.
- **Audit.** The protocol [above](#decision-models-jev-type), per question, on the held-out window, beside a hosted decision model and the large-LLM fallback on the same items where the data allows.

### P2 · A small model that emits our schema

- **Model.** An open-weight instruction model of at most 8B, with a licence that permits on-premises use, tuned with LoRA or QLoRA on D3.
- **Output.** `TranslationResult` JSON, either import signals or `GraphUpdateEvent` operations. Decoding is constrained to the JSON schema (grammar-constrained decoding), so every output parses; ids are constrained to the graph's own.
- **Context.** The candidate ids from P1's encoder, not the whole graph, so the prompt stays short.
- **Preference tuning, optional.** Kept-versus-dropped operations from D4 form preference pairs.
- **Harness.** Replay the held-out period: for each event, restore the version before it, run the candidate translator, and compare with the reviewer's final operations. Report agreement by operation type, dropped signals, latency, and cost, beside the large-LLM fallback on the same events.

### P3 · A JEPA-style predictor of world-model state

- **Idea.** A joint-embedding predictive architecture predicts the *representation* of a target from the representation of its context, rather than reconstructing the target (LeCun, 2022; Assran et al., 2023). Here the context is the state at $t$ and the target is the state at $t + h$.
- **Input.** Each value's standardized level and recent changes, its kind, and its place in the graph; masked values and masked horizons serve as targets.
- **Training data.** Raw observations, never the filter's points, and the true state in synthetic worlds (ground rule 1 of the roadmap). Trained on filtered values, it would learn the engine's own predictions back.
- **Uses**, each a ranking or a proposal, never a forecast:
  - **analog recall**: nearby states retrieve past episodes (F8);
  - **anomaly detection**: a large prediction error marks what the graph does not explain, for the open-world measures and the frontier's movers;
  - **a prior for interaction proposals**: a source whose masking hurts the prediction of a target most is tested first.
- **Separated from the causal engine.** Its outputs never enter the filter, the Monte Carlo, or a scenario weight. A pair it suggests passes R2's test and a person's review like any other. The causal engine stays the source of truth for forecasts.

### How a model is swapped in

Every phase lands behind a slot, chosen by config, so it can be compared by ablation on the same history and seed ([cognition.md](design/cognition.md#how-to-test-the-claim)):

```yaml
translators:
  news: [hand_drawn, template, small_extractor, llm]   # small_extractor: P2 (planned); llm last, logged
components:
  decision_model: own              # P1 (planned slot): own | hosted (e.g. Jev, where a client allows) | llm_typed
  entity_resolver: biencoder        # P1 (planned); alias_fuzzy today; the decision model weighs its candidates
  triage: decision_model            # P1 (planned slot)
  review_ranker: decision_model     # P1 (planned slot)
  state_encoder: jepa               # P3 (planned slot)
```

A model's weights and the dataset version it was trained on are to be recorded (planned) in the change set of anything it produced, so a reviewer, and an audit, can tell which model read which event.
