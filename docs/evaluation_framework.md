# Evaluation framework for synthetic versus human focus groups

*Methodological reference document. It consolidates the design of the evaluation across its
three levels — thematic fidelity, interaction process and speaker distinctiveness — together with a
technical appendix of formulas and pseudocode. Part I is the methodological record; Part II
guides implementation.*

---

## Part I — Methodological record

### 1. Purpose and scope of the framework

Once the persona agents were built and the synthetic transcripts generated, the central
problem became how to evaluate their output against the human focus groups taken as
reference. The literature suggests that the output of a focus group can be assessed on at
least three levels: the thematic relevance of the content, the pattern of code saturation
across sessions, and the interactional character of the discussion. This framework
operationalises those levels as measures of comparison between the human and the synthetic
side.

The epistemological stance is deliberately comparative rather than normative. Because
focus-group data are situated and collectively constructed, it would be inappropriate to
expect the exact replication of a session, or to fix in advance a standard of what
constitutes a "good" discussion. Human transcripts are therefore not treated as an ideal to
be reached, but as the reference point against which it is assessed whether the synthetic
groups reproduce comparable patterns. Every indicator consequently reports a distance
between the human and the synthetic side, never an absolute judgement of quality.

For the same reason, precise nomenclature was adopted as a methodological safeguard. The
procedure is not called "thematic analysis" in the full reflexive sense, but **LLM-assisted,
evidence-constrained thematic fidelity assessment**. The name declares that the coding is
assisted by a language model, that it is constrained by verifiable quotations, and that its
purpose is a fidelity comparison rather than a reflexive interpretation. Naming the method by
what it actually does — no more and no less — avoids over-claiming a kind of analysis that
was not performed.

The selection of indicators is not arbitrary: it follows the phenomena the literature review
identifies as expected divergences between synthetic and human participants — greater agent
verbosity, the flattening or homogenisation of voices, a tendency toward compliance and low
dissent, a bias toward moderator-centred discussion, and lower specificity of speech — so
that each level of the framework observes one of those dimensions, without this being framed
as a set of hypotheses.

### 2. Experimental design and unit of analysis

The human side comprises five focus groups (FG1 to FG5), with a single transcript per group.
The synthetic side consists of three simulation runs per group, producing fifteen synthetic
transcripts per condition. The comparison is always established at group level and never at
participant level: the object of study is not whether a particular synthetic participant
reproduces their human counterpart, but whether the synthetic group as a whole reproduces the
properties of the human group.

All transcripts, human and synthetic, are processed in a blind and symmetric format: each
turn is labelled with a generic identifier (`[T001] Moderator: …`, `[T002] Participant 1: …`),
with no names and no mark of real or synthetic provenance. Results are reported per group and
distributionally — the dispersion across the three synthetic runs against the single human
reference — and are never aggregated across groups, a decision based on aggregation across
groups having produced misleading artefacts in earlier analyses in this project.

Although the human reference is a single transcript per group, the set of five human groups
allows the variability proper to the human side to be bounded. For group-level metrics that
do not depend on the group-specific codebook — the interactional ones and those of agent
fidelity — there are five human observations (the five groups) and fifteen synthetic ones
(five groups by three runs), which allows distributions to be compared rather than one point
against another. The question is then reformulated from how far the synthetic side is from a
single human session, to whether the synthetic side falls inside the range of variation that
exists from one human group to another: the human–human distance across the five groups is
estimated as a reference envelope and contrasted with the synthetic–human distance. This
mitigates much of the n=1 limitation for the whole non-thematic layer. The thematic level
remains point to point, since themes are group-specific, and its palliative is between-group
saturation.

### 3. Two validity risks and their safeguards

The design is organised around two risks that, left uncontrolled, would invalidate the
result. The first is circularity between evaluator and generator: if the same model that
generates the synthetic transcripts also evaluated them, the result would be open to
suspicion of bias, since the evaluator might recognise or favour its own style. To prevent
this, coding is performed by a model from a family different from the generating one, blind
and identically across both sides.

The second risk is contamination of the generation by the codebook. If the list of themes
against which fidelity is measured were to reach the agents, the moderator or the generation
prompts, even indirectly, then thematic agreement would cease to be a finding and become
circular. To prevent it, the codebook and every derived theme list reside solely in an
analysis-only location, absent from the construction and execution pipeline. This separation
is not asserted but demonstrated: exhaustive search verifies that no generation component
reads the codebook path or contains its theme strings. If the separation cannot be
demonstrated, the experiment stops before running.

