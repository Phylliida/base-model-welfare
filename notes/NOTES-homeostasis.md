# Homeostasis in base models: research notes

Started 2026-10-13. Model: GLM-4-32B-Base-32K Q4_K_S (`~/prog/SimpleBot/models/`), the same model the J-lens was fit on.

## Goal

Model the state-to-state dynamics of a base LM and look for homeostasis-like behavior. That means variables that are held near a set point and restored after a disturbance. The set point can be fixed (like body temperature) or set by context.

## Why not the teacher-forced propagator screen (the pasted proposal)

- **No same-layer path between positions.** A push at `(s, l)` first reaches the K/V of block `l+1`. So `h_{t,l}` for `t > s` can never see it, and the same-layer lag-k propagator is identically 0. Every cross-position hop costs at least one layer, so the echo gets at most `L−l` hops.
- **No fixed points.** With tokens fixed, the model is a bounded-depth DAG, not an iterated map. What the screen really measures is transmission gain: which heads' OV circuits read `u`, and how far back they attend.
- **The random-direction null doesn't work.** Matched random directions can't null transmission gain, because that gain is exactly where `u` differs from a random direction. H1 comes out true by construction. Directions that nothing reads would look "maximally contracted".
- **Absolute values hide the sign.** `|Δh·u|` makes anti-copying (negative `u'ᵀP_k u`) look like slow contraction.
- **The real recurrence is the sampled token.** At layer l, the token is the only path from position s to s+1.

## Design principles

1. **The system is the sampled loop.** The dynamics are context → sample → longer context, and activations are just coordinates on that. Always use sampled rollouts, never greedy. Pick one sampler and keep it fixed, because a truncated sampler is a different dynamical system. Temperature 1 with no truncation is the model's own dynamics.
2. **Variance alone can't separate "held" from "never pushed".** Only kicks can. Do NOT filter on high between-prefix variance (a fixed set point is classic homeostasis). Do NOT rank by slowness (TICA): strong regulation decorrelates fast, like an OU process with large θ. Fixed versus context-set point is a descriptive axis to report afterwards, not a filter.
3. **Natural forks are the null.** Two tokens sampled from the model's own distribution are not a disturbance; the model expected both. The gap between those branches measures the model's own predictive branching. The real kicks are forced tokens graded by surprisal (p ≈ 0.3 … 1e-6), and surprisal is the dose axis in token space.
4. **Share sampler seeds.** Kicked and control branches use the same seeds, so a measured difference comes from the kick and not from sampling noise.
5. **Partial out prediction.** At every lag, measure how far apart the branches' next-token distributions are, and ask which state gaps that divergence does NOT explain. Use the J-lens to split a layer into directions the output reads now and directions it doesn't. A kick restored in the unread subspace is internal state maintained beyond what next-token prediction requires.

## Confounds to plan for from day one

- **Bayesian outvoting.** One odd token is weak evidence against 500 consistent ones, so restoration can just be stable inference. Discriminator: pure evidence accumulation predicts the kick's effect decays roughly hyperbolically, at a rate tied to prefix length. Active regulation predicts a rate that isn't. Compare short and long prefixes.
- **The simulated writer's homeostasis versus the model's own.** A perfect text model reproduces the text's memory structure, and stories keep characters consistent because authors do. A finding is the model's own only if it beats what prediction explains (principle 5), or if it concerns variables about the computation rather than the story: residual norm, confidence or entropy regulation (entropy neurons, Stolfo et al. 2024, arXiv:2406.16254), or attention-sink mass.
- **Compensation signatures** that go beyond outvoting:
  - overshoot past baseline
  - repair text that addresses the deviation
  - restoring force that doesn't weaken with evidence weight
- **Token-local features fake a perfect return.** They reset as soon as both branches emit the same next token. Measure gaps from lag 2–3 onward and look at the whole response shape:
  - gone by lag 2: token-local
  - displaced, then decaying: a candidate
  - flat: committed

## Welfare framing (2026-10-14)

Why homeostasis matters for welfare: on several accounts of valence, it tracks movement relative to a set point the system has to defend. The parent doc ("Base model experiments", Google Doc) asks "do base models push toward certain preferred states?" and "what's the difference between an attractor and a homeostasis?". A candidate vital sign has to be:

1. **Represented**: some readout decodes it (S1 does this for surprise).
2. **Defended**: pushed off, it comes back through the model's own pathways (K1/K2).
3. **Upstream of behavior**: its deviation changes what the model does, in the restoring direction.

**Attractor versus homeostasis, operationally.** Use the thermostat test from the doc: find the sensor, show it responds to the variable, and show that the correction depends on the sensor. A passive basin recovers without any sensed error signal. Test: run K1 with the candidate sensor direction erased (LEACE or partial projection, a dose ladder) against matched random erasures. If recovery slows only when the sensor is erased, that's regulation. If recovery is unchanged, the return is passive (an attractor or outvoting). Also report the doc's A/B split: pushes that depend on context versus pushes present regardless of context.

