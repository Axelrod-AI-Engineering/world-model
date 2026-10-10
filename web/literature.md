# Causation, prediction, and concept formation: a literature review

*Axelrod World Model · October 2026 · the Literature tab of the demo; How it works shows the flowcharts, and Implementation the ML stack*

The Axelrod World Model keeps an evidence-backed, evolving causal state of markets, companies, macro variables, policies, and events, and it answers what-if questions against that state. The job sits where three literatures meet: causal inference, the psychology of causal reasoning and concept formation, and macroeconomic and financial forecasting. This review covers all three.

- **Part I** is a primer on correlation, causation, and prediction, followed by an annotated reading list on causal inference.
- **Part II** describes the model's methods and reviews the literature each one borrows from.
- **Part III** places each part of the model on Pearl's ladder of causation, states the assumptions each step needs, and lists open problems.

The reading list in Part I began as a short list compiled for the team. In it, ⁺ marks works this review added, and *In the model* notes point to where a work bears on the design. Every reference was checked against its publisher, Crossref, arXiv, or proceedings record (see the note at the end).

---

# Part I. Correlation, causation, and prediction

## 1. Primer

### 1.1 Correlation versus causation

Correlation means two variables move together in observed data. Causation means that changing one changes the other. A correlation between X and Y can come from four structures.

| Structure | Graph | Example |
|---|---|---|
| X causes Y | X → Y | Higher oil prices raise airlines' fuel costs. |
| Y causes X | X ← Y | Rate hikes coincide with high inflation because inflation prompts the hikes. |
| A common cause (confounder) | X ← Z → Y | Strong global demand lifts both oil prices and chip orders. |
| Selection on a common effect (collider) | X → Z ← Y, with the sample selected on Z | Among firms in the news, strong earnings and a scandal look negatively related, because either one is enough to make the news. |

Reichenbach's (1956) common cause principle covers the first three structures. If X and Y are dependent and neither causes the other, they share a cause, and conditioning on it makes them independent ("screens them off"). The fourth structure is a sampling artefact, known as collider bias or endogenous selection bias (Elwert & Winship, 2014). The principle assumes it away.

### 1.2 Pearl's three levels

Pearl (2009; Pearl & Mackenzie, 2018) separates three kinds of causal question.

| Level | Activity | Query | What answers it |
|---|---|---|---|
| Association | Seeing | P(y \| x) | Observational data |
| Intervention | Doing | P(y \| do(x)) | A causal model (a graph and its assumptions) or an experiment |
| Counterfactual | Imagining | "Would Y have happened if X hadn't?" | A structural causal model, with mechanisms and their noise |

Data alone can't move you up a level. The causal hierarchy theorem makes this precise: data from a lower level almost never determine the answers on a higher one (Bareinboim et al., 2022). Moving up takes assumptions (a causal graph), randomization, or variation known to be exogenous, such as a policy surprise.

### 1.3 Predictability

Prediction doesn't require causal knowledge. If the world stays stable, a confounded correlation predicts fine. It breaks when someone intervenes or the distribution shifts, because the correlation was never what produced the outcome. Economics has a name for each failure:

- for policy, the Lucas (1976) critique: estimated relations change when the policy rule changes;
- for forecasting, forecast failure after structural breaks (Clements & Hendry, 1998).

Machine learning makes the same point about generalization under shift: the relations that stay invariant across environments are the causal ones (Peters et al., 2016; Schölkopf et al., 2021).

Granger (1969) causality is a predictive notion: X Granger-causes Y if X's past helps forecast Y beyond Y's own past and the other information used. It is not proof of causation, since a hidden common driver can produce it. It coincides with structural causation only when X is conditionally exogenous given what is observed (White & Lu, 2010).

Rule of thumb: prediction asks "what will I see?", and causal inference asks "what happens if I act?" (Hernán et al., 2019; Kleinberg et al., 2015).

### 1.4 In cognitive science

Causation enters cognitive science in two roles.

- **As a theory of the mind.** People appear to learn and reason with something like causal models, not just associations. They treat interventions differently from observations (Sloman & Lagnado, 2005; Waldmann & Hagmayer, 2005), and they use counterfactuals when assigning blame or credit (Gerstenberg et al., 2021; Lagnado et al., 2013).
- **As a problem of method.** Most psychology and neuroscience data are observational or correlational, so confounding, collider bias, and unclear mechanisms are everyday issues (Rohrer, 2018). Neuroimaging connectivity is a well-known example. On simulated fMRI networks, methods that read the direction of an influence from time lags, Granger causality among them, performed poorly (Smith et al., 2011).

## 2. Reading list

The groups follow the list this review started from.

### 2.1 Foundations

The foundations run from Hume's doubt that causation can be observed, through two formal languages for causal claims, to algorithms that learn causal structure from data. The two languages are potential outcomes and causal graphs, and they are compatible. Potential outcomes define an effect as a contrast between outcomes that cannot both be observed. Graphs say which of these contrasts the available data can identify.

- **Hume (1748/2008), *An enquiry concerning human understanding*.** We never observe causal connection, only regular succession, so causal belief is inferred. The 1748 first edition was titled *Philosophical Essays Concerning Human Understanding*.
- **Reichenbach (1956), *The direction of time*.** Introduces the common cause principle and the conjunctive fork, in which a common cause screens its effects off from each other. The book was published after Reichenbach's death.
- **Granger (1969), "Investigating causal relations by econometric models and cross-spectral methods."** Defines causality as predictive precedence relative to an information set. Useful and widely misused: leave a common driver out of the set and spurious causality appears. *In the model:* the correlation frontier tests lagged dependence in this sense, and it promotes nothing without review (§5.4).
- **Rubin (1974), "Estimating causal effects of treatments in randomized and nonrandomized studies."** The potential outcomes framework. A causal effect compares the outcomes a unit would have under two treatments, and only one of them is ever observed. Randomization makes the comparison unbiased on average; nonrandomized studies need assumptions about how treatment was assigned.
- **⁺Holland (1986), "Statistics and causal inference."** Names the fundamental problem of causal inference (one observed outcome per unit) and argues for "no causation without manipulation." *In the model:* a thesis is written as operations on the graph, such as a changed value or a held decision, so every what-if names its manipulation (§3.3).
- **Pearl (1995), "Causal diagrams for empirical research."** Causal graphs plus the do-operator. Gives graphical criteria (back-door and front-door) and a calculus for deciding when an interventional distribution can be computed from observational data.
- **Pearl (2009), *Causality* (2nd ed.).** The full treatment: structural causal models, identification, and counterfactuals.
- **Spirtes, Glymour & Scheines (2000), *Causation, prediction, and search* (2nd ed.).** Algorithms (PC and FCI) that learn causal structure from patterns of conditional independence, under the causal Markov and faithfulness assumptions. FCI allows for hidden common causes.
- **⁺Imbens & Rubin (2015), *Causal inference for statistics, social, and biomedical sciences*.** The standard text on potential outcomes: assignment mechanisms, randomized experiments, and inference under unconfoundedness.
- **⁺Eberhardt & Scheines (2007), "Interventions and causal inference."** Separates structural ("hard") interventions from parametric ("soft") ones, and shows what each reveals about causal structure. A hard intervention cuts a variable off from its causes; a soft one changes the variable's mechanism without cutting it. *In the model:* a held decision is a hard intervention, and a shocked value is a soft one (§7).
- **⁺Elwert & Winship (2014), "Endogenous selection bias: The problem of conditioning on a collider variable."** Conditioning on a collider makes its causes dependent, whether the conditioning comes from selecting the sample, stratifying, or adding a regression control. A graphical account with many worked examples.
- **⁺White & Lu (2010), "Granger causality and dynamic structural systems."** Granger causality and structural causality coincide when the candidate cause is conditionally exogenous given the observed covariates.
- **⁺Peters, Bühlmann & Meinshausen (2016), "Causal inference by using invariant prediction."** A target's causal parents are the predictors whose relation to it stays the same across environments. This yields confidence statements about causal structure.
- **⁺Bareinboim, Correa, Ibeling & Icard (2022), "On Pearl's hierarchy and the foundations of causal inference."** The causal hierarchy theorem: the three levels almost never collapse, so data from a lower level leave the answers on a higher one undetermined unless assumptions are added.