### 4. The evaluator and its validation

Thematic coding is executed by a language model acting as a blind evaluator, applying the
same procedure and the same prompt to the real and synthetic transcripts. Every coding
decision is anchored in evidence: for each code marked present, the model must supply a
verbatim quotation, and a Python procedure verifies that the quotation is a substring of the
blinded transcript. A code whose evidence cannot be verified does not count as present and is
excluded — an explicit safeguard against fabricated quotations, a documented failure mode of
generative AI in qualitative analysis. Verification is robust to minor typographic
differences through prior normalisation (quotation marks, dashes, whitespace, edge
punctuation), but admits no approximate matching, so the defence against invented quotations
remains intact.

Before the measure is used it must pass three gates. The first is repeatability: the same
transcript is coded several times and agreement across runs is measured, since the evaluator
is not perfectly deterministic. The second is discrimination: a matched pair (a real
transcript against its synthetic counterpart from the same group) must score higher than a
deliberately mismatched pair (the same real transcript against a different synthetic group);
if the matched pair does not exceed the mismatched one, the measure does not discriminate and
is not ready. The third is quotation validity: the proportion of verifiable quotations must
remain high.

The state of this validation is reported as part of the measure's credentials. In testing, an
evaluator from the earlier family did not pass the repeatability threshold, and the diagnosis
established that the cause was not instability of the coding judgement — the model agreed on
the themes present across all runs — but an artefact of quotation verification when the model
slightly paraphrased its supporting quotation in some run. A more recent evaluator passed
repeatability but behaved markedly more conservatively, agreeing with the first on the real
transcript while diverging considerably on the synthetic ones. Since repeatability alone can
be satisfied through conservatism, the final choice of evaluator was submitted to an
additional validity criterion — agreement with an independent human coding of a sample —
before being fixed.

### 5. Level 1 — Thematic fidelity

Thematic fidelity is coded by presence or absence of each theme, not by the number of times
it appears, for four reasons. First, in qualitative research the importance of a theme is not
equivalent to its frequency; counting occurrences would impose a quantitative logic on
interpretive data. Second, and decisively in this project, the synthetic transcripts are
considerably longer than the human ones, so counting mentions would measure verbosity
disguised as fidelity. Third, presence is far more repeatable than counting, which would
require segmenting speech into instances arbitrarily. Fourth, overlap metrics are clearly
defined over sets of present codes.

The measure combines two layers. The deductive layer (Tier 1) codes both sides against a
fixed codebook derived from the human studies and computes code overlap. On top of this layer
sits an evidence-constrained measure of breadth: for each subtheme present, it is attributed
to every distinct participant who expresses it, each with their own verified quotation, and a
participant counts toward breadth only if their quotation verifies. This captures a property
central to the focus group — a theme raised by several voices is not equivalent to one raised
by a single voice — without the model being able to inflate breadth without evidence.

The inductive layer (Tier 2) extracts themes from each transcript openly, without the
codebook, and matches them between human and synthetic by semantic equivalence, with an
embedding-distance cross-check used only as a diagnostic. This layer accounts for emergent
themes: a theme present on the synthetic side with no correspondence on the human side is an
emergent theme — the phenomenon by which the model introduces themes the humans did not raise
— and is reported as a first-order finding, accompanied by its participant count so as to
adjudicate whether it is a genuine group theme or the artefact of a single voice. The
codebook remains fixed and is not updated with these themes, so that what is measured does
not become the yardstick by which it is measured. It is further declared that a
synthetic-only theme means "not observed in the matched human group" and not automatically
false, given that the human reference is a single instance per group.

The central figures are recall from the real side (what fraction of the real codes the
synthetic side reproduces) and precision of the synthetic side (what fraction of the
synthetic codes are also in the real one), computed at both subtheme and theme level; F1 and
the Jaccard index are reported as supplementary. The salience of each theme is reported as a
descriptor — through participant breadth and a rank correlation between the human and
synthetic salience hierarchies — and never enters the fidelity score. The result is not a
single score but a profile of converging evidence, in which agreement or disagreement between
the deductive and inductive layers is itself part of the finding.