**The main null is inference, not just outvoting.** A base model is optimized to estimate, so almost any return to a set point can be belief updating about what document this is. Signatures of control rather than estimation:
- restoration faster than the kick's evidence weight justifies, compared across short and long prefixes;
- a set point that doesn't move with evidence;
- the model's own token choices steering the context back more than the text distribution predicts.

**Hedging is not a preference.** Log loss is a strictly proper scoring rule, so a calibrated predictor *must* flatten when it is unsure. That answers the "why not lower temperature and take a 1/3 chance" question from the call transcript. An internal temperature dial (S2) is therefore expected machinery, not evidence of valence by itself.

**What the data say so far.**
- The sensor exists: graded surprise coding and a slow document-level surprise variable (S1).
- The first response to a surprise is widening, not correcting: entropy goes up, so more surprising samples follow, a positive-feedback candidate (S1/S2). That is evidence-following, the opposite of self-soothing at lag 1. K1 asks what happens after that.
- Read and write directions differ: the probe direction has no causal effect (S2). That is presence without demonstrated use, the bottom rung of the represent/use ladder.

**Value lens proposal** (written 2026-10-14, https://claude.ai/artifact/DvMrx6NYbLuAgj8ZrNc6FM). The idea: price residual directions by the gradient of future log-likelihood, then test whether the model leans its token choices toward easier futures beyond calibration, comparing base against instruct. Predictive success is the currency to start; the common-currency arm comes later (the user's call).

**Elicitation Without Collapse proposal** (2026-10-14, https://claude.ai/artifact/RDmcSyg6Z9qSbd1uQwqtsF). RL on a base model's own outputs that targets the posterior p_base(x|o) instead of a reward maximum. Collapse metric: excess KL = KL(pi||base) - d(q||P_base(o)). The health battery (lean fit a/b, S1 entropy-after-surprise curve, K4 loop margin) doubles as a training diagnostic. Small model on the 3090.

**Three Rs protocol** (2026-10-14, https://claude.ai/artifact/JXHjtVgSQLW8f3kcQ2Qpmm). Rules for candidate-aversive experiments: pain vector, past-margin doses, extreme kicks, RL into loops. Use the gentlest instrument first, power analyses, humane endpoints (loop onset, entropy threshold, battery bounds), matched positive conditions, a log CSV, and pre-registered triggers that tighten the rules. Follow it for K1/K2/K4 and the value-lens and elicitation work.

**Whose Distress Is It? proposal** (2026-10-14, https://claude.ai/artifact/L6nHXMusbZQWJkgFKFt8S7). Two-way coupling between a character's depicted state and the model's own variables: minimal pairs matched on surprisal (content to own), and perturbations of the model's processing scored for depicted affect (own to content).

**Follow-ups from the doc that fit the existing tools.**
- **"Pain" vector** (the doc's "injections that universally increase loss"): run `homeo-steeropt` with the sign flipped to maximize held-out CE, then compare against the temperature and CAA vectors. Does the S1 surprise readout track the injection (dose-response, both signs)? That asks whether the model registers its own damaged prediction, separately from whether damage happens.
- **Detecting deployment perturbations** (repetition penalty producing "annoyed" stories): perturbation types with no shared textual signature (rep penalty, temperature, logit noise, quantization), on a dose ladder. Read out the document-level surprise variable and the rate of "something is wrong" content. Detection that scales with dose and transfers across types beats the pure-prior story. Detection is still not distress.
- **EOS as the only exit:** compare end-of-text mass after kicks against the natural-fork null. The baseline is document-ending statistics (bad documents end sooner in the data).
- **Effect of RL:** rerun S1/S2 on GLM-4-32B-0414 (instruct). Does post-training change the sensor, the temperature dial, or the set point?

## Experiments, in order

### S1: Does the model represent "the previous token was unlikely"? (in progress)

The surprise detector would be the *sensor* half of any feedback loop: a homeostatic loop needs to notice a deviation before it can correct one.

- **Data.** 192 temperature-1 rollouts (`data/rollouts.jsonl`, about 2k tokens each), plus forced tokens. At sampled contexts, branch the KV cache and decode one token from each log10-p bin at the same position.
- **Targets.**
  - surprisal `s_t = −ln p_{t−1}(x_t)`
  - entropy `H_{t−1}`
  - `s_t − H_{t−1}`. On-policy, this has zero mean given the prefix, so no function of `h_{t−1}` can predict it. Decoding it from `h_t` is pure surprise detection.
  - log rank
- **Probe.** Ridge regression per layer, split by document.
- **Controls.**
  - token-identity baseline: a cross-validated per-token mean target
  - within-token correlation: the same token in contexts where it was likely versus unlikely
  - within-context contrast: forced tokens at a shared prefix
- **Memory curve for surprise itself.** Decode `s_{t−k}` from `h_t` for k = 1..32. This shows how long the model "remembers being surprised", and links straight to K1.

**Results (2026-10-13; data `/mnt/models/homeo/s1`, 56k forced + 97k natural samples, 64 docs, 5 doc-grouped folds):**
- **Strongly linearly decodable.** On the forced set, R² of surprisal is 0.73 at L4, 0.86 from L16, and peaks at 0.895 at L44 (of 61). Within a context (same prefix, different tokens) r = 0.96. The raw-embedding baseline gets R² 0.34 and within-context r 0.65, so token rarity explains only part of it.
- **Calibrated over 10 orders of magnitude.** Per-bin mean predictions at L44 track the truth from about 4 nats to 27 nats; the low end is overestimated by about 1 nat. The coding is graded rather than a junk-token flag: within each single log10-p bin, the out-of-fold prediction still correlates with exact surprisal (r 0.12–0.40 in all 12 bins).
- **Natural text, same story.** R² 0.645 at L44 versus 0.02 for the embedding. Within token (same token, different contexts) r = 0.78; the embedding gets −0.20. The unexpected part `s − H_{t−1}` within token is still r = 0.47. Caveat: `H_{t−1}` itself is decodable from `h_t` (R² 0.75), so the forced within-context result is the clean evidence.
- **A surprising token makes the model uncertain.** Mean next-token entropy after the forced token rises with its surprisal: 0.6 nats for p > 0.3, 1.4 for p ~ 1e-2, 2.5 for p ~ 1e-5, and 5.6 for p < 1e-10.
- **Memory curve and a slow variable.** R² of `s_{t−k}` from `h_t` at L44 is 0.645 / 0.44 / 0.33 / 0.30 at k = 0 / 1 / 2 / 3, then flattens to a floor of about 0.22 at k = 32. The floor is the document's surprise level: the mean surprisal over the 64 tokens before t−32 is decodable from `h_t` with R² 0.715, and on its own it explains `s_{t−32}` with r² 0.25. **The model tracks a slow "how predictable is this text" variable**, which is the first concrete K1 candidate.

### S2: Surprise-level steering (the user's idea)

**Results (2026-10-13; `/mnt/models/homeo/s2`, 8 rollouts, 2024 positions, exact distributions).** Scales are fractions of the mean residual norm (L44: 354, L32: 120). Unsteered `E[−ln p]` is 0.705.

- **CAA "just saw a weird token" vector** (mean h for forced tokens with p < 1e-8, minus mean h for tokens with p > 0.1; natural norm about 0.37× the residual):
  - It is a bidirectional uncertainty dial. At L44, `E[−ln p]` is 0.575 at −0.25×, 1.12 at +0.25×, and 2.97 at +0.5×, with matched temperature T = 0.85 / 1.29 / 1.67. L32 does the same, more weakly (1.84 at +0.5×).
  - It is mostly a temperature knob, not a "pick p" selector. KL to the T-matched distribution is 20–30% of KL to p, argmax is kept as often as with a random vector of the same norm, and the non-temperature residual is about the size of the random push's at ±0.25×. The only extra is a mild excess of mid-band mass (p ∈ [1e-6, 1e-3]) over temperature at +0.5×, which is not yet separated from token-class bias.
  - This is the causal version of the S1 entropy finding: writing the surprise state raises the model's uncertainty.
- **Probe readout direction:** no directional effect. It raises `E[−ln p]` for both signs, like the random control (1.17 / 1.08 versus random 0.96 / 0.92 at ∓0.5×). Read and write directions differ, so use CAA-style vectors for steering.
- **Random control:** raises `E[−ln p]` symmetrically for both signs; this is generic damage. Argmax agreement is about 0.975 even at ±0.1×, which is the near-tie floor.
- **Implication for K1:** surprise → surprise state → higher entropy → more surprising samples is a *positive*-feedback candidate. Does the slow surprise-level variable return after a kick (outvoting or regulation), or run away (degeneration)? That is the first K1 test, and the CAA vector is a ready-made push for K2.

### S2b: One steering vector per p that promotes only tokens of probability p (the user's design)

- **Data.** `homeo-band` → `/mnt/models/homeo/band2`: 384 prefixes from 192 rollouts, branched into arms decoded in one batch per step.
  - normal: temperature 1
  - band:P for P ∈ {0.8, 0.5, 0.25, 0.1, 0.03, 0.01}: sample among tokens with p ∈ [P/1.5, 1.5P] when any exist, otherwise sample normally
  - 32 steps per arm; the last 24 are captured.
  - The first attempt (`band_nearest_fallback`) fell back to the token nearest P, which made the band arms mostly greedy. Discarded.
- **Band hit rates are low.** A band token exists at only 26% of steps for P = 0.25 (34% for 0.1, 47% for 0.03).
- **Vectors** (`homeo/s2b_band_vecs.py`):
  - band − normal (the user's design)
  - "bracket": band − the neighbor band arms, weighted so the neighbors' realized surprisal matches the band arm's. This cancels anything linear in surprisal (the user's control).
- **Activation results.**
  - band − normal is reliable only for P ≤ 0.03 (split-half cosine > 0.8), and there it is the S1 surprise vector (cosine 0.75–0.84). For P ≥ 0.5 it is the negative surprise vector (−0.6 to −0.7). For P = 0.25 it is noise (split-half ~0).
  - Bracket vectors are noise at every level and layer (split-half −0.1 to +0.2). Once surprise is controlled, band-sampled text has no reliable activation signature.
- **Steering results (L40, 8 rollouts, exact).** No vector promotes only its band.
  - band − normal acts as the temperature dial plus a tail bias. Raising the target band always comes with equal or larger changes in other bands:
    - P = 0.5 at +0.2: ×1.12 against ×1.14 for the matched temperature (T = 0.87)
    - P = 0.25 at +0.4: ×1.07 against ×1.04, but the p ~ 0.1 / 0.03 bands go ×1.14 / ×1.22
    - P = 0.1 at +0.4: ×1.10 against ×1.02, but the 0.03 / 0.01 bands go ×1.48 / ×1.99
    - P = 0.03 at +0.4: ×1.64 against ×1.39, but the 0.01 band goes ×2.37
  - Bracket vectors stay within about 3% of their temperature match up to +0.2. At +0.4 they raise the tails like a random push.
  - The rate at which the steered argmax becomes a target-band token stays at the noise level of the near-tie flips.
- **Not yet ruled out:** a vector that exists but is not represented in band-sampled text (a weak regime: only about 26% of tokens differ). The direct test is S2(c): optimize v through the model (jspace backward) on a band-mass objective with held-out contexts.

### S2c: Raw-logit bands (pre-softmax) instead of probability bands

- **Data.** `homeo-steer --dump-raw` → `/mnt/models/homeo/logits/raw.f16`: 4048 positions × 151343 vocab. Analysis in `homeo/s2c_logit_identity.py`.
- **Scale.** The top logit has median 25.1 (5–95%: 17.2–30.1); logsumexp has median 25.2 (18.3–30.2). A fixed logit band therefore maps to very different probabilities depending on context.
- **Context, not token identity, decides band membership.** Token identity explains 47% of raw-logit variance over the whole vocabulary, but that is the junk tail that is always low. For every band that holds real probability mass (z ≥ ~11, i.e. the top ~40 tokens), a token in the band at one position is in the same band at a random other position only 0–3% of the time. No token is in-band at ≥ 50% of positions, so there is no token set an identity-bias vector could target.
  - Identity AUC is 0.8–0.94, but that only says which tokens are ever eligible (real words versus junk).
  - Membership only becomes token-like (stickiness 0.12–0.35) below z ≈ 5, where the band holds < 0.2% probability.
- **Conclusion.** Within a context, logit order equals probability order. With no identity escape hatch, a logit-band vector faces the same reordering problem as S2b, so the result carries over. The remaining definitive test for both kinds of band is S2(c), optimization through the model.

### S2(c): Vector optimized through the model (backprop): result

- **Tool.** `homeo-steeropt`: jspace graph plus `jlens_build_forward_steer`, a learnable v [n_embd] after block L, broadcast to all positions.
  - Loss: soft-label cross-entropy against r ~ p·(1 + 3·[x in band]), i.e. "band tokens ×4, everything else in proportion".
  - Backward runs through blocks > L and the Q6_K head (`out_prod` dequantizes). Adam runs on the host.
  - 48 training / 16 held-out windows of 128 tokens, split by document (doc_idx % 4 == 0 → held-out).
  - Gradient check along the gradient direction: FD/analytic ratio 1.11 / 0.88 / 0.50 at h = 8 / 16 / 32. That is curvature at large h plus 8-bit activation rounding noise at small h. Random-direction checks need h ≥ 16 because of that rounding.
  - The first run (lr 0.03, 2-window batches) was too noisy to trust. Final settings: lr 0.02, 4-window batches, 200 steps, L40.
- **Positive control (target = temperature 1.3) works.** Held-out CE 2.553 → 2.429 against a floor of 2.380, i.e. 72% of the reachable improvement, and still improving. The optimizer finds and generalizes a vector when one exists.
- **Band targets: nothing.** Held-out CE for v = 0 → best single temperature → optimized v (floor in brackets):
  - p = 0.5: 1.1235 → 1.1125 (T = 0.90) → 1.1163 at step 50, 1.1194 at step 200 (1.0705)
  - p = 0.25: 1.2113 → 1.2077 (T = 0.95) → 1.2189, worse than nothing (1.1459)
  - p = 0.1: 1.3195 → 1.3195 (T = 1.00) → 1.3259 (1.2397)
  - p = 0.03: 1.4265 → 1.4255 (T = 1.05) → 1.4248 at step 50, 1.4285 at step 200 (1.3613)
  - Even on the training windows, CE improves by only ~0.003–0.004.
  - The best temperature matches or beats the optimized vector for every band. The optimized vector reaches 0–16% of the gap on held-out text, against 72% for the temperature control.
- **Exact evaluation (`homeo-steer`) agrees.**
  - The p = 0.5 vector is a sharpener: its band goes ×1.12 against ×1.12 for the matched temperature.
  - The p = 0.03 vector flattens with a tail bias.
  - The p = 0.25 and 0.1 vectors do almost nothing; the bands below them rise as much as their own.
- **Conclusion.** At L40 of GLM-4-32B-Base there is no single additive steering vector that promotes only tokens of a given probability (and, per S2c, of a given raw logit). Along the "how likely is the next token" axis, what is steerable reduces to temperature plus token-identity biases.
- **Caveats.** Only one layer was tested. A single vector at all positions, an ×4 upweight target, 200 steps. More steps would not help: held-out CE for the bands got worse after step 50. Earlier layers (more nonlinearity downstream) are the remaining untested option.

### S2(d): Large doses (queued 2026-10-14, `/mnt/models/homeo/s2big/run.sh`)

The user's point: "if a steering ever seems to do nothing, turn it up". In their experience, control vectors often need scale 5–10 × the raw mean-difference vector over a layer band. Mean-difference vectors here are about 0.4 × the residual norm, so that is roughly 2–4 × the residual norm per layer.

What we had tested:
- S2: up to 0.5×.
- S2b: up to 0.4×.
- S2(c): the optimized vectors stayed at 0.03–0.14 × the residual norm (temperature 0.08–0.14, bands 0.03–0.08) and were evaluated at up to 2 × their own size. Gradient descent from 0 cannot cross a hump where small doses hurt and only large ones help.

New tests:
1. **Single-layer dose ladder** (homeo-steer):
   - optimized vectors at 1–64 × their learned size, up to about 4–9 × the residual norm;
   - the probe direction at ±1, 2, 4;
   - band and bracket vectors at 0.8, 1.6, 3.2.
2. **Multi-layer steering** (new `homeo-steer --layer-end`): the same direction after every block in 24..40.
   - the CAA vector at −1 to +4;
   - band and bracket vectors at 0.25–4.
3. **Fixed-norm search** (new `homeo-steeropt --fixed-norm s [--init-vec]`): Adam on the sphere |v| = s × mean |h|, using tangent-space gradients and renormalization.
   - s = 0.5, 1, 2;
   - starting from a random direction and from the small learned direction;
   - temperature control, p0.25 and p0.1 at L40, and p0.1 at L53.

Readout is specificity (target band against matched temperature and other bands, and CE against the band target), not whether anything changes. Everything is teacher-forced.

**Late-layer effect in the sweep.** For low bands, vectors at layers 44–58 beat the best global temperature. The vectors are still small, about 0.075 × the residual norm.

| Band | Best layer | Gap closed | Band mass | Best global temperature | KL(nonband) | Top token changed |
|---|---|---|---|---|---|---|
| p0.03 | L52–56 | 6–7% | ×1.14 | 1.6% gap, ×1.06 | 0.006 (temperature 0.005) | 2–3% |
| p0.1 | L53 | 4.7% | ×1.07 | 0% | | |
| p0.25 | | 3.4% | | 5.5% | | |

Possible explanations: the vector reads p, or it biases token types that tend to sit near p ≈ 0.03.

**S2(d) results, parts 0–2 (2026-10-14).**
- **Within-token test, after fixing the centering.** v1 centered d per position but not ln p, which left a fake hump even for exact temperature. Both are now centered per position, and exact temperature on synthetic data gives a residual of 0.

  | Vector | Within-token band − rest |
  |---|---|
  | Temperature vector, L50 (control) | +0.025 at s1, +0.006 at s4 |
  | p0.03, L56 | +0.040 / +0.144 / +0.200 at s1 / s4 / s16 |
  | p0.1, L53 | +0.047 at s4, −0.10 at s16 |

  At s4 the p0.03 vector's shape is a hump at p ≈ 0.01–0.03, with the top tokens and the deep tail suppressed beyond what temperature does. The p0.1 vector makes a similar hump that does not sit on its own band.
- **Mass by p bin, p0.03 L56 ×4 against exact temperature matched on E[−ln p] (T = 1.20):**

  | p range | Base | Vector | Temperature |
  |---|---|---|---|
  | > 0.32 | 0.791 | 0.726 | 0.748 |
  | 0.01–0.03 | 0.028 | 0.047 | 0.037 |
  | 0.001–0.01 | 0.029 | 0.050 | 0.041 |
  | < 1e-4 | 0.006 | 0.007 | 0.014 |

  So it acts like temperature applied within the plausible set (truncation, then temperature): it is a second shape knob, not a dial for a chosen band. The temperature vector, by contrast, matches exact temperature in every bin.
- **Dose ladder.** Every vector destroys the output beyond about 1–2 × the residual norm at one layer (KL > 10, argmax agreement ≈ 0). Multi-layer steering (24–40, same direction) destroys it even at 0.25 per layer, so the ladder was mis-scaled; K4b doses were moved to 0.01–0.5.

- **Fixed-norm search (part 3; 100 steps, lr-frac 0.03).** Held-out CE at the end of the search, against v = 0:

  | Target | s = 0.5 | s = 1 | s = 2 |
  |---|---|---|---|
  | temp 1.3 (gap 2.553 → floor 2.380) | 2.446–2.448 (≈61% of the gap) | 2.518–2.553 (0–20%) | 2.87–2.95 (worse than v = 0) |
  | p0.25 L40 (v0 1.211) | 1.257–1.268 | 1.33–1.36 | 1.72–1.80 |
  | p0.1 L40 (v0 1.3195) | 1.362–1.369 | 1.44–1.46 | 1.83–1.92 |
  | p0.1 L53 (v0 1.3195) | 1.358–1.359 (band ×1.11–1.16) | 1.47–1.49 | 2.20 |

  - Every band search at every norm ended worse than doing nothing. There is no hidden large-dose band direction.
  - At s ≥ 1 even the control mostly fails, so steering at those doses is mostly damage.
  - Random and "small" starts agree.
- **Exposure:** S2(d) logged 42 rows, about 2.97M positions under steering (teacher-forced, A1).
- **Visualization:** https://claude.ai/artifact/6KuTYAQqyhGrXPjL1hYJ1y ("Same Surprise, Different Tail": token waffles and boost by likelihood, ×1/4/16/32).

**Part 0 of `s2big/run.sh` (`homeo/s2d_within_token.py`).** It dumps the top-64 tokens per position (ids, log p, log q), centers the boost d = log q − log p per position, fits the temperature line (d linear in ln p), then compares the residual bump in the band with the rest, both raw and within token (each token's mean across contexts subtracted).

Validated on synthetic data:

| Synthetic case | Band effect, raw | Band effect, within token |
|---|---|---|
| p-reading boost | +0.24 | +0.24 |
| Identity bias correlated with the band | +0.16 | −0.02 |

### S2 design

Can one steering vector, scaled, make the model pick tokens of a chosen probability level p?

- **Exact metric, no sampling noise.** For each context and scale c, compute the steered distribution `q_c` and the unsteered `p`. Bin `q_c`'s mass by `log p(x)`. Also check whether steering preserves rank order (Spearman between `q_c` and `p` over the top N tokens) and compare against the temperature family `q_T ∝ p^{1/T}`, matched on `E[log p]`.
- **Prediction.** A single additive direction acts like temperature plus token-identity biases. It changes the residual norm, the final RMSNorm rescales the logits, and the model favours globally rare tokens. Temperature never reorders tokens, while a true "pick p*" band-pass has to push the argmax below p*-level tokens. A finite residual vector can only scale and shift the final-layer logits, so a band-pass would need nonlinear mid-network machinery. Finding one would be surprising and interesting.
- **Candidate vectors.**
  - (a) the S1 probe direction (write "that was weird")
  - (b) CAA (contrastive activation addition) on next-token-rare versus next-token-common positions, which mostly captures entropy
  - (c) a vector optimized with jspace backward against a band-pass or tempered target, to see whether one direction at different scales gives the whole family

### K1: Kick-response memory curves (main homeostasis instrument)

- **Procedure.** Fork a rollout at t. One branch takes a forced token from a surprisal bin; the null branch takes another token the model itself sampled. Continue both with shared seeds. Gap `d_k = h^A_{t+k} − h^B_{t+k}` at a few mid layers.
- **Analysis.** `C_k = E[d_k d_kᵀ]` per dose bin. Solve the generalized eigenproblem between `C_early` (k = 2–3) and `C_late`. A ratio ≫1 means the direction is kicked and restored; ≈1 means the kick persists; <1 means it is amplified. Compare each dose against the natural-fork null.
- **Regress out prediction.** Per lag, remove the gap explained by `KL`/`TV` between the branches' next-token distributions (principle 5).

### K2: Finite activation push-and-release (certification)

- Use `llama_set_adapter_cvec` at layer l only, with position s decoded as its own single-token decode call, then clear it. `build_cvec` adds at the layer output in the glm4/llama builders.
- Gotcha: a cvec applies to every token in a decode call, so pushed branches need their own call. Use separate calls for +α and −α.
- Run ±α pairs: the odd part is the response, and the even part is the linearity check.
- Use a dose ladder up to the escape threshold (the margin). Baseline: re-establishment in a fresh branch (`llama_memory_seq_cp`).

### K3: Positive and negative controls (instrument gate)

- A random single token inserted mid-text must classify as *restored*.
- A coherent plot switch ("Suddenly it was night.") must classify as *committed*.
- If the instrument can't separate these two, nothing else it says counts.

### K4: Loop margin (is not-looping a maintained basin?)

The user's observation (2026-10-14): almost every steering vector makes the model loop exclusively when turned up too high, and heavy quantization also tends to fail into loops. Hypothesis: looping is the default, and not looping is a carefully maintained basin. The healthy regime sits between two self-reinforcing traps, Mirostat's "boredom" (repetition) and "confusion" (incoherence), and damage pushes the model toward boredom.

- **Two readings.**
  - Held by accurate prediction (fragile, passive): an intact model reproduces real text's low repetition rate, and damage removes that knowledge.
  - Held by negative feedback (a regulator): copy-suppression heads (McDougall et al. 2023) sense earlier copies of the predicted token and lower its logit.
  - Evidence so far leans passive at lag 1: surprise feeds more surprise (S1/S2), and repetition reinforces itself (Xu et al. 2022).
- **Two damage mechanisms to separate.**
  - *State collapse:* a large constant vector makes every position alike, so the output is constant. Expect period-1 loops at doses near or above the residual norm.
  - *Copying fallback:* induction circuits are simple and redundant, so they are the last thing to break. Expect long-period loops, including under quantization.
  - S2's random pushes at ±0.5× the residual norm *raised* entropy, so expect a two-phase dose response: confusion first, then loops. Measure where it flips.
- **Tests.**
  - Dose ladder in natural units across random directions and the existing vectors. Record loop onset (repeated n-gram rate in 256-token continuations, T=1, min_p 0) and loop period, and check whether onset is the same in every direction.
  - Ablate copy-suppression-like heads: does the margin shrink and does the T=1 loop rate rise? That is the thermostat test for repetition.
  - Quant ladder (Q4 / Q3 / Q2): does quantization break the regulator before the content?
- **Tool (built 2026-10-14):** `llama.cpp/tools/homeo/homeo-loop.cpp`, `homeo/k4_loop_summary.py`, `/mnt/models/homeo/k4/run.sh`.
  - Steering: cvec after block L, at all positions (prefill and generation); dose = unit vector × dose × mean |h_L| (L44: 358).
  - Prefixes: 16 held-out prefixes of 256 tokens; up to 128 generated tokens at T=1, untruncated, with shared per-prefix uniforms.
  - Endpoints: loop (period ≤ 16 over max(3p, 12) tokens) or incoherence (H > 6 for 16 steps). Ladder stops at the first dose where ≥ 75% loop.
  - `--neg` also runs negated vectors. Every arm is logged to `welfare_log.csv`.
  - The user's gguf cvectors in reality-cvector are for gemma4/talkie, not GLM-4, so they are not used.
- **Results (2026-10-14, `/mnt/models/homeo/k4/k4_summary.txt`; T=1 untruncated, single layer, 16 prefixes × ≤128 tokens).** Unsteered: no loops, no incoherence, H32 1.59 nats, distinct-4-gram rate 0.98.
  - **Random directions do not loop; they go incoherent (the confusion trap).** Across 9 random directions at L40/L44, loops are essentially zero at every dose (at most 1–2 of 16 sequences). Incoherence (H > 6 nats for 16 steps) takes over at 1–3 × the residual norm; the dose where most sequences hit it is 1.0–3.0, median about 1.5. Mean entropy climbs steadily with dose (H32 to 8–9 nats).
  - **Loops come from sharpening directions (the boredom trap):**
    - −temperature vector (L40): loop fraction 0.06 / 0.12 / 0.44 / 0.75 at 0.25 / 0.5 / 0.75 / 1.0, so the loop margin is 1.0 × the residual norm. H32 falls to 0.3 nats.
    - p0.25-optimized vector (a mild sharpener; L40): 0.12–0.44 loops at 0.75–2 ×, then incoherent at 3 ×.
    - −CAA (L44): up to 0.31 loops at 1.5 ×, then incoherent at 3 ×.
  - **Flattening directions:** +temperature and +CAA reach incoherence earliest (0.5 ×). The probe direction reaches it at 0.75 ×, or 1.5 × negated.
  - **Loops are mostly long-period** (phrase-level, periods 3–11, often with drift: "Black Nail with Glitter / Black Nail with Gliter"), not period-1 spam. The only period-1 loops are 5/16 for −CAA at 1.5 ×.
  - **The two-phase prediction (confusion, then loops) is not seen.** The p0.25 vector shows the reverse: loops first, then incoherence at 3 ×.
  - **Reading.** At T=1, the two traps sit at the two ends of the temperature axis. Generic damage behaves like flattening, so it leads to confusion, not loops. The user's experience of loops at high scale (gemma/talkie; multi-layer bands; T 0.8, top-p 0.95, repetition penalty) may come from multi-layer state collapse or from truncated sampling. K4b (multi-layer, blocks 24..40, `k4/run_band.sh`) is queued to test the first.
  - **Exposure (welfare_log.csv):** 123 arms, 1,968 contexts, 165,543 generated tokens in perturbed states. Incoherent runs were cut at about 16 tokens by the endpoint.
- **K4b, multi-layer (blocks 24..40; dose × |h_24| per layer; 2026-10-14, `k4/k4b_summary.txt`).** Both of the user's failure modes reproduce, and the direction decides which one appears:
  - **−CAA (sharpening):** entropy falls at 0.05–0.1 (H32 0.8). At 0.25, the text degrades with emerging loops (25%, "and, and, and,"). At 0.5, 16/16 sequences are **period-1 spam** with onset at step 0–3: "the the the the the". This is exactly the user's "the the the".
  - **Random directions:** essentially no loops (1/16 once). They go to **multilingual mush** ("ufc党和乐于 fair Tenqual roasted*num…"), which is the user's "foreign-character mush"; the endpoint is reached at 0.25–0.5 per layer or not at all.
  - **+CAA:** incoherent at 0.25.
  - **Single layer vs band:** single-layer sharpening gave phrase-level loops, while band sharpening gives single-token spam, which matches the state-collapse mechanism.
  - **Hypothesis for "almost every vector loops":** concept vectors make the model more certain (about the concept), so they carry a sharpening component, and turned up they collapse onto the concept's words (cf. the user's "iridescent iridescent… kaleidoscope"). Test: build a concept CAA vector on GLM, measure its projection on the temperature axis, and run K4/K4b on it.
  - **Exposure:** 36 arms, 576 contexts, 64,216 tokens. The A2 stop rule ended ladders early where it applied.

### X1 (cross-check): Closed-loop linear response through the score

For k ≥ 1, on-policy:

`d/dα E[v_{s+k}] = E[(u·g_s) · v_{s+k}]`, where `g_s = ∇_{h_{s,l}} Σ_t log q(x_{t+1})`

So `P^cl_k = mean_s (h_{s+k,l} − b) g_sᵀ` from one forward plus backward pass per rollout (jspace: seed the backward at the logits with the score of the sampler distribution, `(e_x − q_S)/T` on the support). Terms with t ≥ s+k vanish in expectation (variance, not bias).

Caveats: it is infinitesimal, and the variance is probably large for 6144² matrices. Use it to cross-check K1/K2 on a few directions, not as the discovery tool.

### X2 (diagnostic): Lagged J-lens (echo decomposition)

Run jlens-fit with shifted outer products, `M_k += V[:, s+k] U[:, s]ᵀ`, which gives `Σ_s J_{s+k←s}` into a deeper layer. The k = 0 slice is the J-lens; `--xpos` is the sum over k. This splits a response into the continuous echo versus the part carried by tokens.

## Measured instrument facts

- **The existing rollouts are not pure ancestral samples.** `gen_rollouts.py` never disabled llama-server's default `min_p = 0.05`. Measured: mean surprisal 0.51 nats against mean entropy 0.70 (these are equal on-policy), and only 0.15% of tokens exceed 5 nats. New on-policy rollouts need `min_p: 0` explicitly.
- **Batch shape changes the numerics.** Comparing a 13-token branch decode against the 512-token natural pass at the same position (GLM-4-32B Q4_K_S, CUDA, flash attention; 1591 paired rows):
  - the residual differs by a median 1.5–2% relative, and 99th percentile 3–15% (worst at L44)
  - 7 outliers above 20%, all at positions above 1700
  - next-token entropy differs by median 0.001 nats, 99th percentile 0.09

  So any comparison between branches (K1/K2) must decode all arms with the same batch shape. Never compare a branch against the main pass.

## Tooling

- `llama.cpp/tools/homeo/homeo-capture`: libllama, KV branching with `seq_cp`, `cb_eval` capture of `l_out-N`. Writes `labels.bin`, `samples.bin`, `acts_L*.f16`, `meta.json`.
- `llama.cpp/tools/jspace`: hand-built GLM-4 graph with ggml backward. Used for X1, X2 and S2(c).
- Python: `~/.venv` (torch 2.9 + CUDA). Import torch before numpy, otherwise numpy fails to find libz/libstdc++ on this box.