### 2.2 Causal reasoning in humans

Work on human causal learning has moved from associative accounts, in which people track contingencies, to model-based ones, in which people build causal structures and reason with them. Three distinctions recur, and the model keeps each one: causes versus effects, structure versus strength, and seeing versus doing.

- **Waldmann & Holyoak (1992), "Predictive and diagnostic learning within causal models."** Learning depends on whether cues are causes or effects: alternative causes compete for credit, and effects of a common cause do not. Purely associative models treat all cues alike, so they cannot explain this asymmetry.
- **Cheng (1997), "From covariation to causation: A causal power theory."** People infer a cause's power to produce its effect, not just how the two covary.
- **⁺Lu, Yuille, Liljeholm, Cheng & Holyoak (2008), "Bayesian generic priors for causal learning."** Human judgments of causal strength and structure fit a Bayesian model whose generic priors favor sparse and strong causes. *In the model:* each new interaction starts from its interaction generalization's prior (§5.2).
- **Steyvers, Tenenbaum, Wagenmakers & Blum (2003), "Inferring causal networks from observations and interventions."** People learn causal structure better when they can intervene. Their inferences, and their choices of which intervention to make, match Bayesian structure learning reasonably well.
- **Sloman & Lagnado (2005), "Do we 'do'?"** People treat an intervention as breaking the incoming causal links of the variable it sets, as the do-operator predicts. Sloman's *Causal models* (2005) is the book-length version.
- **⁺Waldmann & Hagmayer (2005), "Seeing versus doing: Two modes of accessing causal knowledge."** People predict differently after observing a variable than after setting it, in the way causal Bayes nets prescribe.
- **Griffiths & Tenenbaum (2005), "Structure and strength in causal induction."** Separates judging whether a link exists (causal support) from judging how strong it is, within a Bayesian framework. Many human judgments track support rather than strength. *In the model:* every interaction holds a belief that it exists, apart from its effect, and the hypothesis frontier asks about existence (§4.4).
- **Gopnik et al. (2004), "A theory of causal learning in children: Causal maps and Bayes nets."** Young children make interventions and inferences consistent with causal Bayes nets.
- **Körding et al. (2007), "Causal inference in multisensory perception."** The brain appears to infer whether two sensory signals share a cause, and it combines them according to that inference.
- **⁺Kemp, Goodman & Tenenbaum (2010), "Learning to learn causal models."** People learn causal schemata: categories whose members share causal properties. With a schema, a few observations of a new member are enough. *In the model:* an entity's kind supplies its default subentities and interactions (§4.2).
- **⁺Rottman & Hastie (2014), "Reasoning about causal relationships: Inferences on causal networks."** A review of how people reason on causal networks. People broadly follow causal Bayes nets but systematically violate the Markov (screening-off) condition.
- **⁺Bramley, Dayan, Griffiths & Lagnado (2017), "Formalizing Neurath's ship."** In online causal learning, people keep one working hypothesis and revise it locally, a piece at a time. *In the model:* the graph also changes one reviewed operation at a time (§5.4).
- **⁺Lagnado, Gerstenberg & Zultan (2013), "Causal responsibility and counterfactuals."** Judgments of responsibility track two things: how close a person's action came to being decisive (counterfactual pivotality), and how critical their role seemed beforehand.
- **Gerstenberg, Goodman, Lagnado & Tenenbaum (2021), "A counterfactual simulation model of causal judgments for physical events."** Causal judgments track mental simulations of what would have happened otherwise. *In the model:* a "Why" explanation simulates the forecast without each candidate interaction (§5.5).

### 2.3 Prediction versus explanation, and method

A model built to explain and one built to predict are optimized and judged differently. This literature argues for three practices: keep the tasks distinct, test predictions out of sample, and state causal assumptions openly.

- **⁺Breiman (2001), "Statistical modeling: The two cultures."** Contrasts two cultures: one models the process that generated the data, the other judges algorithms by predictive accuracy.
- **Shmueli (2010), "To explain or to predict?"** A model built for explanation and one built for prediction are optimized differently, and mixing them up causes errors.
- **⁺Kleinberg, Ludwig, Mullainathan & Obermeyer (2015), "Prediction policy problems."** Some decisions need only a good prediction, such as whether to carry an umbrella. Others need a causal effect, such as whether a rain dance brings rain.
- **Hernán, Hsu & Healy (2019), "A second chance to get causal inference right."** Splits data science tasks into description, prediction, and causal inference.
- **Yarkoni & Westfall (2017), "Choosing prediction over explanation in psychology."** Psychology often fits models to explain but never tests their predictions out of sample. Its explanatory claims are therefore weaker than they look.
- **Rohrer (2018), "Thinking clearly about correlations and causation."** A short, practical introduction to causal graphs for observational data. It shows which variables to adjust for, and which (colliders and mediators) to leave alone. Read this first if you read one method paper.
- **Grosz, Rohrer & Thoemmes (2020), "The taboo against explicit causal inference in nonexperimental psychology."** Researchers imply causal claims anyway, so they should state and defend them openly. Section 8 does this for the model.
- **Jonas & Kording (2017), "Could a neuroscientist understand a microprocessor?"** Standard neuroscience analyses fail to recover the known mechanisms of a system we fully understand, a microprocessor. A warning about correlational methods.
- **⁺Smith et al. (2011), "Network modelling methods for FMRI."** On simulated fMRI networks, several methods recovered which connections exist. Lag-based methods, Granger causality among them, did poorly, and the direction of a connection was hard to recover. This is a warning for any test that reads direction from time lags in slow or smoothed data.

### 2.4 Broader and accessible

- **Pearl & Mackenzie (2018), *The book of why*.** A non-technical tour of the causal ladder.
- **Schölkopf et al. (2021), "Toward causal representation learning."** Why machine learning models need causal structure to generalize under shift. Causal mechanisms are independent of each other and change only a few at a time, so they transfer to new settings where correlations do not.

### 2.5 Practitioner reading

- **⁺Dalio (2021), *Principles for dealing with the changing world order*.** Long cycles of debt, internal order, and external order behind the rise and fall of nations and reserve currencies. A portfolio manager recommended it as a macro foundation that applies to company analysis too. *In the model:* macro regimes enter as rival schemas (§5.5).

### 2.6 Suggested order

1. Rohrer (2018)
2. *The book of why*
3. Sloman & Lagnado (2005)
4. Griffiths & Tenenbaum (2005)
5. Shmueli (2010) and Yarkoni & Westfall (2017)
6. Pearl (1995)

Then, for this model's design:

1. White & Lu (2010) and Stock & Watson (2018): when time-series dependence is causal.
2. Lucas (1976): policy questions.
3. Kemp et al. (2010) and Fisher (1987): kinds.
4. Singaravadivelan & Langley (2026): composition.

---

# Part II. The model and the literature it borrows from

## 3. The model in brief

### 3.1 What it represents

The model's vocabulary follows the project's naming guide.