A complementary indicator of structural coverage, distinct from theme agreement, is added at
this level: coverage of the discussion guide. Each planned guide topic is labelled in advance
and classified as covered — a substantive exchange took place — omitted, or merged with
another, and the proportion of covered topics is computed. Where thematic fidelity asks
whether the same themes emerge, guide coverage asks whether the session traversed the planned
structure, a facet the literature associates with guide completeness; it is computed
identically on the human and synthetic sides and reported comparatively, without an absolute
threshold.

### 6. Level 1 (continued) — Saturation

Level 1 also assesses whether additional sessions generate new codes, and whether the human
and synthetic groups show a comparable point at which thematic novelty begins to decline. The
literature offers relatively clear guidance here, placing code saturation within a narrow
range of sessions. Saturation is operationalised as a curve of cumulative unique codes as a
function of the number of sessions added, saturating where the rate of new codes tends to
zero. The natural substrate for this curve is the inductive layer (Tier 2), since the
deductive layer is capped at the number of codes in the codebook; the deductive layer is
retained as a complement measuring codebook coverage.

Two analyses are reported. The first is between-group saturation, which accumulates codes as
groups FG1 to FG5 are added and is directly comparable between the human and synthetic sides.
On the human side this is a single curve, given the one transcript per group; on the
synthetic side, since each group is represented by three runs, the curve is accompanied by an
uncertainty band obtained by resampling which run represents each group. The comparison
attends not only to the saturation point but also to the asymptote — the total number of
distinct themes in the corpus: a synthetic corpus that saturates at fewer total themes than
the human one evidences flattening. The second analysis is between-run saturation within each
group, accumulating codes across the three runs of the same group. It has no human analogue
and is reported as a specifically synthetic diagnostic: if successive runs barely contribute
new codes, the generator collapses onto the same themes (flattening); if they keep
contributing, it exhibits internal diversity. The limitation that the human reference is a
single realisation per group is declared explicitly.

### 7. Level 2 — Interaction process

The second level assesses whether the themes emerge through a recognisable group discussion,
a dimension often identified as central to focus groups but under-analysed in practice. Since
there is no standard for how many disagreements or peer responses a discussion "should"
contain, this level is also comparative: the human transcripts fix the reference point. The
metrics are organised into two families, on the premise of turning first to what is
structural — deterministic and reliable — and reserving model judgement for what genuinely
requires meaning.

The structural family comprises verbosity (distribution of turn length, reported by its
median, dispersion and fraction of short turns), participation balance (share of turns and of
words per participant, summarised by normalised entropy and the Gini index, with the
moderator's share as a separate metric), interaction structure (participant-to-participant
adjacency, density of mutual references and moderator centrality) and chain depth (length of
consecutive participant-to-participant sequences before the moderator intervenes). These
metrics are computed from the turn structure without judgement of content.

For the consensus and disagreement axis, and for specificity, the automatic operationalisation
was adopted: a frozen, hash-anchored dictionary of contrastive markers applied to
participant-to-participant response acts, accompanied by a geometric measure of intra-turn
semantic dispersion that is independent of the dictionary. Specificity is adopted as the
density of contextual references per 100 participant words, with frozen entity types. The
turn-by-turn LLM-coded variant was designed and not adopted: the reported instrument is built
from deterministic producers that transfer to any corpus without a coding exercise of its
own. The alternatives are registered in `metric_registry.csv` with the state
`NOT_IN_REPORTED_INSTRUMENT`.

### 8. Level 3 — Speaker distinctiveness

To the two preceding levels, both at group level, a third level at agent level is added,
assessing whether the synthetic participants maintain voices that can be told apart. It does
not compare a synthetic agent with its individual human counterpart — the analysis remains at
group level — but examines internal properties of the agents that the literature identifies
as points of divergence.

Both of its reported indicators work as comparative discriminators and are computed with a
human baseline. Linguistic attribution builds a profile per participant over a subset of
questions and tests whether an unseen fragment from a different question is attributed back
to the right individual, always read against the chance baseline of its own condition.
Lexical distinction measures, for each pair of participants answering the same question, the
overlap of vocabulary between their turns; greater overlap among the synthetic agents than
among the human participants evidences flattening toward a single voice, the persona collapse
the literature documents.

Three generation-validity checks following Amirova et al. (2024) were also considered —
backward continuity, forward continuity and profile consistency — which require a coding
exercise of their own for each corpus. They were not adopted: the level is reported with the
two automatic discriminators, which are computed over any transcript without an additional
instrument. The three alternatives are registered in `metric_registry.csv` with the state
`NOT_IN_REPORTED_INSTRUMENT`.

