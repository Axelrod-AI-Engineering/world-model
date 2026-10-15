# The ML roadmap: from heuristics to methods we can defend

[ml-stack.md](ml-stack.md) states what the code computes today and what an adversarial review found wrong with it (§13 there). This page is the plan: for each problem, the method that replaces it, why it is sound, what it assumes, and the test that says it works. It was revised after the same review, which corrected several of its first claims; those corrections are noted where they apply. Nothing here is in the front end yet.

## Ground rules

1. **Truth is observed, never filtered.** Every score, fit, and test compares against raw observations (with the forecast's spread widened by observation noise) or, in synthetic worlds, against the world's true state. Nothing is ever scored against the model's own filtered values.
2. **Each observation is used once per posterior.** Every derived statistic records the observations it consumed. A later step may not add those observations again: analogs, kind priors, hedge shares, scenario weights, and track records all obey this rule.
3. **Misspecified and null worlds, then real vintages.** A method is judged first by recovery and calibration on synthetic worlds built *differently* from the model (R16), including worlds with no edges at all. Only then is it judged on real, point-in-time data (R15), against simple baselines, with proper scores (R10).
4. **Prices and fundamentals are different things.** Traded values (prices, yields, spreads, volatility) respond to surprises at once. Fundamentals (margins, CPI, capex) respond to realized changes with lags. The model treats them differently (R13).
5. **People stay in the loop.** Every structural change remains a proposal a person reviews. Better statistics change what is proposed and how it is described. They also change how much the proposal's numbers can be trusted; they do not change who decides.
6. **The smallest model that does the job.** Rules, classical ML, small embedders, finetuned classifiers, and decision models (typed, calibrated answers, Jev-type) come first; a large LLM is the logged fallback for the long tail (R20).

## Phase 0: stop the model confirming itself

### R0. Score against observations

**Problem.** The backtest, kernel learning, and scenario fit compare against the live engine's filtered values, which are pulled toward the model's own predictions (S-C1).

**Method.**
- Store every raw observation with its noise.
- Score a forecast's predictive distribution, its level spread plus observation noise, against the raw observation.
- In synthetic worlds, score against the world's true state as well.
- Kernel learning and scenario fit use the Kalman filter's one-step-ahead prediction-error decomposition on raw observations, not differences of filtered points.

**Test.** On a world where the model is deliberately wrong, the score must get worse, not stay flat.

### R18. Provenance: each observation once

**Problem.** Several steps count the same data more than once:
- analog prefill pools a channel's own history with its own posterior, enters a day once per overlapping episode, and keeps only same-sign siblings (S-C3);
- kind statistics are pushed per touch (S-C4);
- fuzzy-end shares count article volume and count a co-movement both in the share and in the fold (S-M8);
- scenario weights multiply support, in-sample fit, and backtest track records (S-M5).

**Method.**
- **Analogs** come only from other channels or entities, or from held-out periods. Each day is assigned to at most one episode. Sign heterogeneity is modeled hierarchically, not filtered.
- **Kind statistics** keep one sufficient-statistic entry per item, replaced and never appended (see R5).
- **Fuzzy ends** get likelihood-based responsibilities: one Kalman predictive per candidate, so a co-movement's weight depends on its size and on the other drivers. Distinct sources are counted, not articles. The candidates are sampled as one categorical draw over the candidates and the open reserve, on one substream, so two never act at once.
- **Track records** are kept strictly out of sample (R7).

**Test.** A provenance audit: for each posterior, the multiset of observations it used has no repeats.

## Phase 1: measure and model markets properly

### R3. Units: estimated scales and native-unit reporting

**Problem.** Scales are set once at creation and never estimated, so "1 sd" means different things for different values, and every threshold inherits the inconsistency (F-C3, S-M9).

**Method.**
- **Transforms.** Make each value's transform explicit in its kind:
  - log-returns for prices and indices;
  - changes for yields;
  - levels for spreads;
  - discrete step processes for policy rates.
- **Scales.** Estimate each value's scale from its own series as the horizon-specific realized volatility (EWMA, with a regime-aware option). Store the scale with its vintage, and rescale effects when scales change: $\beta_{\text{new}} = \beta \cdot (s_{a,\text{new}}/s_{a,\text{old}}) \cdot (s_{b,\text{old}}/s_{b,\text{new}})$.
- **Reporting.** Report every effect in native units (bp, %, $) next to the horizon volatility, as effect$/\sigma_H$.
- **Thresholds.** Every threshold becomes a statement in volatility units at the relevant horizon.
- **Kernel shapes.** Derive them from the transforms, so stocks and flows stay consistent: a level-to-rate link needs a differencing (transient) kernel, and a rate-to-level link needs an integrating one.
- **Cointegration.** Where levels share a long-run relation, use an error-correction form rather than differencing it away. Unit-root pretests (ADF with KPSS) have low power, so they inform the choice; they do not make it.

**Test.** On simulated random walks with no true link, the learned effect's 95% interval covers zero about 95% of the time.

### R14. Factor structure and investable group readouts

**Problem.** There is no market factor: a market shock moves no stock in the book, level shocks are independent across names, and a 50-name book's risk is understated several-fold. Group forecasts average values of different signs and units (F-C2).

**Method.**
- **Factors.** Model traded values in returns with a contemporaneous factor structure: market, sector, rates, the dollar, and oil. The covariance is $\Sigma = BB^\top + D$, with loadings estimated from returns on rolling windows. The factor shocks are drawn per Monte Carlo sample, on shared substreams.
- **Groups.** A group's financial readout is the value-weighted or portfolio-weighted return of its share prices only. Fundamentals groups are reported separately, with an explicit sign convention ("good or bad for holders").

**Test.** On backtests, portfolio-level interval coverage, and VaR and expected-shortfall backtests (Kupiec; Christoffersen).

### R13. Expectations and pricing-in

**Problem.** Everything has at least a one-day delay and usually a multi-week ramp. Releases are read as levels, anticipated policy moves are treated as shocks, and a 28-day momentum drift is extrapolated into prices. The model therefore forecasts large post-news drift, a claim of exploitable predictability no desk would accept (F-C1, F-M4, S-M4).

**Method.**
- **Expectation nodes.** Add a consensus for each scheduled release, so that surprise = actual − consensus. Policy expectations come from the OIS or fed-funds-futures path, and oil expectations from the futures curve.
- **Impact and drift for traded values.** Traded values get an impact term at lag 0, driven by the surprise. Drift is a separate, learned term, labelled as a predictability claim and tested out of sample (R10). The default kernel for a price target is delay 0, lag 1.
- **Interventions.** A thesis is stated against the priced path: "rates stay where they are" means the gap between no change and the forwards.
- **Baselines.** Prices get no drift (or a carry or risk-premium term). Trends stay only for slow macro series where a backtest supports them.
- **Identification.** Identified surprise series give event studies something to identify with. Examples: OPEC-announcement oil surprises (Känzig, 2021) and high-frequency monetary surprises (Kuttner, 2001; Gürkaynak, Sack and Swanson, 2005).

**Test.** In event windows, the forecast's split into impact and drift should match the realized cumulative abnormal returns over [0, 1] and [2, 60] days. The claimed drift must be significant out of sample, or it is set to zero.

### R15. Point-in-time and mixed-frequency data

**Problem.** Observations are dated by release, with no reference period, vintage, or revision, and quarterly fundamentals sit on a daily grid. On real data, publication lags become spurious "delays", and stamping values at their reference date is look-ahead (F-M1, S-M12).

**Method.**
- **Fields.** Every observation carries `reference_period`, `release_ts`, and `vintage`, in an ALFRED-style vintage store.
- **Assimilation.** Use mixed-frequency state space, with temporal aggregation for flows.
- **Calendars.** Align markets by their close, and test lags 0 and 1 jointly, so non-synchronous trading is not mistaken for lead-lag.
- **Backtests** run on vintages only.

**Test.** A publication-lag world (R16): learned delays should not absorb the reporting lag.

### R16. Worlds built to break the model

**Problem.** The synthetic world uses the model's own kernel family, its linear structure, and true effects centered on the model's priors. Recovering them proves self-consistency only (F-C4, S-E6).

**Method.** A suite of worlds, each with a known truth:
1. random-walk log prices with Student-$t$ GARCH noise and a factor structure;
2. latent common drivers (no causal sufficiency);
3. anticipation: announced events move prices before they happen;
4. publication lags and revisions;
5. kernel shapes outside the model's family, and time-varying and regime-dependent effects;
6. **null worlds** with no edges, and placebo worlds with shuffled series.

Every learner reports its false-discovery and recovery rates on each.

**Test.** This is the test bed for every other item.

### R10. Evaluation that would convince a desk

**Method.**
- **Rolling-origin backtests** on point-in-time vintages (R15), scored against raw observations (R0).
- **Proper scores from samples.** Use CRPS with the unbiased estimator $\frac{1}{n(n-1)}\sum|X_i - X_j|$ for its spread term, plus the log score. Report PIT histograms and coverage by horizon, with coverage intervals that account for autocorrelated days.
- **Baselines**:
  - a random walk in returns;
  - futures- and consensus-implied paths;
  - rolling factor betas;
  - a Bayesian VAR with a Minnesota prior, or a FAVAR (an unrestricted VAR on about 100 values is infeasible);
  - local projections (Jordà, 2005) on identified shock series (R13).
- **Baselines get the same information.** When a backtest feeds the realized shocks as the thesis (an oracle), it is a *conditional* transmission test. It is reported as such, never as forecast skill.
- **Comparisons.**
  - Diebold–Mariano tests (1995) with HAC variance and the Harvey–Leybourne–Newbold correction for overlapping horizons.
  - Clark–West for nested models (the graph against a reduced graph).
  - Giacomini–White (2006) for rolling windows.
  - The Model Confidence Set (Hansen, Lunde and Nason, 2011) across many models.
- **Desk metrics**:
  - event-study cumulative abnormal returns against a market model, split into what was priced and the claimed drift;
  - cross-sectional information coefficient;
  - direction hit rate with a binomial test;
  - a long–short portfolio sorted on predicted exposure, net of costs, with Sharpe ratio and drawdown;
  - VaR and expected-shortfall backtests.
- **Posterior predictive checks**: innovation whiteness (Ljung–Box), the normalized innovation squared, and daily one-step PIT. The frontier relies on white innovations.

## Phase 2: discovery with error control

### R2. The frontier, and superentity induction, with valid tests

**Problem.** Both select on the outcome and reuse the selecting data, and neither has a test with known error. The frontier promotes on a bar a null pair passes about one time in eight per selected pair. The induction's sign test passes by construction on unobserved targets (S-M6, S-C2).

**Method.**
1. **Only observed, out-of-sample quantities.** Use innovations from observed days only, computed with effects frozen before the test window.
2. **Residualize** on the current graph's predictions and on the factors (R14). Without this, the frontier rediscovers the market.
3. **Test** conditional independence of the target's innovation and the source's lagged change, given the target's parents.
   - The null distribution comes from residual permutation (Freedman–Lane) or a conditional randomization test (Candès et al., 2018; Berrett et al., 2020).
   - *Correction from the review:* plain block permutation of the source is not a valid null for a partial correlation, because it breaks the source's dependence on the conditioning set.
   - If the innovations are confirmed white, a prewhitened parametric test is enough (Haugh, 1976).
4. **Test sequentially, with error control.** Pairs are re-tested as data arrive, so a batch FDR procedure over a window does not control error under continuous monitoring (*corrected from the first draft*, which proposed Benjamini–Yekutieli). Use anytime-valid e-values (Howard et al., 2021) with online FDR control: LORD or SAFFRON (Javanmard and Montanari, 2018; Ramdas et al., 2018), or e-BH (Wang and Ramdas, 2022). Each proposal records its e-value.
5. **Causal claims need more.**
   - PCMCI (Runge et al., 2019) assumes causal sufficiency, stationarity, and faithfulness, and market data have latent drivers. Where an algorithm is used, prefer LPCMCI (Gerhardus and Runge, 2020), which allows latent confounders, and PCMCI+ (Runge, 2020) for same-day links.
   - In any case, the proposal says "lagged dependence not explained by the current graph or the factors", and a person decides.
6. **Superentity induction** gets the same treatment:
   - observed changes only;
   - contributions computed with effects frozen before the window;
   - a null from sign- or block-permuted contributions;
   - online FDR across the components scanned.

**Test.** On null and latent-confounder worlds (R16), the realized false-discovery proportion is at most about the target level $q$. Recall of planted edges is reported as a function of history length.

### R11. Evidence types

A learned edge is a statement about predictive dependence given what the graph already knows. It becomes a causal claim only with an identifying argument: an event study on a dated *surprise* (R13; an announced change is mostly priced already), an instrument, or domain knowledge entered by a person.

Each interaction records its evidence type, which the review and the forecast show:
- constructed;
- reported in an article;
- learned from co-movement;
- confirmed by an event study.

## Phase 3: one model, with honest uncertainty

### R1. Existence: one model for filter and forecast, with inclusion probabilities

**Problem.**
- The filter uses every channel at full strength, while the forecast switches channels off. The two are different models (S-M2).
- The existence pseudo-count re-adds the prior and cannot learn absence (S-M1).
- Reported changes train the in-channels (S-M7).

**Method.**
1. **Filter with the mixture.** A channel contributes $\mathbb{E}[p]\mu$, with variance $p(1-p)\mu^2 + p\sigma^2$. Better: use a Gaussian-sum or interacting-multiple-model filter over the channels' on/off states.
2. **Track inclusion by sequential model comparison.** Each channel's log-odds accumulate the log ratio of one-step-ahead predictive densities of filters with and without it.
   - *Corrected from the first draft*, which called this exact. It is the exact marginal-likelihood ratio only when the hyperparameters (level noise, observation noise, the effect random walk, the kernel) are fixed and not learned from the same data; when the regressor is a known exogenous series (here it is built from a filtered source, so it is a generated regressor); and when both filters run from the channel's inception.
   - With several channels, conditioning the others on their current means is an approximation, and it fails for collinear sources. Exact enumeration of $2^n$ filters is feasible for $n \le 4$; its cost is $O(2^n n^3)$ per target-day, not "as now".
   - Inclusion probabilities are sensitive to the slab width (the Lindley–Bartlett effect) and to the effect random walk, which penalizes the "on" model each step. Both need priors or calibration.
3. **Reported changes enter as shocks**, updating only the level, never the effects.

**Test.** Calibration of inclusion probabilities (of channels given 0.8, about 80% real) on R16 worlds, including null worlds, where they must fall.

### R17. Hyperparameters by marginal likelihood

Observation noise, level noise, the effect random walk, and the scales are fixed by kind today, so only their ratios are identified, and wrongly (S, minor). Estimate them per value by maximizing the prediction-error-decomposition likelihood, or by EM for state-space models (Shumway and Stoffer, 1982). Re-estimate on a schedule, with provenance (R18).

### R4. Kernels: a posterior, not a three-point grid

Keep a discretized posterior over (delay, lag) on a log grid of about 8×8 per channel, and over the duration on a one-dimensional grid. Score each grid point by the Kalman marginal likelihood, integrating the effect jointly (*corrected*: not first differences of filtered values), and with the MA(1) structure of differenced noisy observations. The reported mean and CV come from the posterior, so the CV shrinks only when the data are informative. Monte Carlo draws come from the grid.

**Test.** Recovery and interval calibration of planted kernels, including kernels outside the family (R16).

### R6. Ripple judgments as a mixture that learns

Represent each judged ripple as a two-component mixture (it arrives, or it does not), with prior weight $w$ applied to the *mean* path, not a median that already integrates existence. Run a Gaussian-sum filter that updates $w$ as the target is observed. Apply the same switch in the Monte Carlo, on a shared substream, so forecasts carry the judgment too (today they ignore it).

**Test.** With $w = 0.5$ in a world where the ripple arrives half the time, forecast coverage holds and $w$ converges toward the truth.

### R9. Market-realistic noise

In order:
1. **Joint parameter draws.** Draw $[a, \beta]$ per target from $\mathcal{N}(\theta, P)$, and start from the posterior of today's state, not from a fixed point.
2. **Common factors** in level shocks (R14).
3. **Volatility clustering.** A GARCH(1,1) scale, for daily-observed values only; it is meaningless for monthly releases.
4. **Heavy tails.** Student-$t$ innovations.
   - Unconditional daily single-stock returns have tail indices of about 3 to 5 (Cont, 2001). GARCH-standardized residuals are lighter, with degrees of freedom around 5 to 10.
   - Combining $t$(3–6) with GARCH would double-count tails.
   - Over a 182-day horizon, daily $t$ shocks aggregate toward Gaussian, so long-horizon tails come from volatility persistence, event-day jumps, and regimes.
5. **Regimes** (Hamilton, 1989), with stress-dependent correlation. Crisis-correlation estimates conditioned on high volatility are biased upward (Forbes and Rigobon, 2002).

**Test.** PIT and tail coverage on R16 worlds and backtests.

## Phase 4: structure and inference

### R5. Kinds as a hierarchical model

**Method.**
- A kind's members' effects follow a measurement-error hierarchy: $\hat b_i \sim \mathcal{N}(\theta_i, se_i^2)$, $\theta_i \sim \mathcal{N}(\mu, \tau^2)$, with $\tau^2$ estimated. A new member's prior is the posterior predictive, so its width reflects how much members truly differ.
- One entry per item (R18).
- A new edge's existence prior has a bounded concentration, for example $\alpha + \beta \le 2$.
- The tree's shape can still grow by Cobweb-style operators (Fisher, 1987), with Classit's acuity floor for numeric attributes (Gennari, Langley and Fisher, 1989). But category utility is a heuristic and order-dependent, and restructuring changes members' priors after the fact. So it proposes structure, and the hierarchical likelihood decides.

**Test.** Held-out prior predictive log score for new members.

### R7. Scenario weights by out-of-sample prediction

**Method.**
- Score every rival on the same set of values (the union of their targets), with the shared baseline standing in where a rival is silent.
- Use leave-future-out predictive densities (Bürkner, Gabry and Vehtari, 2020), not in-sample fit.
- *Corrected from the first draft:* for this misspecified, M-open setting, Yao, Vehtari, Simpson and Gelman (2018) recommend **stacking**, or pseudo-BMA+ with the Bayesian bootstrap, over Bayesian model averaging; "tempered BMA" is not their proposal.
- For a CRPS objective, use CRPS-optimal pools. Linear pools of calibrated components are over-dispersed, which a beta-transformed linear pool corrects (Ranjan and Gneiting, 2010; Gneiting and Ranjan, 2013).
- Track records enter only out of sample (R18).

**Test.** The combined forecast against the best single rival, by Diebold–Mariano or Giacomini–White. Combination is not guaranteed to win.

### R8. Value of information for the forecast's loss

For a hypothesis $h$ and a proper score $S$ with generalized entropy $H(F) = \mathbb{E}_F S(F, Y)$, the value of resolving $h$ is $H(F_{\text{mix}}) - \sum_h p_h H(F_h) \ge 0$ (Gneiting and Raftery, 2007; Dawid, 2007). It is computed from the on/off Monte Carlo runs, with the unbiased estimator of $\mathbb{E}|X - X'|$ for CRPS.

*Corrected from the first draft:* this is the expected value of *perfect* information for a CRPS-scored forecast. It is an information gain only under the log score, where it equals the mutual information $I(h; Y)$.

Two refinements follow:
- Resolution usually comes from noisy data, so the target is the expected value of sample information.
- Sums across watched values must be in comparable units (R3), or replaced by a desk's own loss.

### R12. Transmission by path effects

**Method.**
- **Linear part.** Path-specific effects are exact by path tracing (Wright): along each path, the product of the effects times the convolution of the kernels, summed over paths. Report the paths that carry most of each value's effect, and place a value in the grid by the hop count of that path.
  - *Corrected from the first draft*, which proposed Shapley values over edge ablations. Those are not path-specific effects (Pearl, 2001; Avin, Shpitser and Pearl, 2005), so they are kept only for the nonlinear parts: moderators and bounds.
- **Readouts.** Report each value with:
  - its **mean** effect;
  - $P(|\Delta| \ge$ threshold$)$, so that low-probability large effects show;
  - effect$/\sigma_H$ (R3);
  - the probability that the realized move has the predicted sign, *including outcome noise*;
  - time to 50% of peak in place of the sum of delays.

The transmission grid's "strongest paths" view already ranks paths by linear gain ($\prod \mathbb{E}[p]\mu$, without the kernels). It is the first step of this item.

### R19. Economic structure

Review findings F-M2, F-M3, and F-M5 are about the demo world's economics rather than its statistics. They are fixed in `data/worlds/economy/`, with each change tested on backtests.

**Airlines.**
- Separate the jet-fuel spot price (a market price, with a crack-spread driver) from realized fuel cost per gallon (quarterly, with hedge-ratio and refinery moderators that differ by firm).
- Add a same-day oil-to-airline-equity exposure estimated from returns.
- Add fare and capacity pass-through, which makes the margin effect transient.
- Drive share prices from earnings surprises.

**Policy.**
- Taylor-type reaction functions on core inflation and slack, with each bank reading its own region's data.
- Meetings as a discrete process: an ordered probit over steps, on the calendar's dates.
- Policy-rate forecasts anchored on OIS.

**Regimes.**
- Regime moderators: curve slope and stress.
- A convex, asymmetric volatility response.
- Same-day blocks for market variables, including two-way causality between volatility and positioning.
- Transient defaults for margins and flows.

## A parallel track: small models and owned structure

### R20. Small models first, and fine-tuning to own the structure

**Problem.** The only language model in the code is a stub (`translator: llm`). Text is read by fixtures and regular expressions, which cover only what someone wrote a rule for. Filling the gap with a large LLM on every call would put client text on a third party's servers, make readings non-deterministic, and cost per item what a small model costs per thousand. It would also leave our structure in prompts rather than in models we own.

**Method.** [ml-stack.md, Small models first](ml-stack.md#small-models-first) assigns each step its smallest adequate model, with a large LLM last and logged; [ml-stack.md §14](ml-stack.md#14-fine-tuning-to-own-the-structure) gives the fine-tuning plan. Its milestones, in order:

| Milestone | Delivers | Needs first | Done when |
|---|---|---|---|
| R20.0 · Datasets (P0) | D1–D5, versioned, split by time, built inside the client's environment | R18 (provenance), so each example records the observations it used | A leakage audit passes: no test example precedes a training one, and every example traces to a ledger entry |
| R20.1 · Fallback chain | `llm` last in each `translators:` chain, every call logged with its review decision; quote alignment and conflict rules | R20.0 | Fallback cases appear in D3 with their outcome |
| R20.2 · Decision models (P1) | A `decision_model` slot; our own typed, calibrated decision models for linking, signal type, conflict, triage, and review confidence, compared with a hosted one (Jev) on synthetic and public items; bi-encoder retrieval; interaction typing | R20.0 | The P1 bars in ml-stack §14 on the held-out period, including calibration error after recalibration |
| R20.3 · Small structured generator (P2) | A ≤ 8B LoRA model emitting `TranslationResult` under constrained decoding | R20.2 (candidate ids), and a few thousand reviewed items | Approved-unchanged rate within 2 points of the large-LLM fallback, at a fraction of its cost |
| R20.4 · JEPA-style state predictor (P3) | A state encoder for analogs, anomalies, and candidate order | R0 (raw observations), R15 (point-in-time data), R16 (worlds to test on) | Beats signature Jaccard on analog recall, and its candidate order raises R2's pass rate, on R16 worlds |

**Boundary.** A decision model's calibrated probabilities may weigh *readings* of text (which candidate, which signal, how sure the reading is), after the calibration audit. None of these models computes an effect, a kernel, a forecast, an existence belief, or a scenario weight, and none applies a change a person must review. R20.4 in particular only ranks and proposes; the causal engine stays the source of truth.

**Test.** Each milestone is an ablation behind its slot: the same history on the same seed, with and without the model.

## Phases

| Phase | Items | Why |
|---|---|---|
| 0. Stop self-confirmation | R0, R18 | Every later result is judged by these |
| 1. Measure and model markets | R3, R14, R13, R15, R16, R10 | Units, factors, pricing-in, and honest test beds come before any claim |
| 2. Discovery | R2, R11 | The largest source of false structure |
| 3. One honest model | R1, R17, R4, R6, R9 | Filter and forecast agree; uncertainty means what it says |
| 4. Structure and inference | R5, R7, R8, R12, R19 | Long-term memory, scenarios, readouts, economics |
| Parallel. Small models and owned structure | R20.0 with R18, then R20.1–R20.3; R20.4 after R0, R15, R16 | Reading text without a large LLM; models trained on our ids and reviews |

## How this was reviewed

Three adversarial reviewers, each an independent agent, read [ml-stack.md](ml-stack.md), this page, and the code, with instructions to break them:
1. **Fidelity**: does every formula and constant match the code?
2. **Statistics**: are the methods and these proposals sound, and are their claims and citations right?
3. **Finance**: are the assumptions grounded in how markets and economic data behave, and would a practitioner trust the outputs?

Their findings are in [ml-stack.md §13](ml-stack.md#13-adversarial-review).

The statistics reviewer corrected six of this page's first claims; the corrections are marked in R1, R2, R4, R7, R8, and R12. The other citations, both reviewers confirmed, are correct:
- Granger and Newbold, 1974;
- Fisher, 1987;
- Gennari, Langley and Fisher, 1989;
- Runge et al., 2019;
- Jordà, 2005;
- Diebold and Mariano, 1995;
- Yao et al., 2018.