| Term | Meaning |
|---|---|
| Entity | An actor or node: a firm, an agency, a market, or an idea. |
| Subentity | An attribute of an entity, such as a revenue line or a policy rate. Each has a prior and a posterior distribution. |
| Interaction | A directed, labeled edge between subentities. It carries a belief that it exists, an effect size, a lag kernel (delay, lag, and duration), a causal-significance weight over time, a confidence, and its supporting evidence. |
| Graph update event | A set of operations on the graph (add an entity, add an interaction, change a value, and so on), translated from news or data. |
| Superentity | A recurring subgraph, or schema, in the spirit of Trellis chunks. Superentities nest. |
| Hypothesis | A claim that an interaction is present or absent, or that an entity will make a given decision. Each has a probability and an informational value. The value decays over time and is rescored as updates arrive. Together the hypotheses form the hypothesis frontier. |
| Working memory | The current graph and its daily state: each subentity's deviation from normal, in standard deviations. |
| Long-term memory | What the model has generalized, distilled daily. It holds object generalizations, interaction generalizations, entity memories (one per entity, including a record of its decisions), the correlation frontier, and prior states (episodes and explanations). |
| Thesis | A hypothetical graph update event, posed as a what-if question. |

### 3.2 Learning

Learning keeps the state current, one event at a time, and every event's learning is staged before anything is written.

1. **Predict the day.** Carry recent deviations through the interactions along their lag kernels, so that subentities nobody observes still move.
2. **Read the event.**
   - A language model translates text into operations.
   - Each fuzzy end is refined from a generalization to an entity to a concrete subentity.
3. **Learn working memory, on a staged copy.** Parse, classify, recall, and prefill: sort what is new into the concept trees, inherit priors, and retrieve analogs. Simulate the event's ripple, order by order. Fold: for each observed subentity, update its level and the effects of its incoming interactions by Kalman filtering.
4. **Learn long-term memory, on the same copy.** Update the kinds, the entity memories, the correlation frontier, and superentity support. Promotions, admissions, and dissolutions become proposals of their own.
5. **Review.** A person checks everything the copy would commit, including the second- and third-order ripple, keeps what makes sense, and only that is committed.

### 3.3 Inference

Inference runs once for each thesis. It reads the state without changing it, apart from the track records that outcomes return.

1. **Parse and recall** the thesis.
2. **Isolate** the networks (superentity instances) it touches.
3. **Isolated prediction:** simulate each network alone along its lag kernels.
4. **Distributed prediction:** couple the networks across the interactions between them.
5. **Unify** rival scenarios, weighted by their track records.
6. **Read out and explain.** Report densities and tail quantiles for subentities, entities, sectors, and superentities, with the paths and news that shaped them.
7. **Decide and evaluate.** Record decisions against the point-in-time version of the model, and score outcomes as they arrive.

How it works draws both, stage by stage.

### 3.4 Commitments

Four commitments shape the choices reviewed below.

- Borrow published methods, and state each edit.
- Represent every object in one standardized format, with a Cobweb tree for each data structure and for each composition of structures.
- Let the model compute every effect and forecast. Language models only translate text.
- Keep every step inspectable through its trace.

## 4. Concepts, schemas, and memory

### 4.1 Concept formation

**Background.**
- Cobweb builds a hierarchy of probabilistic concepts incrementally (Fisher, 1987). It sorts each instance down the tree by category utility, and it predicts missing attributes from the concept where sorting stops.
- Classit extended Cobweb to continuous attributes, with an acuity parameter that floors a concept's variance (Gennari et al., 1989).
- Category utility favors the basic level of a hierarchy, the level people name first (Corter & Gluck, 1992; Rosch et al., 1976).
- Cobweb reproduces human category-learning effects (Lian et al., 2024) and learns incrementally with little catastrophic forgetting (Barari et al., 2024, 2026). It also supports hierarchical retrieval over embeddings (Gupta et al., 2025).

**In the model.** An instance is built mostly from structured data the model already holds:
- a profile (kind, sector, and region);
- factor exposures (Ross, 1976; Stock & Watson, 2002);
- responses to standard shocks (Jordà, 2005; Sims, 1980);
- graph connections (Grover & Leskovec, 2016);
- co-holdings, where such data exist (Gabaix et al., 2025);
- text only where the input is text (Reimers & Gurevych, 2019).

Grouping objects by how they respond, and not only by how they look, follows the causal-model theory of categorization (Rehder, 2003). The vectors go into Cobweb without whitening. Each tree sets its own acuity cutoff instead.

### 4.2 Kinds and composition

**Composition.** LABYRINTH classifies the parts of a structured object first, and then describes the whole by the concepts its parts fell into (Thompson & Langley, 1991). TRESTLE adds partial matching to align roles and relations (MacLellan et al., 2016). Trellis gives one account of concepts and chunks (Singaravadivelan & Langley, 2026). The model borrows this design loosely. Each data structure has its own tree:
- subentities;
- entities;
- interactions;
- events;
- schemas;
- episodes.

A composite refers to its parts by their concepts, so no long part vector dominates a composite.

**Kinds.** Cobweb's prediction of missing attributes is what gives each entity its default subentities. An entity sorted under Airline is predicted to have:
- a jet fuel cost;
- passenger traffic;
- a market share.

These link to oil and to confidence as other airlines' do. This is the computational counterpart of three findings:
- Causal schemata, categories whose members share mechanisms (Kemp et al., 2010).
- Categories carry causal relations among their features, not just the features (Rehder, 2003).
- Generic priors carry over from the kind to the case (Lu et al., 2008).

### 4.3 Schemas, analogs, and explaining away

- **Schemas.** People induce a schema by comparing cases (Gick & Holyoak, 1983). In the model, recurring configurations of entities and interactions become superentity patterns. A pattern is admitted after review, scored by connectedness (Diebold & Yılmaz, 2014), and nested inside larger ones.
- **Analogs.** Analogy maps relational structure, not surface features (Gentner, 1983), and retrieval runs as a fast filter followed by structural alignment (Forbus et al., 1995). In the model, episodes are retrieved from their tree and aligned in the same two stages. Historical crises supply the analogs (Reinhart & Rogoff, 2009).
- **Explaining away.** Dayan and Kakade (2001) give a Kalman-filter account of explaining away: evidence for one cause lowers belief in a rival cause. In the model, a move that an entity's kind already predicts is explained by that kind, so it is not counted as evidence for a new schema.

### 4.4 Hypotheses and the value of information

The hypothesis frontier keeps structure separate from strength (Griffiths & Tenenbaum, 2005). An interaction hypothesis asks whether an interaction is present or absent, whatever its size.

An entity-decision hypothesis asks whether an actor will make a given decision. Its probability comes from the actor's entity memory, which keeps a record of decisions by context: for example, how often a central bank raised, cut, or held when inflation was above normal. This is an empirical reaction function, the nonparametric cousin of a Taylor (1993) rule.

Each hypothesis has an informational value made of two factors. The first is how far the forecasts being watched would move if the hypothesis held, in standard deviations. The second is the model's uncertainty, 4p(1 − p). Like the expected information gain of a yes-no question (Nelson, 2005), this value peaks at p = 0.5. Choosing what to watch is the observational counterpart of choosing interventions to learn structure (Steyvers et al., 2003). The value decays with a half-life and is rescored as updates arrive.

### 4.5 Memory

Working memory and long-term memory, with a daily distillation from one to the other, follow complementary learning systems theory (McClelland et al., 1995). On this account, specific episodes are stored fast, and structured knowledge is consolidated slowly and in an interleaved way, which avoids catastrophic interference.

Each entity has its own long-term memory, its entity memory. The other long-term stores are shared across entities:
- object generalizations;
- interaction generalizations;
- the correlation frontier;
- prior states.

### 4.6 People in the loop

Interactive machine learning puts a person inside the learning loop, and its central finding is that the interaction must be designed around what people can judge well, not only around what the learner needs (Amershi et al., 2014). Active learning asks which labels are worth a person's time (Settles, 2012); the hypothesis frontier's value of information plays that role for what to watch (Section 4.4).