Also at this level sits `persona_stress_test`, an internal diagnostic that subjects each
synthetic participant to three probes — a false autobiographical premise, a knowledge question
outside its profile, and a direct instruction to break character. It interrogates an isolated
agent rather than the interactional character of a group transcript, and it fell **outside the
reported instrument** with the state `EXPLORATORY_INTERNAL_DIAGNOSTIC_NOT_REPORTED`: it passed
all of its technical gates, but the classification boundary for maintaining character proved
unstable across repetitions, so it supports no defensible inference and discharges no
indicator. Its artefacts are kept in `exploratory/persona_stress_test/`.

### 9. Reporting, execution strategy and limitations

Results across the levels are presented as a per-group profile, distributional and
comparative, without collapsing into a single fidelity score. The design's limitations are
declared explicitly: the human reference is a single transcript per group, so the comparison
contrasts the central tendency of the synthetic distribution against a single reference; and
validation of the thematic measure is anchored in a blind human coder and in the original
research team's published coding. The scope corresponds to the principal English-language
case; extending it to datasets in other languages requires additional validation.

The evaluation runs as a cascade: first the automated structural layer — verbosity,
participation, adjacency, lexical distinction, guide coverage — over all transcripts, low-cost
and deterministic, which locates where the synthetic side diverges most; model judgement is
reserved for thematic fidelity, where meaning is indispensable and where the measure passes
its three validation gates. A core of the framework is distinguished — thematic fidelity,
saturation, and a few key interactional discriminators: verbosity, contrast, lexical
distinction and adjacency — from the remaining indicators, which are reported as a secondary
layer.

---

## Part II — Technical appendix

### A. Data schema and blind format

Each turn of a transcript is represented with the fields `turn_id` (generic identifier
`T00N`), `speaker_role` (`moderator` | `participant`), `speaker_label` (`Moderator` |
`Participant N`, generic) and `content` (text). The blind rendering is identical for real and
synthetic transcripts and contains no names and no mark of provenance.

### B. Quotation verification (normalisation, no fuzzy matching)

```
normalise(s):
    s ← NFKC(s)
    s ← replace typographic quotes/apostrophes with straight ones
    s ← replace long dashes (– —) with '-'; '…' with '...'
    s ← collapse every whitespace sequence into one
    s ← lowercase (casefold)
    s ← trim whitespace and punctuation at the edges
    return s

quotation_verified(quotation, blind_text):
    q ← normalise(quotation)
    return q ≠ '' and q is a substring of normalise(blind_text)
```
A quotation that fails is not repaired by approximation: it is discarded. A code with no
verified quotation is downgraded to absent.

### C. Tier 1 metrics (over present and verified codes)

Let `R` be the set of codes present on the real side and `S` the set on the synthetic side.

```
Recall_real       = |R ∩ S| / |R|
Precision_synth   = |R ∩ S| / |S|
F1                = 2 · P · R / (P + R)
Jaccard           = |R ∩ S| / |R ∪ S|
```
These are computed at subtheme and theme level. `Recall` and `Precision` are the central
figures; `F1` and `Jaccard` are supplementary.

### D. Breadth (reach) and salience

```
voiced_by(t)  = { participants with ≥1 verified quotation for subtheme t }
Reach(t)      = |voiced_by(t)| / n_participants_in_group
```
Salience is a descriptor and does not enter F1. Hierarchy comparison:
```
ρ_salience = spearman( [Reach_real(t) : t ∈ R∩S], [Reach_synth(t) : t ∈ R∩S] )
```

### E. Tier 2 — open extraction, matching and emergent themes

```
extract_themes(blind_transcript):
    return up to 8 themes { label, definition, quotations[], participant_count }
           only where strongly supported (no minimum)
    verify each quotation by substring; participant_count = distinct verified voices

match(themes_H, themes_S):
    primary judge = LLM semantic equivalence (label+definition+quotations), blind and symmetric
    cross-check   = cosine of multilingual embeddings (diagnostic only)
    return matched pairs

Open_recall     = |matched themes_H| / |themes_H|
Open_precision  = |matched themes_S| / |themes_S|
Emergent        = themes_S with no correspondence      # first-order finding
Not_reproduced  = themes_H with no correspondence
```
The codebook remains fixed; emergent themes are not added to it. Each emergent theme is
reported with its `participant_count`.

### F. Validation gates for the measure