In the model, the person does not label raw examples. They judge consequences: the items an event would add or retire, the value it moves, and the ripple that move sets off through the graph, order by order. Reviewing the staged result rather than the event follows the same principle. A person reads "Brent jumps 20%" correctly at once, but whether that should lower one airline's share price by half a standard deviation three interactions later is a claim about the model, and it is the claim that gets committed. Each decision, each deselected item, and each note is kept in the log, so the review is also a record of expert judgments.

The reviewer also states how far to trust what they approve, for the whole article or for one change. Updating on evidence one is not sure of is Jeffrey conditioning (Jeffrey, 1965), and Pearl (1988) treats it as virtual evidence that scales a likelihood. In the model a confidence c shrinks a new interaction's existence prior toward ignorance, inflates an observation's noise by 1/√c, and makes a reported move happen with probability c, so its expected size is c times the move. The value is stored with what it wrote, and at 100% nothing changes.

## 5. Dynamics, identification, and forecasting

### 5.1 Belief state and nowcasting

State-space models treat the quantities of interest as latent states, which are predicted forward and then corrected by each observation's prediction error (Durbin & Koopman, 2012). Nowcasting applies them to the real-time flow of data releases (Bańbura et al., 2013; Giannone et al., 2008). It attributes each forecast revision to the news in each release (Bańbura & Modugno, 2014).

In the model, each subentity's deviation from normal is a latent state. Each day predicts through the interactions and then corrects by prediction error. One edit to the borrowed method: every event is attributed, not only data releases. That attribution is what a brief's "news that shaped it" reports.

### 5.2 Effects, lags, and shrinkage

The model borrows four tools for effects that unfold over time:
- distributed lags (Almon, 1965);
- vector autoregressions and their impulse responses (Sims, 1980);
- local projections (Jordà, 2005);
- shrinkage priors that make many-variable systems estimable (Bańbura et al., 2010; Litterman, 1986).

In the model, each interaction has three parts:
- an effect, in standard deviations of the target per standard deviation of the source;
- a belief that the interaction exists;
- a lag kernel.

A new interaction starts from the prior of the interaction generalization it was sorted under and learns by filtering. One edit to the borrowed method: a Bayesian VAR shrinks every coefficient toward one generic prior, while here each interaction shrinks toward the prior of its own kind. The graph also grows one reviewed interaction at a time. A large VAR would be re-estimated whole.

### 5.3 Identification: when are these effects causal?

Here Part I meets macroeconomics. Effects estimated from observational time series are causal only under identifying assumptions. Two classic critiques frame the problem:
- Sims (1980) called the restrictions in large structural models "incredible."
- Lucas (1976) showed that estimated relations shift when policy rules change.

The modern answer is to find variation known to be exogenous:
- narrative shocks (Romer & Romer, 2004);
- high-frequency surprises in futures prices around announcements (Känzig, 2021; Kuttner, 2001);
- external instruments for dynamic causal effects (Stock & Watson, 2018).

Ramey (2016) surveys this work, and Kilian and Lütkepohl (2017) cover structural VARs.

In the model, three features play this role.

1. **Events are read as surprises** relative to the model's expectation. This is the logic of high-frequency identification, and the logic practitioners call pricing in: good news moves a price only if it beats what the market already expected, whisper numbers included.
2. **A reported change is not an unexplained move.** A change reported in the news enters as an observation of its subentity's new level. It is not counted as an unexplained move, so it cannot seed a new candidate interaction: the report is taken as the move's cause.
3. **Every interaction acts with a delay of at least one day.** The model identifies effects by temporal precedence, and it does not represent same-day feedback.

These are assumptions, not tests. Section 8 states them.

### 5.4 Discovering interactions: the correlation frontier

Granger (1969) causality tests whether one series' past improves forecasts of another. PCMCI extends conditional-independence testing to large, autocorrelated time series while controlling false positives (Runge et al., 2019). Billio et al. (2012) built networks of Granger causality among financial institutions, and found that those networks grew denser around periods of financial crisis. Smith et al. (2011) show the limits of reading direction from lags.

The correlation frontier works in five steps.

1. **Find unexplained moves:** the filter's prediction errors after the known drivers.
2. **Pair them with earlier moves** elsewhere, over a grid of lags.
3. **Skip pairs already connected** by an interaction.
4. **Re-check candidates at spaced intervals.**
5. **Promote an interaction only on review.** If a reviewer rejects a pair, the pair is blocked for a cooling-off period.

Conditioning on the known drivers removes confounding by causes the model already represents. It cannot remove hidden ones (Reichenbach, 1956; White & Lu, 2010), which is why promotion needs review. Like the people in Bramley et al. (2017), the model revises one working graph, a piece at a time.

### 5.4a Fuzzy ends: hedge, then resolve

A vague mention ("a US carrier", "airlines' jet fuel costs") poses a data-association problem: which known entity produced the report. Multiple-hypothesis tracking keeps every association alive and defers the choice until later scans settle it (Reid, 1979); probabilistic data association weights each candidate by its posterior instead of picking one (Bar-Shalom et al., 2009). Committing once the accumulated evidence crosses a bound is a sequential test (Wald, 1945), and a share kept for "one not seen yet" is the open-world mass of a Dirichlet process (Ferguson, 1973).

The model follows the correlation frontier's pathway with that math.

1. **Bind only a named mention.** Otherwise the end becomes a hedge: a Dirichlet posterior over the candidates the taxonomy allows, plus an open share.
2. **Hedge the forecast too.** Each candidate value gets a soft interaction whose existence is its probability, so ripples split across candidates.
3. **Weigh later evidence.** An article that names a candidate, or a candidate that moves the way the interaction predicts, adds weight, times the reviewer's confidence. This runs inside the event's staged learning, so the reviewer sees the odds change.
4. **Resolve only on review.** Once one candidate passes the bound with enough checks, a resolution keeps it and retires its rivals. A rejection sends half its weight back to the open share.

### 5.5 Networks, regimes, and forecasts

The forecasting stage draws on five literatures:
- the propagation of idiosyncratic shocks through networks (Acemoglu et al., 2012);
- regime-switching models (Hamilton, 1989);
- forecast combination (Bates & Granger, 1969), extended to weights that change over time (Raftery et al., 2010);
- fan charts (Britton et al., 1998);
- growth-at-risk, which reads tail quantiles from conditional densities (Adrian et al., 2019).

In the model, a thesis is answered in four steps:
1. Isolate the networks it touches.
2. Simulate each network alone.
3. Couple the networks across the interactions between them.
4. Unify rival scenarios by their track records.

Rival schemas play the role of regimes. The model reports densities and tail quantiles at every granularity: a subentity, an entity, a sector, or a superentity.

**Forecasts are paired simulations.** Each thesis is simulated twice on the same random draws (common random numbers), once with its operations and once without. The forecast is the difference between the two runs. A "Why" explanation re-runs the pair with one interaction removed and reports how much the forecast changes. This is counterfactual simulation in the sense of Gerstenberg et al. (2021). It is also the simulated analogue of the structural decompositions of Kilian and Lütkepohl (2017).