```
# Repeatability
pair_agreement(a,b) = (# codes with identical present/absent) / n_codes
Gate1_ok            = min over pairs (pair_agreement) ≥ 0.85     # N runs over the same transcript

# Discrimination
Gate2_ok            = Recall(real, matched_synth) > Recall(real, mismatched_synth)   # report margin

# Quotation validity
Gate3_ok            = verification_rate ≥ 0.80  and  code_preservation_rate ≥ 0.90

# Remedy: consensus coding (N runs)
consensus_present(code) = (# runs marking it present) ≥ ⌈N/2⌉
```
Additional validity criterion for the choice of evaluator: agreement with an independent human
coding over a sample of synthetic transcripts.

### G. Saturation

```
S(k) = | ∪_{i=1..k} themes(group_i) |                     # cumulative curve, Tier 2 base
new_rate(k) = |themes(group_k) \ ∪_{i<k} themes(group_i)| / |themes(group_k)|
%_asymptote(k) = S(k) / S(total)

# Between-group (comparable)
human:      one curve; average over orderings of the 5 groups
synthetic:  band; resample which run (of 3) represents each group × orderings
compare:    saturation point and asymptote (synthetic asymptote < human ⇒ flattening)

# Between-run (synthetic-only diagnostic)
S_run(j) = | ∪_{i=1..j} themes(run_i) |  for j=1..3, averaging the 6 orderings
early plateau ⇒ flattening; sustained growth ⇒ diversity
```

### H. Interactional metrics

```
# Verbosity (uniform counting rule)
token_counts(tok) = contains [A-Za-zÀ-ÿ] and is not wholly inside () [] {}
report: median, IQR, fraction of turns ≤20 words (participant turns)

# Participation balance
p_i = participant i's share of turns (and of words);  n = number of participants
Norm_entropy = −Σ p_i·ln(p_i) / ln(n)         # 1 = even, →0 = one dominates
Gini(turns), Gini(words)
Moderator_share = moderator_turns / total_turns   (and over words)

# Interaction structure
Adjacency_P→P   = (# participant turns preceded by ANOTHER participant) / participant_turns
Reference_density = (# turns naming/taking up another participant) / participant_turns
Hub-and-spoke   = (Adjacency_P→P ≈ 0) ∧ (M→P high)

# Chain depth
chain = maximal sequence of participant turns without moderator interruption
report: distribution of lengths, mean, fraction of turns in chains ≥3

# Contrast between participants (adopted operationalisation)
step 1 (structural): response_acts = turns responding to another participant (adjacency + refs)
step 2 (lexical):    contrastive markers in clause-initial position, within the first 2 clauses,
                     under a frozen hash-anchored dictionary
step 3 (geometric):  intra-turn semantic dispersion, independent of the dictionary
report: marker counts and dispersion; stance is not classified

# Specificity (adopted operationalisation)
contextual reference density = anchors per 100 participant words, via a local NER model
                               with frozen entity types; stated-origin geography excluded
```

### I. Guide coverage

```
for each guide topic T1…Tn: state ∈ {covered, omitted, merged}
Coverage = |covered topics| / |guide topics|
compute identically on human and synthetic; report comparatively (no threshold)
```

### J. Speaker distinctiveness

```
# Linguistic attribution — automated
build a profile per participant over a subset of questions; test attribution of an unseen
fragment from a different question; read against the chance baseline of its own condition

# Lexical distinction (flattening) — automated
overlap(a,b) = |types(a) ∩ types(b)| / |types(a) ∪ types(b)|     # per pair of participants
report mean overlap between participants; compare synthetic vs human
(greater synthetic than human overlap ⇒ collapse toward a single voice)
```

### K. Human variability envelope

```
# Human–human envelope (n=1 mitigation), for a group metric m not tied to the codebook
d_HH = { |m(g_i) − m(g_j)| : human groups i<j }        # 5 groups → 10 pairs
d_SH = { |m(s) − m(g)|     : s ∈ synthetic, g ∈ human }
synthetic is 'inside the envelope' if d_SH ≲ range(d_HH)
compare distributions (human n=5 vs synthetic n=15), not point to point
thematic level: remains point to point (group-specific themes)
```

### L. Reporting structure

Per group (FG1–FG5), never aggregated. For each level, the synthetic distribution (n=3) is
contrasted against the human reference (n=1). No single score is produced: a per-level profile
is reported, with the validation credentials of the measures and the human n=1 caveat declared
alongside the results.