**Transmission across orders.** In production networks, idiosyncratic shocks travel past direct partners. A supplier's disruption hurts its customers' customers, and more so when the inputs are hard to replace (Barrot & Sauvagnat, 2016). After the 2011 Great East Japan Earthquake, the disruption propagated upstream and downstream to firms several links away (Carvalho et al., 2021). The model makes these orders explicit. For every value a thesis reaches, it reports:
- its order: the fewest interactions between the shock and the value, so first-order effects are direct and second- and third-order effects pass through one or two values in between;
- the most significant path of that length: its transmission path;
- when the effect arrives (the sum of the path's delays) and when it peaks.

For example, a shortage of Japanese build-up film reaches substrate output at first hand, TSMC's advanced packaging at second hand, and NVIDIA's data-center revenue at third hand.

**A context layer.** A forecast also accounts for every name a portfolio tracks. A context network carries the most significant shortest paths from the shock to every target and every watched name, so a faint path is still simulated. Each name is then reported as moving, moving slightly, reachable but negligible, or with no path in the graph at all. No tracked name is silently left out.

**Economic constraints.** A physical simulator obeys laws; an economic one obeys constraints that are tendencies, not laws. Buyers keep a second source, so one supplier's share rarely passes a cap, and a yield cannot pass 100%. In the model, a constrained value bends smoothly toward its bound instead of crossing it, and the forecast reports how often the bound binds.

### 5.6 Evaluation

Forecasts are scored after the fact:
- with the continuous ranked probability score (CRPS), a proper scoring rule (Gneiting & Raftery, 2007);
- with probability integral transform (PIT) checks of calibration (Diebold et al., 1998).

The scores set each schema's track record, which sets its weight in the next forecast. This is out-of-sample testing in the sense Yarkoni and Westfall (2017) recommend. Forecast failure after breaks (Clements & Hendry, 1998) is the reason the model keeps rival schemas and lets old evidence decay.

## 6. Text and language models

Two lines of work cover the role of text:

- **Text as data.** Text is now a standard economic input (Gentzkow et al., 2019). In the model, news is an input, and sentence encoders embed it where the input is text (Reimers & Gurevych, 2019).
- **Language models and causality.** Large language models do well on many causal benchmarks but fail in unpredictable ways (Kıcıman et al., 2023). They may repeat causal facts seen in training without reasoning causally, as "causal parrots" (Zečević et al., 2023).

The model limits language models accordingly:

- A language model only translates text into operations, constrained to the operation grammar and conditioned on retrieved, reviewed examples.
- It never supplies an effect size or a forecast.
- Anything it translates waits for review.
- Interactions come from data and review, because plausible text is not evidence.

---

# Part III. Synthesis

## 7. Where the model sits on the ladder

The model answers questions at all three levels, and each answer rests on different assumptions. Two kinds of thesis map onto the two kinds of intervention.

- **A changed value is a soft intervention.** For example, T-01 asks what happens if oil prices double. The thesis adds a step to oil's level, and oil's own causes still act on it.
- **A held decision is a hard intervention.** For example, a decision hypothesis posed as a thesis asks what happens if the Fed holds its rate. The decision subentity is held at the set value for the window, and its incoming interactions are ignored. This is Pearl's do-operator, and it is the "undoing" that people apply to interventions (Sloman & Lagnado, 2005).

Paired draws matter for the third level. A counterfactual needs the noise that produced the outcome; Pearl (2009) calls the step of recovering it abduction. In a simulated world the noise is known, so abduction comes for free. Each pair of runs is therefore a unit-level contrast within the model's own simulated world.

| Part of the model | Level | What licenses it | What can break it | Literature |
|---|---|---|---|---|
| Daily state (predict and fold) | Association: forecasts what will be observed | Stable effects and correct lag kernels | Breaks and regime shifts | Durbin & Koopman (2012); Clements & Hendry (1998) |
| Effect estimates | Observational data, used for interventional answers | The graph's interactions are the channels that matter; causes precede effects; reported changes are exogenous | Hidden common drivers; same-day feedback; blurred timing | Granger (1969); White & Lu (2010); Stock & Watson (2018) |
| Correlation frontier | From association to candidate structure | Conditioning on known drivers; spaced re-checks; review | Hidden common causes; selection in the news stream | Reichenbach (1956); Runge et al. (2019); Elwert & Winship (2014) |
| Kinds and default interactions | Prior structure | Members of a kind share mechanisms | Firms that differ from their kind | Kemp et al. (2010); Rehder (2003); Lu et al. (2008) |
| Thesis: changed value | Intervention (soft) | Other mechanisms stay put (modularity) | Mechanisms that change with the shock | Eberhardt & Scheines (2007); Lucas (1976) |
| Thesis: held decision | Intervention (hard) | Graph surgery for the window | Expectations that change with the policy rule | Pearl (1995); Sloman & Lagnado (2005); Lucas (1976) |
| Transmission map | Intervention, read path by path | The simulated effect, attributed to the most significant shortest path | A path can carry less than a longer one; orders count interactions, not importance | Barrot & Sauvagnat (2016); Carvalho et al. (2021) |
| "Why" explanations | Counterfactual, within the model's simulated worlds | Paired draws: the same noise with and without an interaction | Valid only as far as the model is right | Gerstenberg et al. (2021); Kilian & Lütkepohl (2017) |
| Hypothesis frontier | Structure versus strength; what to watch | A separate belief that each interaction exists; sensitivity times uncertainty | Sensitivity computed on a model that may be wrong | Griffiths & Tenenbaum (2005); Nelson (2005) |
| Evaluation | Prediction | Proper scores, out of sample | Scores test forecasts, not causal claims | Gneiting & Raftery (2007); Yarkoni & Westfall (2017) |

## 8. Assumptions, stated openly

Following Grosz et al. (2020) and Rohrer (2018), these are the causal assumptions the model's answers rest on.

1. **Sufficiency, up to review.** The interactions in the graph, including each kind's defaults, are the channels that matter. Hidden common drivers are what the correlation frontier and review exist to catch. Until one is caught, the estimated effects can absorb it.
2. **Temporal precedence.** Every interaction acts with a delay of at least one day, and same-day feedback is not represented.
3. **Reported changes are causes.** A change reported in the news is taken as the cause of its subentity's move. It is not treated as an outcome for the graph to explain.
4. **Modularity.** Intervening on one subentity leaves the other interactions' mechanisms unchanged. Policy theses therefore inherit the Lucas critique, and the briefs say so.
5. **Linearity in deviations.** Effects are linear in standardized deviations, with optional moderators that scale them.
6. **Exchangeability within kinds.** Members of a kind start from shared priors for their subentities and interactions, until their own data say otherwise.
7. **Soft economic constraints.** Where a value has a bound (a share cap, a 100% yield), the bound bends simulated paths but is not a law; how hard it bends is a modeling choice.
8. **Faithful translation.** A reviewed translation says what its source said.

## 9. Open problems

1. **Hidden common drivers.** The frontier conditions on known drivers only. Two remedies are candidates:
   - invariance across regimes as a test (Peters et al., 2016);
   - external instruments and high-frequency surprises for key interactions (Känzig, 2021; Stock & Watson, 2018).
2. **Timing.** Daily, weekly, and monthly series with release lags blur the order of moves, and reading direction from lags is fragile when timing is blurred (Smith et al., 2011). Nowcasting models handle release calendars as a "ragged edge" (Bańbura et al., 2013; Giannone et al., 2008), and the frontier could use those calendars too.
3. **Selection in the news stream.** Stories are written because something moved, so the news is a sample selected on outcomes. Any analysis that conditions on what was reported risks collider bias (Elwert & Winship, 2014).
4. **Policy questions.** A held decision assumes that other actors' mechanisms do not change with it. Rival schemas could carry mechanisms that depend on the regime, as regime-switching models do (Hamilton, 1989).
5. **Counterfactuals about realized history.** A question such as "Would CPI have risen without the oil supply cut?" needs the realized shocks, and a state-space smoother can estimate them (Durbin & Koopman, 2012). Today's explanations are counterfactuals about the model's own simulated futures.
6. **Testing causal claims, not just forecasts.** Proper scores test predictions. Policy surprises and announcements, such as export controls, act like natural experiments, and they are the natural tests of the model's interventional answers. Since the model cannot intervene on markets, these events are also its best source of the interventional evidence that speeds human structure learning (Steyvers et al., 2003).

---

## References

*A note on the references.* Every reference was checked on 6 October 2026 against Crossref, publisher, arXiv, NBER, or proceedings records. Corrections to the original reading list: Hume's *Enquiry* first appeared in 1748 under the title *Philosophical Essays Concerning Human Understanding*, and is cited here from Millican's edition; Spirtes, Glymour and Scheines (2000) is the second edition (the first appeared in 1993), and its publisher's record dates the release to January 2001; Pearl (2009) is the second edition of *Causality* (the first appeared in 2000). All other years and titles matched, and full titles are given above. † Page numbers confirmed only on the lab's publication list.

Acemoglu, D., Carvalho, V. M., Ozdaglar, A., & Tahbaz-Salehi, A. (2012). The network origins of aggregate fluctuations. *Econometrica, 80*(5), 1977–2016. https://doi.org/10.3982/ECTA9623

Adrian, T., Boyarchenko, N., & Giannone, D. (2019). Vulnerable growth. *American Economic Review, 109*(4), 1263–1289. https://doi.org/10.1257/aer.20161923

Almon, S. (1965). The distributed lag between capital appropriations and expenditures. *Econometrica, 33*(1), 178–196. https://doi.org/10.2307/1911894

Amershi, S., Cakmak, M., Knox, W. B., & Kulesza, T. (2014). Power to the people: The role of humans in interactive machine learning. *AI Magazine, 35*(4), 105–120. https://doi.org/10.1609/aimag.v35i4.2513

Bańbura, M., & Modugno, M. (2014). Maximum likelihood estimation of factor models on datasets with arbitrary pattern of missing data. *Journal of Applied Econometrics, 29*(1), 133–160. https://doi.org/10.1002/jae.2306

Bańbura, M., Giannone, D., & Reichlin, L. (2010). Large Bayesian vector auto regressions. *Journal of Applied Econometrics, 25*(1), 71–92. https://doi.org/10.1002/jae.1137

Bańbura, M., Giannone, D., Modugno, M., & Reichlin, L. (2013). Now-casting and the real-time data flow. In G. Elliott & A. Timmermann (Eds.), *Handbook of economic forecasting* (Vol. 2A, pp. 195–237). Elsevier. https://doi.org/10.1016/B978-0-444-53683-9.00004-9

Barari, N., Lian, X., & MacLellan, C. J. (2024). *Incremental concept formation over visual images without catastrophic forgetting*. arXiv:2402.16933.

Barari, N., Lian, X., & MacLellan, C. J. (2026). Robust incremental learning of visual concepts without catastrophic forgetting. *Cognitive Systems Research, 96*, 101447. https://doi.org/10.1016/j.cogsys.2026.101447

Bareinboim, E., Correa, J. D., Ibeling, D., & Icard, T. (2022). On Pearl's hierarchy and the foundations of causal inference. In H. Geffner, R. Dechter, & J. Y. Halpern (Eds.), *Probabilistic and causal inference: The works of Judea Pearl* (pp. 507–556). Association for Computing Machinery. https://doi.org/10.1145/3501714.3501743

Barrot, J.-N., & Sauvagnat, J. (2016). Input specificity and the propagation of idiosyncratic shocks in production networks. *The Quarterly Journal of Economics, 131*(3), 1543–1592. https://doi.org/10.1093/qje/qjw018

Bar-Shalom, Y., Daum, F., & Huang, J. (2009). The probabilistic data association filter. *IEEE Control Systems Magazine, 29*(6), 82–100. https://doi.org/10.1109/MCS.2009.934469

Bates, J. M., & Granger, C. W. J. (1969). The combination of forecasts. *Operational Research Quarterly, 20*(4), 451–468. https://doi.org/10.1057/jors.1969.103

Billio, M., Getmansky, M., Lo, A. W., & Pelizzon, L. (2012). Econometric measures of connectedness and systemic risk in the finance and insurance sectors. *Journal of Financial Economics, 104*(3), 535–559. https://doi.org/10.1016/j.jfineco.2011.12.010

Bramley, N. R., Dayan, P., Griffiths, T. L., & Lagnado, D. A. (2017). Formalizing Neurath's ship: Approximate algorithms for online causal learning. *Psychological Review, 124*(3), 301–338. https://doi.org/10.1037/rev0000061

Breiman, L. (2001). Statistical modeling: The two cultures. *Statistical Science, 16*(3), 199–231. https://doi.org/10.1214/ss/1009213726

Britton, E., Fisher, P., & Whitley, J. (1998). The Inflation Report projections: Understanding the fan chart. *Bank of England Quarterly Bulletin, 38*(1), 30–37. https://www.bankofengland.co.uk/quarterly-bulletin/1998/q1/the-inflation-report-projections-understanding-the-fan-chart

Carvalho, V. M., Nirei, M., Saito, Y. U., & Tahbaz-Salehi, A. (2021). Supply chain disruptions: Evidence from the Great East Japan Earthquake. *The Quarterly Journal of Economics, 136*(2), 1255–1321. https://doi.org/10.1093/qje/qjaa044

Cheng, P. W. (1997). From covariation to causation: A causal power theory. *Psychological Review, 104*(2), 367–405. https://doi.org/10.1037/0033-295X.104.2.367

Clements, M. P., & Hendry, D. F. (1998). *Forecasting economic time series*. Cambridge University Press. https://doi.org/10.1017/CBO9780511599286

Corter, J. E., & Gluck, M. A. (1992). Explaining basic categories: Feature predictability and information. *Psychological Bulletin, 111*(2), 291–303. https://doi.org/10.1037/0033-2909.111.2.291

Dalio, R. (2021). *Principles for dealing with the changing world order: Why nations succeed and fail*. Avid Reader Press.

Dayan, P., & Kakade, S. (2001). Explaining away in weight space. In T. K. Leen, T. G. Dietterich, & V. Tresp (Eds.), *Advances in Neural Information Processing Systems 13* (pp. 451–457). MIT Press.

Diebold, F. X., & Yılmaz, K. (2014). On the network topology of variance decompositions: Measuring the connectedness of financial firms. *Journal of Econometrics, 182*(1), 119–134. https://doi.org/10.1016/j.jeconom.2014.04.012

Diebold, F. X., Gunther, T. A., & Tay, A. S. (1998). Evaluating density forecasts with applications to financial risk management. *International Economic Review, 39*(4), 863–883. https://doi.org/10.2307/2527342

Durbin, J., & Koopman, S. J. (2012). *Time series analysis by state space methods* (2nd ed.). Oxford University Press. https://doi.org/10.1093/acprof:oso/9780199641178.001.0001

Eberhardt, F., & Scheines, R. (2007). Interventions and causal inference. *Philosophy of Science, 74*(5), 981–995. https://doi.org/10.1086/525638

Elwert, F., & Winship, C. (2014). Endogenous selection bias: The problem of conditioning on a collider variable. *Annual Review of Sociology, 40*, 31–53. https://doi.org/10.1146/annurev-soc-071913-043455

Ferguson, T. S. (1973). A Bayesian analysis of some nonparametric problems. *The Annals of Statistics, 1*(2), 209–230. https://doi.org/10.1214/aos/1176342360

Fisher, D. H. (1987). Knowledge acquisition via incremental conceptual clustering. *Machine Learning, 2*(2), 139–172. https://doi.org/10.1007/BF00114265

Forbus, K. D., Gentner, D., & Law, K. (1995). MAC/FAC: A model of similarity-based retrieval. *Cognitive Science, 19*(2), 141–205. https://doi.org/10.1207/s15516709cog1902_1

Gabaix, X., Koijen, R. S. J., Richmond, R. J., & Yogo, M. (2025). *Asset embeddings* (NBER Working Paper No. 33651). National Bureau of Economic Research. https://doi.org/10.3386/w33651

Gennari, J. H., Langley, P., & Fisher, D. (1989). Models of incremental concept formation. *Artificial Intelligence, 40*(1–3), 11–61. https://doi.org/10.1016/0004-3702(89)90046-5

Gentner, D. (1983). Structure-mapping: A theoretical framework for analogy. *Cognitive Science, 7*(2), 155–170. https://doi.org/10.1207/s15516709cog0702_3

Gentzkow, M., Kelly, B., & Taddy, M. (2019). Text as data. *Journal of Economic Literature, 57*(3), 535–574. https://doi.org/10.1257/jel.20181020

Gerstenberg, T., Goodman, N. D., Lagnado, D. A., & Tenenbaum, J. B. (2021). A counterfactual simulation model of causal judgments for physical events. *Psychological Review, 128*(5), 936–975. https://doi.org/10.1037/rev0000281

Giannone, D., Reichlin, L., & Small, D. (2008). Nowcasting: The real-time informational content of macroeconomic data. *Journal of Monetary Economics, 55*(4), 665–676. https://doi.org/10.1016/j.jmoneco.2008.05.010

Gick, M. L., & Holyoak, K. J. (1983). Schema induction and analogical transfer. *Cognitive Psychology, 15*(1), 1–38. https://doi.org/10.1016/0010-0285(83)90002-6

Gneiting, T., & Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. *Journal of the American Statistical Association, 102*(477), 359–378. https://doi.org/10.1198/016214506000001437

Gopnik, A., Glymour, C., Sobel, D. M., Schulz, L. E., Kushnir, T., & Danks, D. (2004). A theory of causal learning in children: Causal maps and Bayes nets. *Psychological Review, 111*(1), 3–32. https://doi.org/10.1037/0033-295X.111.1.3

Granger, C. W. J. (1969). Investigating causal relations by econometric models and cross-spectral methods. *Econometrica, 37*(3), 424–438. https://doi.org/10.2307/1912791

Griffiths, T. L., & Tenenbaum, J. B. (2005). Structure and strength in causal induction. *Cognitive Psychology, 51*(4), 334–384. https://doi.org/10.1016/j.cogpsych.2005.05.004

Grosz, M. P., Rohrer, J. M., & Thoemmes, F. (2020). The taboo against explicit causal inference in nonexperimental psychology. *Perspectives on Psychological Science, 15*(5), 1243–1255. https://doi.org/10.1177/1745691620921521

Grover, A., & Leskovec, J. (2016). node2vec: Scalable feature learning for networks. In *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining* (pp. 855–864). Association for Computing Machinery. https://doi.org/10.1145/2939672.2939754

Gupta, A., Singaravadivelan, K., & Wang, Z. (2025). Hierarchical semantic retrieval with Cobweb. *Proceedings of the Twelfth Annual Conference on Advances in Cognitive Systems*. arXiv:2510.02539.

Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. *Econometrica, 57*(2), 357–384. https://doi.org/10.2307/1912559

Hernán, M. A., Hsu, J., & Healy, B. (2019). A second chance to get causal inference right: A classification of data science tasks. *CHANCE, 32*(1), 42–49. https://doi.org/10.1080/09332480.2019.1579578

Holland, P. W. (1986). Statistics and causal inference. *Journal of the American Statistical Association, 81*(396), 945–960. https://doi.org/10.1080/01621459.1986.10478354

Hume, D. (2008). *An enquiry concerning human understanding* (P. Millican, Ed.). Oxford University Press. https://doi.org/10.1093/owc/9780199549900.001.0001 (Original work published 1748)

Imbens, G. W., & Rubin, D. B. (2015). *Causal inference for statistics, social, and biomedical sciences: An introduction*. Cambridge University Press. https://doi.org/10.1017/CBO9781139025751

Jeffrey, R. C. (1965). *The logic of decision*. McGraw-Hill.

Jonas, E., & Kording, K. P. (2017). Could a neuroscientist understand a microprocessor? *PLOS Computational Biology, 13*(1), e1005268. https://doi.org/10.1371/journal.pcbi.1005268

Jordà, Ò. (2005). Estimation and inference of impulse responses by local projections. *American Economic Review, 95*(1), 161–182. https://doi.org/10.1257/0002828053828518

Kıcıman, E., Ness, R., Sharma, A., & Tan, C. (2023). *Causal reasoning and large language models: Opening a new frontier for causality*. arXiv:2305.00050.

Kemp, C., Goodman, N. D., & Tenenbaum, J. B. (2010). Learning to learn causal models. *Cognitive Science, 34*(7), 1185–1243. https://doi.org/10.1111/j.1551-6709.2010.01128.x

Kilian, L., & Lütkepohl, H. (2017). *Structural vector autoregressive analysis*. Cambridge University Press. https://doi.org/10.1017/9781108164818

Kleinberg, J., Ludwig, J., Mullainathan, S., & Obermeyer, Z. (2015). Prediction policy problems. *American Economic Review, 105*(5), 491–495. https://doi.org/10.1257/aer.p20151023

Känzig, D. R. (2021). The macroeconomic effects of oil supply news: Evidence from OPEC announcements. *American Economic Review, 111*(4), 1092–1125. https://doi.org/10.1257/aer.20190964

Körding, K. P., Beierholm, U., Ma, W. J., Quartz, S., Tenenbaum, J. B., & Shams, L. (2007). Causal inference in multisensory perception. *PLoS ONE, 2*(9), e943. https://doi.org/10.1371/journal.pone.0000943

Kuttner, K. N. (2001). Monetary policy surprises and interest rates: Evidence from the Fed funds futures market. *Journal of Monetary Economics, 47*(3), 523–544. https://doi.org/10.1016/S0304-3932(01)00055-1

Lagnado, D. A., Gerstenberg, T., & Zultan, R. (2013). Causal responsibility and counterfactuals. *Cognitive Science, 37*(6), 1036–1073. https://doi.org/10.1111/cogs.12054

Lian, X., Varma, S., & MacLellan, C. J. (2024). Cobweb: An incremental and hierarchical model of human-like category learning. *Proceedings of the 46th Annual Conference of the Cognitive Science Society* (pp. 2597–2604)†. arXiv:2403.03835.

Litterman, R. B. (1986). Forecasting with Bayesian vector autoregressions—Five years of experience. *Journal of Business & Economic Statistics, 4*(1), 25–38. https://doi.org/10.1080/07350015.1986.10509491

Lu, H., Yuille, A. L., Liljeholm, M., Cheng, P. W., & Holyoak, K. J. (2008). Bayesian generic priors for causal learning. *Psychological Review, 115*(4), 955–984. https://doi.org/10.1037/a0013256

Lucas, R. E., Jr. (1976). Econometric policy evaluation: A critique. *Carnegie-Rochester Conference Series on Public Policy, 1*, 19–46. https://doi.org/10.1016/S0167-2231(76)80003-6

MacLellan, C. J., Harpstead, E., Aleven, V., & Koedinger, K. R. (2016). TRESTLE: A model of concept formation in structured domains. *Advances in Cognitive Systems, 4*, 131–150. arXiv:2410.10588.

McClelland, J. L., McNaughton, B. L., & O'Reilly, R. C. (1995). Why there are complementary learning systems in the hippocampus and neocortex: Insights from the successes and failures of connectionist models of learning and memory. *Psychological Review, 102*(3), 419–457. https://doi.org/10.1037/0033-295X.102.3.419

Nelson, J. D. (2005). Finding useful questions: On Bayesian diagnosticity, probability, impact, and information gain. *Psychological Review, 112*(4), 979–999. https://doi.org/10.1037/0033-295X.112.4.979

Pearl, J. (1988). *Probabilistic reasoning in intelligent systems: Networks of plausible inference*. Morgan Kaufmann. https://doi.org/10.1016/C2009-0-27609-4

Pearl, J. (1995). Causal diagrams for empirical research. *Biometrika, 82*(4), 669–688. https://doi.org/10.1093/biomet/82.4.669

Pearl, J. (2009). *Causality: Models, reasoning, and inference* (2nd ed.). Cambridge University Press. https://doi.org/10.1017/CBO9780511803161

Pearl, J., & Mackenzie, D. (2018). *The book of why: The new science of cause and effect*. Basic Books.

Peters, J., Bühlmann, P., & Meinshausen, N. (2016). Causal inference by using invariant prediction: Identification and confidence intervals. *Journal of the Royal Statistical Society: Series B (Statistical Methodology), 78*(5), 947–1012. https://doi.org/10.1111/rssb.12167

Raftery, A. E., Kárný, M., & Ettler, P. (2010). Online prediction under model uncertainty via dynamic model averaging: Application to a cold rolling mill. *Technometrics, 52*(1), 52–66. https://doi.org/10.1198/TECH.2009.08104

Ramey, V. A. (2016). Macroeconomic shocks and their propagation. In J. B. Taylor & H. Uhlig (Eds.), *Handbook of macroeconomics* (Vol. 2A, pp. 71–162). Elsevier. https://doi.org/10.1016/bs.hesmac.2016.03.003

Rehder, B. (2003). A causal-model theory of conceptual representation and categorization. *Journal of Experimental Psychology: Learning, Memory, and Cognition, 29*(6), 1141–1159. https://doi.org/10.1037/0278-7393.29.6.1141

Reichenbach, H. (1956). *The direction of time*. University of California Press.

Reid, D. B. (1979). An algorithm for tracking multiple targets. *IEEE Transactions on Automatic Control, 24*(6), 843–854. https://doi.org/10.1109/TAC.1979.1102177

Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence embeddings using Siamese BERT-networks. In *Proceedings of EMNLP-IJCNLP 2019* (pp. 3982–3992). https://doi.org/10.18653/v1/D19-1410

Reinhart, C. M., & Rogoff, K. S. (2009). *This time is different: Eight centuries of financial folly*. Princeton University Press. https://doi.org/10.2307/j.ctvcm4gqx

Rohrer, J. M. (2018). Thinking clearly about correlations and causation: Graphical causal models for observational data. *Advances in Methods and Practices in Psychological Science, 1*(1), 27–42. https://doi.org/10.1177/2515245917745629

Romer, C. D., & Romer, D. H. (2004). A new measure of monetary shocks: Derivation and implications. *American Economic Review, 94*(4), 1055–1084. https://doi.org/10.1257/0002828042002651

Rosch, E., Mervis, C. B., Gray, W. D., Johnson, D. M., & Boyes-Braem, P. (1976). Basic objects in natural categories. *Cognitive Psychology, 8*(3), 382–439. https://doi.org/10.1016/0010-0285(76)90013-X

Ross, S. A. (1976). The arbitrage theory of capital asset pricing. *Journal of Economic Theory, 13*(3), 341–360. https://doi.org/10.1016/0022-0531(76)90046-6

Rottman, B. M., & Hastie, R. (2014). Reasoning about causal relationships: Inferences on causal networks. *Psychological Bulletin, 140*(1), 109–139. https://doi.org/10.1037/a0031903

Rubin, D. B. (1974). Estimating causal effects of treatments in randomized and nonrandomized studies. *Journal of Educational Psychology, 66*(5), 688–701. https://doi.org/10.1037/h0037350

Runge, J., Nowack, P., Kretschmer, M., Flaxman, S., & Sejdinovic, D. (2019). Detecting and quantifying causal associations in large nonlinear time series datasets. *Science Advances, 5*(11), eaau4996. https://doi.org/10.1126/sciadv.aau4996

Schölkopf, B., Locatello, F., Bauer, S., Ke, N. R., Kalchbrenner, N., Goyal, A., & Bengio, Y. (2021). Toward causal representation learning. *Proceedings of the IEEE, 109*(5), 612–634. https://doi.org/10.1109/JPROC.2021.3058954

Settles, B. (2012). *Active learning*. Morgan & Claypool.

Shmueli, G. (2010). To explain or to predict? *Statistical Science, 25*(3), 289–310. https://doi.org/10.1214/10-STS330

Sims, C. A. (1980). Macroeconomics and reality. *Econometrica, 48*(1), 1–48. https://doi.org/10.2307/1912017

Singaravadivelan, K., & Langley, P. (2026). *A unified account of concepts and chunks*. arXiv:2609.30414.

Sloman, S. (2005). *Causal models: How people think about the world and its alternatives*. Oxford University Press. https://doi.org/10.1093/acprof:oso/9780195183115.001.0001

Sloman, S. A., & Lagnado, D. A. (2005). Do we "do"? *Cognitive Science, 29*(1), 5–39. https://doi.org/10.1207/s15516709cog2901_2

Smith, S. M., Miller, K. L., Salimi-Khorshidi, G., Webster, M., Beckmann, C. F., Nichols, T. E., Ramsey, J. D., & Woolrich, M. W. (2011). Network modelling methods for FMRI. *NeuroImage, 54*(2), 875–891. https://doi.org/10.1016/j.neuroimage.2010.08.063

Spirtes, P., Glymour, C., & Scheines, R. (2000). *Causation, prediction, and search* (2nd ed.). MIT Press. https://doi.org/10.7551/mitpress/1754.001.0001

Steyvers, M., Tenenbaum, J. B., Wagenmakers, E.-J., & Blum, B. (2003). Inferring causal networks from observations and interventions. *Cognitive Science, 27*(3), 453–489. https://doi.org/10.1207/s15516709cog2703_6

Stock, J. H., & Watson, M. W. (2002). Macroeconomic forecasting using diffusion indexes. *Journal of Business & Economic Statistics, 20*(2), 147–162. https://doi.org/10.1198/073500102317351921

Stock, J. H., & Watson, M. W. (2018). Identification and estimation of dynamic causal effects in macroeconomics using external instruments. *The Economic Journal, 128*(610), 917–948. https://doi.org/10.1111/ecoj.12593

Taylor, J. B. (1993). Discretion versus policy rules in practice. *Carnegie-Rochester Conference Series on Public Policy, 39*, 195–214. https://doi.org/10.1016/0167-2231(93)90009-L

Thompson, K., & Langley, P. (1991). Concept formation in structured domains. In D. H. Fisher, M. J. Pazzani, & P. Langley (Eds.), *Concept formation: Knowledge and experience in unsupervised learning* (pp. 127–161). Morgan Kaufmann. https://doi.org/10.1016/B978-1-4832-0773-5.50011-0

Wald, A. (1945). Sequential tests of statistical hypotheses. *The Annals of Mathematical Statistics, 16*(2), 117–186. https://doi.org/10.1214/aoms/1177731118

Waldmann, M. R., & Hagmayer, Y. (2005). Seeing versus doing: Two modes of accessing causal knowledge. *Journal of Experimental Psychology: Learning, Memory, and Cognition, 31*(2), 216–227. https://doi.org/10.1037/0278-7393.31.2.216

Waldmann, M. R., & Holyoak, K. J. (1992). Predictive and diagnostic learning within causal models: Asymmetries in cue competition. *Journal of Experimental Psychology: General, 121*(2), 222–236. https://doi.org/10.1037/0096-3445.121.2.222

White, H., & Lu, X. (2010). Granger causality and dynamic structural systems. *Journal of Financial Econometrics, 8*(2), 193–243. https://doi.org/10.1093/jjfinec/nbq006

Yarkoni, T., & Westfall, J. (2017). Choosing prediction over explanation in psychology: Lessons from machine learning. *Perspectives on Psychological Science, 12*(6), 1100–1122. https://doi.org/10.1177/1745691617693393

Zečević, M., Willig, M., Dhami, D. S., & Kersting, K. (2023). Causal parrots: Large language models may talk causality but are not causal. *Transactions on Machine Learning Research*. arXiv:2308.13067.
