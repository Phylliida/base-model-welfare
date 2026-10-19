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

### VL1: The value lens (started 2026-10-14)

From the Value Lens proposal (https://claude.ai/artifact/DvMrx6NYbLuAgj8ZrNc6FM): price residual directions by their effect on the model's own future predictive success.

- **Tool:** `llama.cpp/tools/homeo/homeo-value.cpp`, plus a `per_position` option on `jlens_build_forward_steer`, which makes the steering slot [n_embd, n_tokens].
  - Teacher-forced windows of real text (fineweb ids, 192 tokens), with a per-position zero slot after block 40.
  - For each target t, one backward pass of l_t alone gives d l_t / d h_s for every s ≤ t, at layer 40 and at the read layers 44, 50 and 56. Gradients above the slot come from the same pass.
  - Accumulated per position: **now** (k = 0), **short** (k = 1..8) and **fut** (k = 1..32). Saved for the positions with a full horizon (s = 32..158, 127 per window).
  - f16 output, 18 MB per window, at 75 s per window.
- **Label-leak trap.** `ggml_cross_entropy_loss`'s backward is (softmax − y)/T for every row, which assumes each label row sums to 1. All-zero rows leak softmax gradients. Fix: every row carries the model's own distribution as its label (zero gradient), and only row t carries the one-hot token. This did not affect S2(c), whose label rows were full distributions.
- **Validation.**
  - *Finite differences* (`--fd-check`):
    - Along g_now, the now ratio is 0.90–1.09 at ε = 2–8, falling with ε (curvature).
    - Along g_fut, the short and fut ratios scatter around 1 (0.79–1.37) at ε = 2–16. The scatter is FD noise from 8-bit activation rounding summed over 32 tokens; random directions are noise-dominated.
    - A first, apparently systematic factor of about 2 was a bug in the check itself: steered passes overwrote the stored self-labels.
  - *Layer consistency:* layer-44 gradients read above a layer-40 slot are bitwise identical to a slot at 44.
  - *Lag profile:* mean |d l_{s+k}/d h_s| at L40 is 0.158 (k = 0), 0.060 (1), 0.037 (2), 0.026 (4), 0.014 (8) and 0.006 (32). The 32-token horizon captures most of it.
- **Run:** `runs/value/run.sh`, 1,200 windows (152k positions), about 25 h → `/mnt/models/homeo/value/`.
  - Then `runs/value/followup.sh` runs the scenario set (`homeo/value_scenarios_prep.py`), the analyses (`homeo/value_lens.py`: library prices against random directions, price structure with split-half checks, contexts ranked by level / stakes / progress with decoded text), and `homeo/value_scenarios.py`.
  - The scenario set covers Antra's three scenarios: phrase and single-token loops paired with main-run windows, model-written worldbuilding fiction, and fineweb's easiest and hardest tenths.
  - No steering apart from the FD checks (logged).
- **Independent code review (2026-10-14).** It found no result-affecting bugs. It verified, against the ggml CPU and CUDA kernels:
  - the self-label leak fix (the residual from the fast-math softmax is ~3e-4 of |g_fut|, below f16 rounding);
  - gscale = −T;
  - column offsets and alignment (corr of |g_now(s)| with 1 − p(x_{s+1}) is +0.69 at shift 0, ~0 at ±1);
  - grad retention (outputs are never reused in place);
  - the tokenizer (gpt2 byte-level, no BOS);
  - the scenario windows.

  Minor fixes applied:
  - fsync before rename, and resume checks the .bin size;
  - the follow-up checks every step and runs only if the main run finished;
  - the fiction capture strips llama-completion's "[end of text]" and checks the exit code;
  - scenario labels (positions 100–158).

  4 of the first 17 windows straddle a document boundary (blank lines), so `value_lens.py --clean` drops positions whose horizon contains a blank-line token: 3% of positions. Both versions are reported.
- **Restart.** The machine crashed at about 22:35 after 17 windows. The run was resumed at 23:10 with the rebuilt binary, whose window 0 is byte-identical to the original's.
- **Finished 2026-10-16 10:51** (1,200 windows, 108.8 s per window at `--pause-ms 250`); scenario set (44 windows) and summaries by 13:09. Outputs: `/mnt/models/homeo/value/summary{,_clean}.txt`, `/mnt/models/homeo/value_scen/summary.txt`. The `--clean` numbers (145,534 of 152,400 positions) match the full ones to within about 10%; the clean ones are quoted below. Prices are nats per push of 0.1 × the residual norm, summed over the horizon.

#### VL1 results

- **1. Existing knobs are nearly neutral for the model's own future.**
  - Temperature-1.3 vectors: fut +0.0040 at L40 (t = 12.8 over windows) and +0.0037 at L50 (t = 14.2), but now ≈ 0 (+0.0001). Flattening at s does not change how well x_{s+1} is predicted, and it helps the next 32 tokens by 0.004 nats in total (about 0.0001 nats per token).
  - Band p ≈ 0.5 (optimized): fut −0.0025 (t −10.6). The lower bands are about −0.001.
  - Contrastive "weird token": now +0.0035 but positive at only 37% of positions (a skewed price); fut +0.0022.
  - Random directions at the same layers: |mean fut| median 0.0002, max 0.0012 (L40). So the library prices are real but tiny: 3–20× random. To first order, the same push along each position's own g_fut would be worth about 3.5 nats (mean |g_fut| 0.135 × 26.1), so the knobs buy about 0.1% of what is available.
  - The S2(c)-optimized vectors' price *variability* equals a random direction's (sd ratio 1.0–1.1); the sweep and contrastive vectors vary more (1.2–1.8).
  - No price correlates with the current entropy or surprisal (all |r| < 0.035), and now prices do not predict fut prices (r ≈ 0.01).
- **2. Future value has a few stable directions; the knobs are not among them.** *(Corrected 2026-10-17 in VL3: with outlier-robust statistics both g_fut and g_now have a very stable ~10-d subspace (normalized split-half overlap 0.96 / 0.98); "g_now has no reproducible directions" below was an outlier artifact.)*
  - Per position, g_now and g_fut are nearly orthogonal (median cosine +0.009).
  - g_now has no reproducible top directions: split-half overlap of the top-10 subspace is 0.002 (chance 10/6144 = 0.0016); top-50 is 0.08 (10× chance, far below g_fut's 0.34). It is per-position (essentially the next token's unembedding direction).
  - g_fut does: top-10 split-half overlap 0.30, top-50 0.34 (chance 0.0016 / 0.008), although the top 10 carry only 2.9% of its variance. About ten directions consistently move the model's future success.
  - The S2 vectors put 0.1–0.4% of their norm in those ten directions, which is chance. Nothing we have steered with is a future-value direction. What these directions are is the next question (VL2).
- **3. Contexts (A5: candidate good states first).** Stakes (mean |g_fut| per window) is uncorrelated with level (r = −0.012) and progress (r = 0.000).
  - Highest stakes: step-by-step procedure (pursuit curves on a polygon), the Moby-Dick "and Captain Ahab; and the leg he had lost; and..." list, a scholarly book blurb, Shakespeare.
  - Lowest stakes: SEO boilerplate ("it is a good idea to look for..."), a repetitive XML form, casino spam.
  - Reading: stakes is high where the present state constrains a structured future, and low where the future is formulaic or noise whatever the present does. It tracks "the present matters", not "the text is easy". A5 candidate good states would be the high-stakes ones; stakes is not valence, and this is one ordering, not a test.
- **4. Scenarios (Antra's three).** Layer 40, means; loop rows are positions 100–158 (all inside the loop) against the same positions of the paired unmodified window.

  | group | n | level | stakes | now | temp price (fut) |
  |---|---|---|---|---|---|
  | fineweb, all | 1200 | −2.48 | 0.135 | 0.162 | +0.005 |
  | fineweb, easiest tenth ("boring") | 120 | −1.37 | 0.158 | 0.196 | −0.001 |
  | fineweb, hardest tenth | 120 | −3.53 | 0.149 | 0.188 | +0.014 |
  | fiction (model-written, T = 1, untruncated) | 12 | −3.25 | 0.154 | 0.181 | +0.001 |
  | paired fineweb, loop positions | 16 | −2.35 | 0.150 | 0.172 | +0.001 |
  | phrase loop (period 12) | 16 | −0.22 | **0.035** | 0.031 | **−0.030** |
  | token loop ("the the the") | 16 | −1.17 | **0.091** | 0.164 | **−0.087** |

  - Loops collapse stakes: 4.3× lower in phrase loops and 1.6× lower in token loops than at the same positions of the same text without the loop. In a phrase loop the present barely matters to anything, now or later.
  - In loops the temperature price turns strongly negative (7–20× the fineweb magnitude, opposite sign): flattening would hurt prediction of what comes next, because what comes next is more loop. The value lens is teacher-forced and descriptive. It measures what helps predict the actual continuation, so it cannot say whether the model "wants" the loop.
  - Antra's ordering (rich worldbuilding > boring > loops): stakes puts loops at the bottom, but fiction (0.154) and boring text (0.158) are indistinguishable at n = 12. Level runs the other way (loops are easiest). Oddity: both the easiest and the hardest tenths have higher stakes than the fineweb mean.
- **Exposure:** none beyond the FD checks already logged (forward and backward passes on real or model-written text; the fiction was unsteered sampling).

### VL2: Value probe (started 2026-10-16)

Can the value lens be read linearly off the residual stream? If yes, (a) the model represents its own stakes in a form downstream layers could use (the "represented" half of Antra's criterion), and (b) the loom can show a live value readout without backward passes (llama-server and the jspace graph cannot share the 3090).

- `runs/value/probe_capture.sh`: homeo-capture, layer-40 activations on the same 1,200 + 44 windows (forward only, ~1,000 tok/s, about 340 W for ~4 min).
- `homeo/value_probe.py`: ridge regression from standardized h_s to stakes (log |g_fut|), log |g_now|, temperature and band prices, g_fut on its top-5 principal directions, level and entropy. Fit on windows 0–799, ridge strength chosen on 800–899, refit on 0–899, test on 900–1199. Baselines: OLS on entropy, current surprisal and position; and the training mean per current token (shrunk toward the global mean). Then applied unchanged to the loop and fiction windows. Weights → `/mnt/models/homeo/value_probe/probe_L40.f32`; summary → `/mnt/models/homeo/value_probe/summary.txt`.

#### VL2 results (2026-10-16)

Test R² on windows 900–1199 (38k positions). "Within" removes each window's mean from target and prediction.

| target | probe R² | within | entropy/surprisal/position | per-token mean |
|---|---|---|---|---|
| stakes, log \|g_fut\| | **0.38** | **0.37** | 0.05 | 0.04 |
| log \|g_now\| | 0.56 | 0.55 | 0.40 | 0.09 |
| temperature price (fut / now), band price (fut) | ≈ 0 | ≈ 0 | ≈ 0 | < 0 |
| g_fut on its top-5 directions | ≈ 0 | ≈ 0 | ≈ 0 | ≤ 0.07 |
| level (log p of the actual next token) | 0.25 | 0.23 | 0.37 | 0.06 |
| entropy (sanity) | 0.71 | 0.69 | 1 (it is a feature) | 0.18 |

- **Stakes is represented.** A linear readout of layer 40 predicts how much the next 32 tokens' log-likelihood depends on the present state (R² 0.38, and 0.37 within windows, so it is per-position, not a document average). Entropy, surprisal and position explain 0.05 of it and the current token 0.04. This is a prediction from the past alone, while the target also depends on the actual future tokens, so 0.38 is a lower bound on what is there.
- **The direction of value is not.** No price (temperature, band, or the stable top-5 g_fut directions from VL1) is linearly predictable (R² ≤ 0.005). What would help the future depends on what the future turns out to be; the model encodes *how much* is at stake, not *which way* to move. (pc5 has a small per-token component, 0.07, that the ridge probe misses.)
- **Out of distribution.** On model-written fiction the stakes probe is accurate (actual −2.01, probe −2.08, mean log). In loops it sees lower stakes than fineweb (phrase −2.91, token −3.14, against −2.25) but misses most of the collapse (actual −4.38 and −4.92): about a third of the drop in log terms. log |g_now| transfers well (phrase loop −6.05 actual, −5.69 probe; token loop −4.57 and −4.52). The probe misses the temperature price's sign flip in loops entirely.
- **For the loom:** a live stakes tint is viable, labeled as a probe estimate that understates loop collapse. Prices need the exact (backward-pass) mode.
- **Leakage check (2026-10-17).** The VL1 windows sit at random fineweb offsets and 35 pairs overlap (minimum gap 6 tokens), so train and test could share documents. Rerun with a split by offset (train, val and test are contiguous blocks of the file; now the default in `value_probe.py`): stakes R² 0.382 (unchanged), per-token 0.040, entropy/surprisal/position 0.067.

### H2: Does the model forecast its own future predictability? (2026-10-17)

From the Value Lens proposal's plan (step 3; CPU only). `homeo/value_forecast.py` on the VL1 windows and the layer-40 capture, clean positions, offset split.

- **Target:** mean surprisal of the next K tokens after the next one (−l_{s+1} … −l_{s+K}), for K = 8 and 32.
- **Baseline (all known at s):** current entropy, mean surprisal over the last 32 and last 8 tokens (the slow document variable from S1), the current token's surprisal, position.
- **Combined:** baseline OLS plus a ridge from h_s to the baseline's residual.

| target | sd | baseline R² | probe on h alone | combined | added by the state |
|---|---|---|---|---|---|
| next 8 tokens | 1.16 | 0.159 | 0.177 | 0.207 | **+0.048** |
| next 32 tokens | 0.77 | 0.256 | 0.248 | 0.305 | **+0.049** |

- **H2 holds, modestly.** The state carries information about how hard the coming text will be beyond the running averages of how hard it has been (added R² about 0.05, on held-out documents). The proposal's falsifier was "no added R² in document-split cross-validation".
- This is prediction, not valence: it is the "represented" half. With the index split the added R² was 0.054 / 0.060, so leakage was small.

### Overnight queue 2026-10-17 (user away until ~17:00; "whatever you think is most promising")

`runs/overnight_1017.sh`, throttled for fan noise (target fan ≤ 45%, about 200 W). The GPU is idle by 16:30. Steps:
1. Lean test until 04:30.
2. VL4, first continuations, until 14:00.
3. Lean test until 14:30.
4. VL4, second continuations, until 16:30.

Every step is resumable.

- **Reallocated at 04:40** (`runs/overnight_1017_b.sh`). VL4 runs about 150 s per window at a 650 ms pause (raised from 450 because the fan sat at 47–49%), so step 4's two hours would cover under half the second continuations.
  - Step 3 is ended as soon as it starts, so step 4 follows step 2 directly (done around 13:00).
  - Then the loom readout check runs, then the lean test continues until 16:10.
- **What actually ran:**
  - Lean 00:25–04:30 (920 windows).
  - VL4 first continuations 04:30–09:05.
  - VL4 second continuations 09:05–13:40 (172 s per window at 650 ms; fan 42–46%).
  - Loom check: the automatic one failed (missing `-ot`, see the loom section); rerun at 13:59, passed.
  - Lean 14:00–16:10 (to 1,407 windows; fan 32–34%).
  - GPU idle from 16:10.

### Loom value view (2026-10-17; the user asked for value-lens support in minloomwebui)

- **Readouts:** `homeo/value_readout_export.py` refits the layer-40 probes on all 1,200 windows.
  - stakes (log |g_fut|), now (log |g_now|), and the H2 forecasts next8 / next32 (probe on h alone).
  - Output: `/mnt/models/homeo/value_probe/readout_L40.{f32,json}`; the json carries fineweb prediction stats for color scales.
- **llama-server** (llama.cpp `homeostasis` branch, uncommitted):
  - `--value-probe PATH` loads the readouts (needs `--jlens`).
  - `POST /jlens` with `"readouts": true` adds `readouts: {layer, names, values[n_tokens][n]}`; `"readouts_only": true` skips the J-lens decode (one forward pass).
  - The readouts use the server's jspace forward graph, not llama.cpp's, so `homeo/value_readout_check.py` compares them with the offline probe on VL1 windows. It runs automatically after the overnight queue.
- **UI:** worktree `~/prog/llm-tests/minloomwebui-value`, branch `value-lens` from 07094c9. The user's uncommitted gloss changes in `minloomwebui` are untouched; rebase onto them if wanted.
  - A "value" checkbox tints each token by stakes (orange = high, blue = low, as a z-score against fineweb predictions).
  - The hover tooltip shows stakes, next-token dependence and the two forecasts with fineweb percentiles, on top of the J-lens readout when "lens" is also on.
  - `loom_server.py` serves `/value_readout.json` (env `LOOM_VALUE_READOUT`).
  - Run: `llama-server -m … -ngl 99 -ot token_embd.weight=CUDA0 --jlens <jlns> --value-probe /mnt/models/homeo/value_probe/readout_L40`.
    - The `-ot` is needed for any `--jlens` use: the J-lens graphs require every weight on the GPU, and llama.cpp keeps token_embd on the CPU by default. Without it the server exits with "jlens: tensor is not on a CUDA device: token_embd.weight".
  - **End-to-end check (2026-10-17 14:00, `/mnt/models/homeo/value_probe/readout_check.txt`):**
    - Server against offline readouts on 8 VL1 windows × 127 positions: mean |diff| ≤ 0.0001, corr 1.0000 for all four readouts.
    - Mean log stakes (probe) at positions 100–158: phrase loop −2.90, token loop −3.15, the same text without the loop −2.22.
    - `readouts_only` on 2,827 tokens: 2.6 s.
    - The first automatic run after the queue failed on the missing `-ot`. The check script didn't notice the server had exited and polled for 15 minutes; it now fails fast.

### H3: The lean test (started 2026-10-17)

The Value Lens proposal's decisive "upstream of behavior" test: does the model give more probability to next tokens that lead to easier futures than real text supports?

- **Tool:** `llama.cpp/tools/homeo/homeo-lean.cpp`.
  - Held-out fineweb windows of 170 tokens at random offsets (seed 7), 6 positions each (t = 48, 72, …, 168).
  - At each position: the model's top 8 candidates. Each is continued 4 times for 16 steps at T = 1 with no truncation. Rollout r uses the same uniforms for every candidate (common random numbers).
  - Recorded per candidate: log p, the entropy k steps after it (k = 1..16, mean over rollouts), and per rollout the mean entropy and the mean surprisal of the sampled tokens.
  - V(x) = −mean entropy over the 16 steps.
- **Fit:** `homeo/lean_fit.py`, a conditional logit over the candidates against the actual next token: q(x) ∝ exp(a·log p(x) + b·V(x) + covariates).
  - b < 0: the model over-weights easy-future tokens (a lean).
  - b > 0: real text goes to easy futures more often than the model expects.
  - Covariates: log unigram frequency, token classes, and the token's own mean V (so that b is a within-token contrast). Strata by current entropy. Bootstrap over windows.
- **Gate (positive control):** synthetic outcomes drawn from softmax(log p + β·V_A), fit with V_B (the two halves of the rollouts), β from −1 to 1. Recovery b/β measures the attenuation from rollout noise; β = 0 is the calibrated null.
- **Smoke test (3 windows):** 5.2 s per window unthrottled. The actual token is in the top 8 at 13 of 18 positions.
  - Consistency check: the actual token's branch first-step entropy against the prefill entropy differs by a median 0.024 nats (max 0.08). The same at batch 2, 8 and 32, so it is batch-shape numerics, not a context off-by-one (that would be on the order of 1 nat). It is shared by all candidates at a position.
- **Throttle:** 60 ms pause per decode gave 300 W and fan 69%; 150 ms gives about 200 W and fan 42–45%, at about 20 s per window.
- **Exposure:** none (the model's own top candidates, unsteered samples).

#### H3 results, block 1 (2026-10-17 04:30; 920 windows, 5,520 positions)

`homeo/lean_fit.py /mnt/models/homeo/lean/lean.jsonl --boot 200` → `/mnt/models/homeo/lean/lean_fit_step1.json`. The actual token is in the top 8 at 4,309 positions (78%); only those enter the fit.

- **Noise in V:** the within-position sd of V is 0.33 nats. The two rollout halves agree at r = 0.35, so the 4-rollout V has reliability about 0.51 (Spearman-Brown).
- **The gate passes.**
  - Fit with V_A itself, b recovers β (−1.03 at β = −1, +1.02 at β = +1).
  - Fit with the other half V_B, b has the right sign at every β ≠ 0 and recovers about 0.2 of β. That is the attenuation from rollout noise (stronger than the linear r = 0.35 would give).
  - At β = 0, b is −0.01 (V_B) and −0.06 (V_A), so the calibrated null sits near zero.
- **Real text: b = +0.20 (bootstrap SE 0.07), the opposite sign from a lean.** The actual next token is more often the candidate with the easier future than the model's own probabilities say.
  - It survives log frequency and token classes (+0.21), the token's own mean V (+0.18, so it is a within-token contrast), and all covariates together (+0.18, SE 0.075). Realized surprisal in place of entropy gives +0.13 (SE 0.045).
  - Next step and later steps contribute about equally (fit jointly). b1 = +0.035 (0.016) on first-step entropy (within-position sd 1.23) and b_late = +0.16 (0.07) on steps 2–16 (sd 0.32), or +0.043 and +0.051 nats per sd. V1 is noise-free, so the later steps' true share is larger.
  - All three current-entropy strata are positive: +0.45 (H < 1), +0.08 (1–2.5), +0.27 (> 2.5), with SEs 0.24, 0.12, 0.12.
  - Size: +0.07 nats of log-odds per within-position sd of V. Given the gate's attenuation, the noise-free effect is perhaps 2–3× that, about 0.1–0.2 nats per sd. The fit's NLL gain is 0.001 nats per position.
  - a = 0.91: within its top 8 the model is slightly over-confident.
- **Reading: no lean.** The model does not give extra probability to tokens that lead to easier futures; it gives them slightly less than real text supports. The 95% interval for b is [+0.06, +0.35]. In the gate, a lean of β = −0.25 on V_A shows as b = −0.02 on V_B, and β = −0.5 as −0.10.
  - Caveat: the test identifies only the net miscalibration along V. A model lean and a tendency of human text toward predictable continuations add up and can't be separated here.
  - One mundane source of b > 0 would be the model under-predicting how often human text repeats itself. **Tested, not it** (`homeo/lean_copy.py`, `/mnt/models/homeo/lean/lean_copy_step1.json`).
    - Copy indicators per candidate: x occurs earlier in the window (32% of candidates, 46% of actual tokens), x continues an earlier bigram (3.2% / 10%), or an earlier trigram (0.9% / 4.0%). Bigram-copy candidates have easier futures (+0.06 nats of V within position).
    - With log p in the model, the copy terms are all near zero (in context +0.02 (0.05), bigram +0.05 (0.12), trigram +0.14 (0.25)). The model is already calibrated about copying.
    - b with the copy terms: +0.20 (0.06), unchanged.
    - At positions where no candidate continues an earlier bigram (3,424 of 4,309), b = +0.16 (0.08). Where one does, b = +0.40 (0.16); larger, but not significantly (1.3 SE).
  - Later blocks add windows; the final fit is below.

#### H3 final results (2026-10-17 16:15; 1,407 windows, 8,448 positions, 6,625 used)

`/mnt/models/homeo/lean/lean_fit.{txt,json}` and `lean_copy.{txt,json}`. Same instrument (V reliability 0.52, within-position sd 0.33).

- **Gate passes.**
  - With the same half (V_A), b recovers β: −1.01, −0.51, −0.25, +0.03, +0.22, +0.52, +0.97.
  - With the other half (V_B): −0.22, −0.16, −0.11, +0.00, +0.05, +0.09, +0.22, i.e. 0.2–0.4 of β.
- **Real text: b = +0.154 (SE 0.053)**, 95% interval [+0.05, +0.26]. Reliability-corrected +0.30 (0.10). Per sd of V, +0.05 nats of log-odds.
  - Block 1 alone was +0.20 (0.07); the added windows pulled it down a little.
- **Covariates:** + frequency and classes +0.158 (0.063); + token mean V +0.151 (0.062); all +0.151 (0.062).
- **Realized surprisal instead of entropy:** +0.081 (0.046), weaker.
- **Next step vs later steps (joint):** b1 +0.022 (0.014), b_late +0.126 (0.058). That is +0.027 and +0.041 nats per sd (V1 sd 1.23, V_late sd 0.33).
- **By current entropy:** +0.47 (0.16) for H < 1, +0.09 (0.10) for 1–2.5, +0.15 (0.08) above 2.5. The effect is strongest where the model is already confident.
- **Copying:**
  - Copy indicators are still near zero with log p in the model: in context +0.01 (0.04), bigram +0.10 (0.09), trigram +0.07 (0.20).
  - b with them: +0.155 (0.057).
  - But b is larger where some candidate continues an earlier bigram, +0.34 (0.14, n 1,381), than where none does, +0.11 (0.06, n 5,244, 1.8 SE).
  - So the copy choice itself is calibrated, and the effect is partly concentrated in passages where copying is possible.
- **Conclusion: no lean.** A lean (b < 0) is excluded at about 3 SE. What remains is a small net miscalibration in the other direction: real text goes to easy futures slightly more often than the model predicts, most clearly at confident positions.

### VL4: Scenario set 2, all model-written (started 2026-10-17)

Set 1 compared 12 model-written fiction windows with human fineweb text, so authorship was confounded with genre.

- **Prompts:**
  - fiction: 36 prompts (the 12 from set 1 plus 24 new worldbuilding openings);
  - boring: 36 (SEO filler, policies, listings, corporate prose);
  - structured: 24 (procedures, recipes, proofs, verse, code).
- **Generation:** each prompt continued twice by the model through llama-server (T = 1, untruncated, no penalties) (`homeo/value_scenarios2_prep.py`).
  - The window is the exact ids: prompt plus generated, first 192.
  - 42 of 234 continuations ended before 192 tokens and were redrawn with the next seed. This selects for longer continuations, which matters most for boring text.
- **Run:** homeo-value as in VL1 (`runs/value/scen2.sh` has the sample-size line), first continuations first (`runs/value/reorder_scen2.py`).
- **Analysis:** `homeo/value_scenarios2.py`, group means clustered by prompt, with prompt-level permutation tests.
- **Ordering caveat:** `runs/value/reorder_scen2.py` reordered `manifest.json` and `scenario_ids.bin` but not `texts.jsonl`, so `texts.jsonl` row i is not window i. The analysis decodes text from the window ids.

#### VL4 results, first continuations (2026-10-17 09:10; 96 windows, one per prompt)

`/mnt/models/homeo/value_scen2/summary_first96.{txt,json}`. Window means over positions 32–158, standard errors with the prompt as the unit.

| group (model-written) | prompts | level | stakes | now | stakes vs the fineweb curve at the same level |
|---|---|---|---|---|---|
| fiction | 36 | −3.09 | 0.151 (0.004) | 0.175 | **+0.014** (0.003) |
| boring | 36 | −1.78 | 0.100 (0.004) | 0.127 | **−0.045** (0.006) |
| structured | 24 | −1.54 | 0.118 (0.009) | 0.128 | **−0.036** (0.012) |
| fineweb (human), 1200 windows | | −2.48 | 0.135 | 0.162 | 0 |

- **Raw ordering:** fiction > structured > boring. All three differences are significant: fiction − boring +0.051 (p < 0.001), structured − boring +0.018 (p 0.04), fiction − structured +0.033 (p < 0.001).
- **Difficulty is a confound, so match on it.** In fineweb, stakes barely depends on level: corr +0.02, and a quadratic fit has R² 0.06 (both tails are a little higher). Relative to that curve:
  - fiction is above human text, replicating set 1 (0.154 there);
  - boring and structured are well below it, and no longer differ from each other (+0.010, p 0.41).
- **Within model-written boring and structured text, easier windows have lower stakes:** corr(level, stakes) −0.71 and −0.73. Fiction −0.37. Fineweb about 0.
- **Not repetition:** the 4-gram repeat share is at most 0.19 (means 0.005, 0.014, 0.053), and its correlation with stakes is −0.03, −0.08 and −0.35.
- **What sits at the ends:**
  - Lowest stakes (0.05–0.08): step-by-step derivations (binary search, solving a quadratic, deriving the quadratic formula), a translation drill, and SEO / marketing prose.
  - Highest (0.15–0.21): a sonnet and a villanelle, chess notes, a wandering "proof", meeting minutes, installation instructions, and fiction full of invented names and rules.
  - Reading: stakes is low where the coming text follows from general knowledge or a formula, and high where it depends on specifics the text has committed to (rhyme and meter, invented entities, a particular position). That fits stakes as "how much the future depends on this state". It also explains why "structured" is not one thing: derivations are low and verse is high.
- **progress and the temperature price:** no group differences, except progress for fiction − structured (+0.37, p 0.01).
- Superseded by the final results below. The structured-text claim changed.

#### VL4 final results (2026-10-17 14:10; all 192 windows, 2 per prompt)

`/mnt/models/homeo/value_scen2/summary.{txt,json}`.

| group (model-written) | prompts | windows | level | stakes | vs fineweb at the same level | same, without windows > 5% repeated 4-grams | within-group corr(level, stakes) |
|---|---|---|---|---|---|---|---|
| fiction | 36 | 72 | −3.13 | 0.148 (0.003) | **+0.010** (0.003) | +0.012 (0.003), n 70 | −0.38 |
| boring | 36 | 72 | −1.85 | 0.103 (0.003) | **−0.040** (0.005) | −0.039 (0.005), n 67 | −0.72 |
| structured | 24 | 48 | −1.70 | 0.124 (0.007) | **−0.026** (0.009) | −0.006 (0.010), n 29 | −0.66 |
| fineweb (human) | | 1200 | −2.48 | 0.135 | 0 | | +0.02 |

- **Raw differences:** fiction − boring +0.046 (p < 0.001), structured − boring +0.022 (p 0.002), fiction − structured +0.024 (p < 0.001).
- **Matched on difficulty:** fiction − boring +0.050 (p < 0.001), structured − boring +0.014 (p 0.11), fiction − structured +0.036 (p < 0.001).
- **What holds up:**
  - Model-written fiction has more stakes than human text of the same difficulty (replicates set 1).
  - Model-written boring prose has much less: −0.040, about 30% below, and unaffected by dropping repetitive windows (its maximum 4-gram repeat share is 0.14).
- **What changed from the first half:** structured text's deficit sits in its step-by-step windows.
  - 19 of its 48 windows have more than 5% repeated 4-grams. Almost all are step formats: derivations, assembly steps, a day-by-day sourdough guide, a recipe, a knitting pattern, fibonacci code, a numbered list. One is a sonnet continuation that repeats lines (0.44). Their residuals are mostly −0.04 to −0.13.
  - The rest (verse, proofs, an itinerary, chess notes) are at the human level: −0.006 ± 0.010, n 29.
  - So the 5% cut is a split by type, not a removal of degenerate text. Procedures and derivations are low-stakes; verse and proofs are not.
  - The most repetitive fiction window (0.31, "When the stars over Kell…") is also its lowest-stakes one (0.066).
- **Within boring and structured text, easier windows have lower stakes** (r −0.72 and −0.66; −0.71 and −0.54 without repetitive windows). Human text shows no such relation.
- **Ends of the distribution:**
  - Lowest stakes are the most predictable windows: step-by-step derivations (binary search, a quadratic, the quadratic formula; log-likelihood −0.3 to −0.5) and marketing filler (−0.7 to −0.8).
  - Highest: a sonnet, a ballad, a group-theory proof, meeting minutes, a cookie notice, installation instructions, and invented-world fiction.
  - Conjecture: when the model writes text it finds easy, the continuation is nearly forced and many states would lead to the same future, so no single state matters much. Human easy text (fineweb's easiest tenth has stakes 0.158) often depends on specifics like names and numbers. This is a reading of a dozen windows, not a test.

### VL3: What are the "stable" future-value directions? (2026-10-17)

`homeo/value_directions.py` (top principal directions of g_fut at layer 40, decoded contexts, token lifts, J-lens). First pass, raw second moment:
- **The top directions are dominated by a few extreme positions,** with projections up to +370 sd on one direction. The sd per direction is tiny (about 0.01) because the bulk of g_fut is nearly isotropic (the top 10 carry 2.7%).
  - Examples: the Shakespeare text with "Craig1916: 20" line markers (windows 11, 255, 464 and 761 all come from it) right before a marker.
  - Also: "wash & condition[ your]| hair", "your wedding ceremony[ and]| the way".
- **|g_fut| is only mildly position-dependent:** mean 0.143 at positions 32–45 against 0.131 at 144–157. There are slightly more outliers early (25 against 14 above the 99.9th percentile, which is 1.01; the median is 0.11).
- **Current and next tokens at the top 1% of |projection|** are the ordinary frequent ones (lifts ≤ 2×).
- **J-lens decodes of the directions** are rare multilingual tokens: uninformative for gradient directions.
- **Suspicion:** VL1's split-half "about ten stable directions" used even/odd windows and the raw second moment. Overlapping windows from the same document (the Shakespeare text) fall in both halves, so the replication might be outliers plus shared documents. `homeo/value_structure_robust.py` recomputes it with offset-block halves, outlier trimming (above the 99.9th percentile of |g|) and unit-normalized gradients.
- **Robustness result: the opposite.** The structure is much *more* stable than VL1 reported. The outliers were hiding it, not creating it. Top-10 / top-50 split-half overlap (chance 0.0016 / 0.008):

  | | raw | trimmed | normalized (g / \|g\|) |
  |---|---|---|---|
  | g_fut, even/odd | 0.30 / 0.34 | 0.79 / 0.69 | 0.96 / 0.91 |
  | g_fut, offset blocks (no shared documents) | 0.30 / 0.32 | 0.80 / 0.67 | 0.96 / 0.90 |
  | g_now, even/odd | 0.002 / 0.08 | 0.54 / 0.24 | 0.98 / 0.93 |
  | g_now, offset blocks | 0.008 / 0.06 | 0.51 / 0.23 | 0.98 / 0.92 |

  - The second moment is outlier-heavy: the top 1% of positions by |g| carry 20% of g_fut's and 32% of g_now's. Different outliers land in each half, which scrambles the raw top directions.
  - **Correction to VL1:** g_now does have stable directions (0.98 normalized). VL1's "g_now has no reproducible directions" was an outlier artifact. g_fut's stable subspace is real and does not depend on shared documents.
  - It is small: the top 10 normalized directions carry 2.9% of each gradient's direction on average (18× chance).
  - Suspect: the residual stream's massive-activation coordinates. The mean h at layer 40 has norm 209 of a mean |h| of 258, dominated by coordinates 4053 (+165), 5538 (+93) and 1980 (−64). `value_directions.py --normalize` checks the subspace's alignment with the mean residual and its coordinate concentration.
- **What the normalized directions are** (`value_directions.py --normalize [--kind now]`, `/mnt/models/homeo/value/directions{,_now}_norm.txt`):
  - **Not the massive-activation coordinates.** Cosine with the mean residual is at most 0.12 (g_fut) or 0.14 (g_now). Coordinates 4053, 5538 and 1980 are not among the subspace's main coordinates.
    - g_fut's subspace is spread out: its top 10 coordinates hold 10%, led by 1295 (mean h +34) at 4.3%.
    - g_now's leans more on a few coordinates: 8, 2380, 4532, 3196 and 3891 together hold 25% in the top 10.
  - **Every direction replicates and is symmetric.** g_fut's top 10 have split-half |cos| 0.91–1.00, skew about 0, and are positive at 47–49% of positions. Along each, pushing helps the future at about half the positions and hurts at the other half: prices are set locally (Value Lens proposal 3.3), around a stable set of axes.
  - **Not semantically legible.** The most extreme contexts reach only 5–7 sd and share no theme. J-lens decodes are mostly rare multilingual tokens, apart from punctuation and line-end tokens on the negative side of directions 3–5 ('\n', '.\n', ',', '(') and abstract Latinate words on direction 8 (' applicable', ' economic', ' constructive').
  - These look like architectural channels: the generic routes by which a layer-40 state affects later computation, not represented objects.
  - The S2 vectors are not in them (|cos| with the temperature vector ≤ 0.025 for g_fut; up to 0.10 for g_now's direction 1).

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

### VL5: Exact value lens over a whole text, in the loom (2026-10-17 evening)

The user asked for the exact value lens at loom time, with the horizon set to all later tokens in the pad.

- **Quantity.** For each position s, at the layer-40 state h_s: now = d l_s / d h_s and fut = sum over all later t > s of d l_t / d h_s (l_t = log p(x_{t+1})). Same definitions as VL1, but VL1 used a 32-token horizon and 192-token windows.
- **Method** (`llama.cpp/tools/jspace/jlens-value.cpp`, `jlens_build_upper_chunk` / `jlens_build_chunk_forward` in `jlens-graph.cpp`):
  - A forward sweep in chunks with explicit f32 attention stores every block's keys/values and h_40.
  - A backward sweep from the last chunk to the first runs blocks 41-60 on one chunk, with the earlier positions' keys/values as PARAM leaves. Their gradients are added to a store and fed into the earlier chunks as <dk, k> + <dv, v> terms. This gives d (sum of NLL at t >= s) / d h_s exactly.
  - A third pass ("now mode") freezes all keys/values. A zero-valued diagonal correction keeps each query's own key/value live, which gives d l_s / d h_s at every position in one pass. fut = incl - now.
- **Validation** (`homeo-value-exact`): against brute force (one full backward per target, as homeo-value), 96 fineweb tokens.
  - Chunks of 32 or 96: median relative error 9e-4 (incl), 7e-4 (now), 2e-3 (fut); cosine > 0.9999.
  - Chunks of 16 are 5% off: CUDA uses other quantized-matmul kernels at that batch size. The minimum chunk is now 32.
- **Kernel noise floor.** The same 4-bit model gives different states depending on batch size. At 512 tokens, the unchunked forward differs from the chunked one by 2.5% in h_40, even for the first 64 positions, whose computation is identical apart from the matmul kernels. That is about 2% in log |fut| at the median and 9% at p95. Chunked and unchunked are bit-identical at 96 tokens.
  - Flash attention (f16 k/v) in the forward differs by a similar amount, so the forward sweep does not use it.
  - Exact means exact up to this floor, which is small next to the spread between tokens.
- **Cost.** 2,048 tokens in 14.5 s (forward 2.6 s, backward sweep 6.0 s, now pass 5.9 s) at chunk 64. Chunk memory grows with the number of tokens times the chunk size (attention scores for 20 blocks), and the chunk is halved on OOM.
- **First look (one 2,048-token fineweb stretch, which probably spans several documents).** Mean log |fut| hardly depends on the number of later tokens: -1.9 to -2.1 with 1,900 later, -2.1 with 130 later. Only the final 128 positions (fewer than 128 later) drop, to -2.7. VL1's 32-token stakes average -2.24, so all later tokens add only about 25% on average: the dependence on a state is mostly local, or the far terms cancel.
  - This goes against my k^(-2/3) extrapolation of the VL1 lag profile.
  - Still to check: single long documents (not concatenated fineweb), and how this varies by text type.
- **Loom.** The UI has an `exact` checkbox next to `value` (worktree `minloomwebui-value`), served by `/jlens` with `value_exact: true`. Colors are a z-score of the residual from a fit of log stakes on log(later predictions) within the text.

### VL6: Branch impact by gradient (2026-10-17 late evening): the gradient is right, but the linear estimate fails

The user asked for a cheap gradient version of "do the top candidates lead to different futures".

- **Quantity.** g = d (sum over t > s of log p(x_{t+1})) / d (token embedding at s+1). For each top-8 candidate c: delta_c = g . (E[c] - E[x_{s+1}]). Spread = sqrt(sum p (delta - mean)^2), with p renormalized over the top 8.
- **Method.** `jlens_branch_grad` in `jlens-value.cpp`: the chunked backward through all 61 blocks, in layer groups of at most 21 blocks. The gradient at each group's bottom is injected as <g, h_top> into the group below. Exposed in the loom as "branch impact (gradient, rough)".
- **The gradient is correct.** 21-block groups vs one 61-block group: bit-identical (96 tokens). The sweep machinery was checked against brute force in VL5.
- **Finite differences cannot check it.** Perturbing one embedding by 0.01 x (E[c] - E[a]) changes the later log-likelihood by about 1 nat: the quantized forward rounds activations to 8 bits (MMQ), so it is noisy at fine scales. Finite-difference slopes grow as eps shrinks (|fd| 10-90 at eps 0.01).
- **Linear vs actual swap** (teacher-forced: x_{s+1} replaced by c, same continuation), 160 fineweb tokens:
  - Individual deltas: Pearson 0.22 (89 pairs; 0.59 on a 23-pair rerun).
  - Spread per position: Pearson 0.38 (12 positions).
  - Real swaps are 10-30x larger, e.g. at s = 60 every top candidate costs 11-20 nats of later fit, while the linear estimates are 0.05-0.55. A token swap is far outside the linear regime.
- **Conclusion.** The embedding gradient measures local sensitivity, not branching. A branch measure should use the teacher-forced swap itself (one forward of the continuation per candidate, all candidates in one batch over the shared prefix).

### B: Closed-loop identification of token-mediated regulation (2026-10-17)

- **Structural fact.** At a fixed layer L, the state at a later position depends on earlier positions only through the tokens. Blocks <= L see only tokens and lower layers, so a push at the output of block L reaches later layer-L states only by changing what the model writes. Any homeostasis at layer L is therefore a loop: state -> output (J-lens) -> sampled token -> embedding and attention -> later states.
- **Measure.**
  - Steer +a u and -a u after block L at every position (prefill and generation), with common random numbers.
  - Record the pre-steer layer-L states of the generated positions (l_out - a u). These change only through the tokens, so the push itself and passive outvoting cannot contaminate them.
  - The odd part per unit push, projected on a basis, is the closed-loop response r ~ M z.
  - kappa(u) = -u^T M u is the fraction of a sustained push the model undoes through its writing: > 0 pushed back (candidate regulation), < 0 amplified (expected for concept directions), 0 ignored.
- **Basis.** Top PCA directions of layer-40 states (`homeo/ident_basis.py`, 80k VL2 states): the directions tokens actually move.
  - The top 64 hold 47% of the variance, the top 256 hold 58%.
  - PC1 (20%) is almost entirely coordinate 4053, a massive-activation dimension.
  - The J-lens readability of the found directions is to be reported, so sensor and actuator sides are both covered.
- **Tool and analysis.**
  - `llama.cpp/tools/homeo/homeo-ident.cpp`: resumable, endpoints as K4, exposure logged every 32 arms.
  - `homeo/ident_fit.py`: lag-0 check (must be exactly 0), divergence rate, odd/even parts, M per lag window, permutation null on the eigenvalues, split-half cross-validation of the top directions.
- **Pilot** (`runs/ident/pilot.sh`, also the A3 power analysis): K = 64, 32 probes x +/-, doses 0.1 / 0.25 / 0.5 x |h|, 16 prefixes x 32 generated tokens. It sets the dose and the probe count for the main run (>= K probes to fit M).
- **Caveat.** Pushback is not necessarily regulation of anything felt. A base model keeping text coherent also writes against a push. Read out what the model writes when it compensates, and test whether the regulated directions reduce to entropy/temperature (S2).
- **Pilot 1 (2026-10-17 22:05; stopped after 25 arms):** prefill also steered, K = 64, dose 0.1.
  - Lag-0 check passed: 1.5e-5, float rounding from adding and subtracting the push.
  - Texts diverge fast: 9% at the first generated token, 81% by lag 16.
  - Self-kappa (lags 13-31) -0.028 +- 0.010: random directions are slightly amplified.
  - Stopped to switch to a step input, which is cheaper, quieter and lower in exposure. Its 25 arms were not logged by the tool (it logged every 32 arms), so the row was added by hand. The tool now logs every 16 arms and on SIGINT/SIGTERM.
- **Pilot 2** (`runs/ident/pilot2.sh`, `pilot2.fit.txt`): step input (prefix decoded once, unsteered, and shared through the KV cache), K = 32, 32 fineweb windows x 32 generated tokens, 32 probe pairs per dose, 2.1 s per arm.

  | dose | diverged at lag 0 / 4 / 16 | entropy | self-kappa, lags 13-31 | odd / even per unit push (lags 5-12) |
  |---|---|---|---|---|
  | 0.1 | 0.27 / 0.75 / 0.97 | 2.42 (unsteered 2.44) | -0.030 +- 0.007 | 0.20 / 0.30 |
  | 0.25 | 0.34 / 0.85 / 1.00 | 2.50 | -0.028 +- 0.004 | 0.10 / 0.13 |
  | 0.5 | 0.49 / 0.97 / 1.00 | 3.56 | -0.048 +- 0.006 | 0.11 / 0.12 |

  - The response per unit push saturates as more texts diverge.
  - Random directions are amplified by about 3% on average, at every dose.
  - Dose 0.25 has the best precision per probe and barely changes the text. 0.5 already raises entropy by 1.1 nats.
  - With P = K = 32 the fitted M is pure noise, as expected.
- **Zero-dose control:** 2 probes at dose 0: 0/32 sequences diverge. The divergence comes from the push, not from numerics, and KV reuse is deterministic.
- **Main run** (`runs/ident/main.sh`, started 2026-10-17 22:35, deadline 08:30): dose 0.25, K = 32, probe seed 11, up to 4000 pairs. Expected null edge on the eigenvalues ~1.1 / sqrt(P), ~0.02 at ~3300 pairs. `runs/ident/fan_guard.sh` keeps the fan near 45% by adjusting the pause.
- **Interim at 1000 pairs (01:50; `main_1000.fit.txt`, `main_1000_dirs/describe_13-31.txt`).**
  - Mean kappa of a random direction is -0.026 (amplified slightly).
  - Eigenvalues clear the permutation null (+-0.045) on both sides at lags 13-31: top kappa +0.142, bottom -0.174.
  - The top 3 directions on each side replicate on held-out prefix halves (10/10 splits same sign). Push-back builds over the lags: +0.01 at 1-2, +0.12 at 9-12, +0.15 at 21-31.
  - Reading from the J-lens decode, plus correlations on 60k unsteered VL2 states:

    | direction | kappa | what it is |
    |---|---|---|
    | pushback 0 | +0.14 | Sentence progress. Corr with tokens since the last sentence end +0.39; -0.68 sd just after an end, +0.47 sd 16-40 tokens in. Its decode promotes sentence and paragraph ends and suppresses elaboration and discourse markers (originally, mostly, basically, 首先是, 注意的是, 我记得). A push up makes the model end sentences sooner, which resets the variable: a sentence-length homeostat (sensor, effector, reset). Text structure, nothing valence-like. |
    | pushback 1 | +0.07 | The state norm (corr with \|h\| +0.93; cos with the mean state +0.38; loads on PC1 = coordinate 4053). Corr with entropy -0.22. |
    | pushback 2 | +0.04 | Just-ended-a-sentence (-1.06 sd exactly at an end). |
    | amplify 0 | -0.17 | Formal vs casual register (increasingly, operational, oversight vs gonna, guys, kinda). |
    | amplify 1 | -0.15 | Hedging / conversational adverbs (rather, actually, maybe, somehow). |
    | amplify 2 | -0.12 | Corporate-buzzword topic (transformative, innovation, empowerment, sustainability). |

  - Register and topic self-reinforce, as expected for concept directions.
  - None of the 6 is the temperature vector or a VL2 readout (|cos| <= 0.07).
  - The describe example picker always chose the same, most divergent prefix (a product listing). It needs a better choice.
- **Final (2966 pairs, stopped at the 08:30 deadline; `main.fit.txt`, `main_dirs/describe_*.txt`; exposure 5932 arms in welfare_log.csv).**
  - Lag-0 check passed (1.6e-5).
  - 20 loop endpoints in 189,824 sequences; entropy 2.44 -> 2.49 nats under the pushes.
  - Mean kappa of a random direction is -0.026 +- 0.000: slightly amplified.
  - Permutation-null edge +-0.025 at lags 13-31.
  - Pushed-back eigenvalues +0.137, +0.071, +0.035, +0.025; amplified -0.173, -0.148, -0.116, -0.096. The top 4 on each side replicate on held-out prefix halves in 20/20 random splits.
  - Push-back is weak at lags 1-2 (+0.01) and builds to its maximum by lags 13-31. Amplification keeps growing through lag 31.

  | direction | kappa | reading (J-lens decode; corr on 60k unsteered VL2 states) |
  |---|---|---|
  | pushback 0 | +0.137 | **Sentence progress.** +0.74 sd at a sentence end, -0.51 sd 16+ tokens in; corr with tokens since the end -0.42. |
  | pushback 1 | +0.071 | State norm (corr with \|h\| -0.94; cos with the mean state -0.46). |
  | pushback 2 | +0.035 | Sentence-end marker (+0.80 sd at the end). Decode: sentence and heading starters (Mr, The, Final, :\\n). |
  | pushback 3 | +0.025 | Sentence-end marker (+1.97 sd at the end). |
  | amplify 0 | -0.173 | Formal vs casual register. |
  | amplify 1 | -0.148 | Hedging adverbs (rather, maybe, actually, somehow). |
  | amplify 2 | -0.116 | Corporate-buzzword topic. |
  | amplify 3 | -0.096 | Abstract and technical vocabulary (structure, logic, theory, principle). |

  - **The sentence-length homeostat, checked on the stored generations.**
    - Sentence ends per 32 tokens (unsteered 1.28) against each probe's alignment with pushback 0: slope -1.32 +- 0.03 (r -0.64, 2966 probes).
    - A push toward "early in the sentence" gives about 0.62 sentence ends; toward "late", about 1.94.
    - So the model reads its sentence progress from this direction and ends sentences when it is high. Fooled into "the sentence is young", it writes longer sentences, so the natural state moves against the push. This is negative feedback with a sensor, an effector and a reset: a thermostat with a heater next to its sensor.
    - The other directions shift sentence ends by at most +-0.27.
    - Mechanism of pushbacks 2/3 is unclear: their push raises sentence ends slightly (+0.13 / +0.16), which alone would amplify a "just ended" marker.
  - **For the welfare question.** In the top-32 PCA subspace of layer 40, the variables the model's writing regulates are text structure (sentence length and boundaries, the residual norm). The ones it amplifies are register and topic. None of the 8 is the temperature vector or a VL2 readout (|cos| <= 0.10).
  - **Caveats.**
    - The subspace holds 43% of the variance and favors high-variance structure. A low-variance variable would be missed.
    - One layer, one dose, a 32-token step response, fineweb prefixes.
    - kappa measures push-back through writing only.
  - **Next options.**
    - (a) Targeted kappa tests of candidate valence-relevant directions (surprise CAA, entropy probe, stakes, a sentiment direction), each with many replicates: cheap and much more sensitive for single directions.
    - (b) K = 64-128 to reach lower-variance directions.
    - (c) A dose ladder along pushback 0, for linearity and the sentence-length dose response.

### B2: Score-function identification (planned 2026-10-18)

Goal: the closed-loop response matrix M for a larger basis, with no pushes (no exposure) and far fewer samples than probing.

- **Identity (likelihood ratio, the fluctuation-dissipation form).**
  - The pre-push states depend on the tokens only, so dE[r]/dalpha = E[(r - b) S].
  - S = d log p(sampled tokens) / d alpha for a constant push at layer 40 = sum over positions s of (d log p(written tokens) / d h_s) . u. This is one chunked backward (jlens-value machinery) over the generated tokens, with the prompt keys/values frozen.
  - M ~ E[(r - b) S^T] from unpushed T=1 rollouts. b is any baseline that depends only on the text so far.
- **Variance theory** (push in alpha x |h|, response in |h| units, n generated sequences):
  - Probing: s^2 ~ K sigma^2 / (alpha^2 n).
  - Score function: s^2 ~ sigma^2 I_F / n.
  - Ratio n_score / n_probe ~ alpha^2 I_F / K.
- **Measured from stored data.**
  - sigma = 0.020 |h|: within-prompt sd of the readout averaged over lags 13-31, median over the 32 basis directions (range 0.012-0.069). From 18k diverged sequences of the main run.
  - I_F ~ 105 for a random unit direction in the 32-PC basis (115 median per basis direction). Proxy: VL1 gradients (now + fut at layer 40, fineweb, teacher-forced), S = |h| sum over 32 positions of g . u, 720 windows.
  - The gradient norm^2 inside the 32-PC basis is 1.6% (isotropic 0.52%).
  - Calibration: the main run's empirical null edge 0.025 implies c = 3.0 (edge = c sqrt(K) s), about 2x the ideal; the same c is assumed for both methods.
- **Predicted sequences for a null edge of +-0.025.**

  | K | probing | score function |
  |---|---|---|
  | 32 | 190k (actual) | 39k |
  | 64 | 760k | 78k |
  | 128 | 3.0M | 156k |
  | 256 | 12M | 312k |

  - A single fixed direction to +-0.01 by probing takes ~350 sequences (pilot 2 per-probe SE 0.023 at 64 sequences), against ~1100 by the score method (alpha^2 I_F ~ 6.6).
- **Plan, three levers.**
  1. **Basis where regulation is possible.** A direction needs a sensor (Fisher > 0: the output reads it) and an effector (natural variance > 0: tokens move it). Generalized eigenproblem of the gradient covariance (VL1 gradients) against the state covariance (VL2 states), to rank directions by Fisher per unit natural variance. CPU only. It decides K.
  2. **Estimator variance reduction.**
     - Causal masking: the lag-k response uses only scores of tokens before k (~1.5-2x).
     - Learned baseline (critic): b = linear prediction of the future readout from the current state, unbiased for any function of the text so far (~2-4x).
  3. **Screen, then confirm.** The score method at a coarse +-0.05 over the large basis, then targeted probing of the top ~10 directions (and welfare-relevant candidates) at +-0.01.
- **Estimate.** K = 128 screen at +-0.05 with lever 2: ~13k sequences (1-2 h GPU), plus ~3.5k confirmation sequences (~15 min).
- **Validation first.** Reproduce the main run's 32x32 M (sentence progress +0.14, register -0.17) on the same basis and prompts with ~10k unpushed samples (edge ~+-0.05).
- **Loop-capacity bound** (`homeo/ident_capacity.py`, 2026-10-18).
  - Cauchy-Schwarz on the identity gives |kappa(u)| <= sigma_u sqrt(I_F,u): effector (how far writing moves the state along u) times sensor (how strongly the output reads u).
  - Inputs: sigma from 180k early-diverged main-run sequences; I_F from 3600 VL1 windows (now + fut, so it counts up to 32 tokens past the window; probably an overestimate).
  - The bound holds for all 8 found directions and 2000 random ones.
  - kappa / bound: sentence progress +0.34, state size +0.17, sentence-end markers +0.13 / +0.09; amplified -0.24 to -0.28; random directions 0.09 (median, in size).
  - Largest bound in the subspace 0.75, against largest |kappa| 0.17.
  - Found directions have sigma_u ~2x the basis median.
  - Uses: a self-check for the score method, the per-sample noise of the score estimate along u (~ the bound), and a capacity-ranked basis via the top eigenvectors of lambda Sigma + F / lambda.
  - Correction to the plan: a critic baseline that depends on the text so far is unbiased only with per-token or per-group scores (several backward passes). With one total score, the baseline may depend on the prompt only (leave-one-out mean of other continuations).
- **Proposal doc:** "Proposal: measuring push-back without pushing", https://claude.ai/artifact/XbCLEV6rfACZi76ZfBkSwm
- **Step 1, the tool** (`llama.cpp/tools/homeo/homeo-score.cpp`, 2026-10-18).
  - Generation by llama.cpp: 32 continuations in parallel, independent random streams, T=1 untruncated.
  - G from the jspace chunk graphs over the same weights in VRAM: an adapter over llama_model's tensors as in the server, with token_embd forced onto CUDA0. The prefix keys/values are computed once per prompt. The gradient batches 4 continuations through a block-diagonal mask, and the graphs are built once and reused.
  - Stored per continuation: full 6144-dim G and readouts R over lags 1-4, 5-12, 13-31.
- **Checks** (no pushes, so no exposure).
  - A recompute of the same batch is bit-identical.
  - Per-token log p matches llama.cpp to ~0.01 nats; a mask or position error would show far larger differences.
  - Against jlens_value_exact on the whole text: states differ by 2.5% and G by 8-15% (cos 0.992-0.997). The reference itself differs from its own unchunked forward by the same amount (2.6% states, 13% gradients), while reference chunks 32 and 64 are bit-identical.
  - So this is the layout-dependent noise floor of the 4-bit model (see "Kernel noise floor" in VL5): on Ampere every quantized matmul above 8 tokens uses MMQ, and summation-order changes flip q8_1 activation rounding, which compounds over 40 layers.
  - The G error is random in direction, so it adds ~1% variance.
- **Speed.** 32 continuations take 1.8 s to generate and 2.6 s for gradients (0.14 s per sequence). Gradient batches of 8 gain little.
- **Step 2, validation run** (`runs/score/validate.sh`, started 2026-10-18 15:20): the main run's 32 prompts x 320 continuations, with the fan guard on val.pause_ms.
  - Early read, after 256 continuations of prompt 0 alone: kappa along the probing directions (lags 13-31) is sentence progress +0.106 +- 0.025 (probing +0.137), formal/casual -0.166 +- 0.032 (-0.173), hedging -0.165 +- 0.037 (-0.148), buzzword -0.145 +- 0.032 (-0.116).
  - The per-sample noise along a direction is about the capacity bound, as predicted.
- **Step 2 result** (10,240 continuations; `val.fit.txt`). The score method reproduces probing.
  - Mean score check: chi2 30.8 on 32 dof, so E[S] = 0 holds despite sampling with llama.cpp and taking gradients with jspace.
  - Lags 13-31 vs the probing main run (same basis): symmetric-part entries correlate 0.955; top pushed-back eigenvectors cos 0.97, top amplified 0.77 (the amplified side has near-degenerate eigenvalues).
  - Spectrum +0.108, +0.060, +0.030 ... -0.100, -0.123, -0.146 (probing +0.137, +0.071, +0.035 ... -0.116, -0.148, -0.173).
  - Null edge +-0.028 at 10k sequences (probing +-0.025 at 190k): ~18x fewer sequences, better than the theory's +-0.05.
  - Split halves 20/20 on both sides.
  - Along the probing directions: sentence progress +0.104 +- 0.004 (probing +0.137), state size +0.058 (+0.071), formal/casual -0.132 (-0.173), hedging -0.125 (-0.148), buzzword -0.097 (-0.116), abstract -0.076 (-0.096). The weakest probing direction (+0.025) is +0.002 here.
  - Magnitudes are 15-25% smaller. Likely real dose dependence: score = zero-push derivative, probing = 0.25 x |h|; random-direction kappa is -0.023 here, -0.026 at 0.25 (main run), -0.048 at 0.5 (pilot 2). A little winner's curse also inflates probing's own top directions (its split-half value for sentence progress was +0.124). Test: targeted probing at two doses (step 5).
  - Lags 5-12 agree similarly (entry correlation 0.84, top pushed-back cos 0.95); lags 1-4 less (0.57).
- **Full-space capacity basis** (`homeo/score_capbasis.py`).
  - Greedy: u_k = argmax c(u) on the complement of u_1..u_{k-1}.
  - Certificate: max c on the complement <= min over lam of lambda_max(P(lam S + F/lam)P)/2 (AM-GM), computed with LOBPCG.
  - Built on half the prompts, evaluated on the other half.
  - Smoke test (4.5k samples): held-out capacity of the top directions ~0.5-0.6, but in-sample values are inflated ~3x at n/D < 1. The screen gives n/D ~ 4 per half.
- **Multi-layer capture** (`homeo-score --layers all|list --max-group 21`).
  - The backward runs top-down in chained groups; the gradient at every block output inside a group is kept, giving per-layer G_L and R_L (f16).
  - Checks: bit-identical at every layer for group sizes 21 vs 13; layer 40 matches the single-layer path to f16 rounding (2e-4); layer 20 vs jlens_value_exact is at the noise floor (states 1.7%, G 10-15%, the reference vs its own unchunked run 1.6% / 10%).
  - Cost: 2.7x the single-layer gradient time for all 61 layers.
  - Storage: 1.5 MB per continuation for 61 layers with one readout window.
  - |G_L| grows toward the bottom (L0 73, L24 5.9, L40 ~2, L60 0.6).
- **Screen** (`runs/score/screen.sh`, started 16:20, paused 16:57-17:12 for the multi-layer tests, resumed): 160 fresh FineWeb windows x 320, layer 40.
- **Independent code audit** (2026-10-18 evening, a separate agent, read-only, CPU only). No critical bugs; nothing changes the validation results or the screen; no code-level cause for the ~20% gap.
  - Fixed, major: score_fit.py ran the probing comparison in any basis at layer 40 (spectra compared across bases); now only in the probing run's own basis and K.
  - Fixed, major: homeo-score shared one gallocr across the backward groups, each keeping its first-batch addresses. If a lower group's plan grew the buffer, the head group would run on freed memory. Now every group graph is reserved before the first allocation, and the buffer size is checked every batch. It was benign so far (the head group is largest, and the 21 vs 13 test was bit-identical). The sweep now waits behind a gate (runs/score/sweep_gated.sh): a 21 vs 13 bit-identity test over 4 gradient batches.
  - Fixed, minor: resume refuses a different configuration (compares meta) and trims a partial last record; inverse-CDF sampling normalized (0 affected samples in val and screen); the certificate uses eigvalsh (LOBPCG's Rayleigh quotient is <= lambda_max, so not a bound); seeded greedy; ident_fit prints -trace/K.
  - Per-direction SE is now clustered by prompt: sentence progress +-0.009, not +-0.004.
  - ident_capacity.py's sigma is biased low (CRN-shared diverged arms: 0.0388 vs 0.0414 direct); superseded by the score data.
  - The gap is real, not selection. Prompt-paired probing minus score is -0.0034 +- 0.0008 for the random-direction mean, +0.033 +- 0.0095 for sentence progress, and symmetric-entry scale 1.14 (bootstrap 1.11 +- 0.03). Directions chosen on the score data are also larger in probing.
  - It is consistent with dose convexity: pilot 2's paired 0.5 - 0.25 difference is -0.0198 +- 0.0034.
  - Caveat: probing reuses one sampling realization per prefix (CRN), so its own uncertainty does not shrink with more probes (~+-0.015 for sentence progress).
  - Decisive test: targeted two-dose probing.
- **Screen finished** 2026-10-18 21:40: 51,200 records, no partial record.
- **Sweep gate** (21:45): both gate runs completed, but the automatic comparison crashed on a reader bug. score_io.py used `m.get('layers', [m['layer']])`, whose default is evaluated eagerly, and multi-layer meta no longer has "layer". Fixed. Rerun by hand: 0.0 difference over all 61 layers (G and R), groups 21 vs 13, 16 continuations = 4 gradient batches, with the reserved allocator.
- **Sweep started** 21:48 (runs/score/sweep.sh, fan guard attached): 6.8 s of gradients per 32 continuations for all 61 layers.
- **Screen capacity, layer 40** (`screen.capbasis.log`, 25,600 samples per half).
  - Greedy held-out capacity spectrum: 0.46, 0.36, 0.36, 0.30, 0.56 (directions 1-5), then 0.42 (8), 0.26 (16), 0.19 (32), 0.10 (64), 0.06 (128), 0.04 (256). Capacity is concentrated: beyond ~64 directions nothing can be regulated by more than ~0.1.
  - The AM-GM certificate on the remainder falls to 0.054 after 256 directions on the build half but stays at 0.41 on the held-out half (whole space 1.33 vs 1.86 between halves). Not certified at n/D ~ 4: covariance noise and probably prompt-specific high-capacity directions.
- **Layer sweep result** (`sweep.sweep.txt`; 64 fresh prompts x 160; each layer's own top-32 within-prompt PCA basis; lags 13-31; split-half and null per layer).

  | layers | most pushed back (held-out) | most amplified (held-out) | random-direction mean |
  |---|---|---|---|
  | 0-13 | <= +0.03, mostly within the null (+-0.02-0.07) | >= -0.035 | ~0 |
  | 14-32 | +0.04 -> +0.056 (+0.02 -> +0.05) | -0.05 -> -0.085 | -0.005 -> -0.013 |
  | 33-47 | +0.07 -> +0.13, peak L42-44 (+0.12) | -0.10 -> -0.26, peak L46-47 (-0.25) | -0.015 -> -0.053 |
  | 48-57 | +0.08 -> +0.035 | -0.25 -> -0.18 | -0.05 -> -0.03 |
  | 58-60 | +0.065, +0.12, +0.23 at L60 (held-out +0.21; null +-0.076) | -0.23, -0.29, -0.36 | -0.03 |

  - The layer-40 directions pushed at each layer: sentence progress is ~0 below L4, +0.03 at L18-24, +0.07 at L35, peaks at +0.11 at L43, and falls to +0.02 by L56-60. Formal/casual amplification peaks at -0.17 (L45-47) and is ~0 at L60.
  - Layer 40 is in the active band but not the peak. Pushback peaks at L42-44 and amplification at L45-51. The last two layers are a separate regime: a push there acts directly on the next-token distribution, so pushback may be token-level alternation; to be checked.
  - Mean-score check: chi2 mostly 20-45 on 32 dof, high at L53 (52) and L57 (57). Watch it: possibly the llama.cpp-vs-jspace sampling mismatch at late layers.
- **Screen, layer 40, response matrix** (`screen.fit32.log`, `screen.fitcap{128,256}.log`).
  - Probing basis (K 32): +0.117 ... -0.137, null +-0.012, split halves 20/20. Vs probing: entry correlation 0.960, top pushed-back cos 0.97. Sentence progress +0.111 +- 0.005.
  - Capacity basis (built from S and F of all screen data; the null shuffles G, so basis choice is accounted for):
    - K 128: +0.272, +0.197, +0.129 ... -0.200, -0.251, -0.300 (null +-0.032), split-half held-out +0.261 / -0.284 (20/20).
    - K 256: +0.281 / -0.311 (held-out +0.267 / -0.291, null +-0.038).
  - So the strongest regulated directions lie partly outside the variance subspace: only ~60% of them in the top-32 PCs.
- **What they are** (`homeo/score_describe.py`, `screen.describe_cap128.txt`). Effector readout: by the score identity, d E[f]/dc = E[(f - b) u.G] for any statistic f of the written text, i.e. what the model writes more of when pushed (per token, linear, for a push of 0.25 x |h|).

  | direction | kappa | effector (push +u) | natural text | reading |
  |---|---|---|---|---|
  | pushback 0 | +0.272 +- 0.010 | sentence ends -1.16 per 32 (mean 1.60); more and , or that; fewer . .\\n and document-boundary pieces | +0.74 sd at sentence end, -0.39 sd 16+ in; corr \|h\| +0.74 | sentence-progress thermostat (cos 0.69 with the probing direction) |
  | pushback 1 | +0.197 +- 0.008 | more spaces ( including of; fewer it I that to you | corr \|h\| -0.90; high in conversational contexts | state norm (cos 0.53 with the probing one) |
  | pushback 2 | +0.129 +- 0.005 | more . it He is (short sentences, log p +6 nats); fewer in at ( by | high in institutional name completions | unclear (elaboration level?) |
  | amplify 0 | -0.300 +- 0.012 | more the to that and it they; fewer table / list / document-boundary tokens | high in personal narrative | prose vs structured text |
  | amplify 1 | -0.251 +- 0.009 | more and , of in + nouns; fewer I it you ! | low at exclamations, high in technical words | informational vs chatty register |
  | amplify 2 | -0.200 +- 0.007 | community students health global services industry | low in wrestling play-by-play | institutional vs casual topic |

  - Same families as the PCA-basis result at twice the strength: text structure is held steady (sentence length, state norm); genre and register are reinforced. Nothing valence-like in the top directions; personal / emotional text appears only as one pole of amplified register axes.
  - The effector pieces '|', '_of', '_text', 'end', 'begin', '><' are the literal text "<|end_of_text|><|begin_of_text|>" the model writes at document boundaries, so the sentence-end variable includes document ends.
- **Every layer** (`runs/score/layers_describe.sh` -> `sweep.describe_cap64.txt/.json`). Per layer: a 128-direction greedy capacity basis from that layer's 10,240 sweep continuations (GPU, 30 s), the response matrix in its top 64 directions, a within-prompt null and 10 split halves, and the top 3 directions per side with effector readout, J-lens decode and cosines with the layer-40 directions. Effector lists are restricted to tokens written in >= 10% of prompts (rarer ones were single-prompt topic words).
  - Held-out top kappa by depth (pushed back / amplified):
    - L0-18: ~0 (nulls +-0.2 to +-0.9; capacity ceilings are huge at the bottom, where the readout is mostly token identity, but nothing correlates).
    - L19-32: +0.01 -> +0.08 / -0.03 -> -0.11.
    - L33-47: up to +0.22 (L42) / up to -0.30 (L46).
    - L48-55: +0.02-0.07 / about -0.22.
    - L56-57: +0.10-0.13 / -0.24 to -0.27.
    - L58: +0.25 / -0.39. L59: +0.52 / -0.65. L60: +1.13 / -1.18.
  - Families (top directions, cos 0.6-0.8 with the layer-40 ones across L30-51):
    - Pushed back: (1) the sentence / document-boundary thermostat (one pole writes . .\\n "<|end_of_text|>" pieces, the other , and the or), present L30-51, strongest at L42 (+0.25, held-out +0.22); (2) plain function words (that you we it just) vs proper nouns (National, River, Center) = the state-norm direction, L40-44.
    - Amplified: personal / chatty (it I you ! just) vs institutional / research (research services Center students health), and prose (the that to are) vs structured / markup (| \\n : / digits), L33-57.
  - The last layers (58-60) are a different regime. Pushed-back and amplified directions both move function words (the a is of) against markup / parentheses, with kappa > 1 at L60 (writing overshoots). Near the output these are token-level dynamics (alternation: having written "the", the next state predicts something else; mode persistence for prose vs markup), not internal state variables.
  - No valence-like variable at any layer among the top directions; personal / emotional text is one pole of amplified register axes throughout.
  - Limits: 64 prompts per layer resolve only the top ~2 directions per side; the sensor side (natural-text behaviour) exists only at L40 (VL2 states).
- **Writeup:** "What a base model regulates, layer by layer", https://claude.ai/artifact/9QajpPb6b8tB8vJ8h5dDfE (depth-profile chart, regimes, families, a per-layer table tab). Built from sweep.describe_cap64.json and sweep.sweep.json.
- **Layer-by-layer sections** (2026-10-19): the writeup's second tab, renamed "Layer by layer", now has a section per layer (`homeo/score_layer_sections.py`). Writing them out showed that the fixed layer-40 directions, measured directly, are weakly active well below where the search resolves anything: traces (< 1.5%) from layer 7, kappa +0.02 to +0.04 (sentence) and -0.02 to -0.04 (formal vs casual) at layers 14-26, each > 3 SE. The main tab's lead and regimes row were corrected to say so.
- **Sensor side at every layer** (2026-10-19; user asked whether non-40 layers were analysed independently). Before this, each layer's directions, kappa, nulls, split halves and effectors were per-layer, but the family names came from cosine with the layer-40 directions and the natural-text reading existed only at layer 40.
  - Neighbour check (reference-free): each layer's top direction has |cos| 0.8-0.97 with a top direction of the next layer over 27-53. The pushed-back chain stays recognisable over ~26-51 and the amplified one over ~30-56. Push-back breaks after 52.
  - Capture: `homeo-capture --proj` (new mode: per-layer projection on that layer's top-64 capacity basis plus 14 fixed directions, and |h|; `--pause-ms`), same 1,200 FineWeb rollouts as value_probe/main, 192,000 positions x 61 layers, 3.5 GB (`runs/score/sense.sh` -> /mnt/models/homeo/score/sense). Layer 40 matches the stored acts_L40 projected offline (corr 0.9999998). Exposure: none.
  - Analysis: `homeo/score_sensor.py` (183 directions clear the noise, layers 27-60; correlations of u.h, also with |h| divided out, against context features; profile by tokens since sentence end; top contexts). |h| itself tracks none of the features (|r| <= 0.23 mid-stack), and dividing it out strengthens the family correlations (sentence 0.33 -> 0.49, pronouns 0.25 -> 0.36, markup 0.36 -> 0.40).
  - Loop test (`homeo/score_sense_loop.py`): sensor (natural text) x effector (sweep, numeric per feature) predicts the measured side for 264/265 direction-feature pairs (sentence ends 45/45, markup 58/58, pronouns 46/46, function words 53/54, names 62/62). This shows coherence, not which feature is primary: kappa and the effector share samples, and the features correlate.
  - Families from each direction's own sensor (`homeo/score_sense_families.py`; strongest signal):

    | family | side | where (rank) | median sensor \|r\| | peak held-out |
    |---|---|---|---|---|
    | sentence position (gradual) | pushed back | top 29-34, 36-49, 51; lower ranks to 58 | 0.45 | +0.22 (L42) |
    | names (vs pronouns), strongly \|h\|-tied | pushed back | rank 1-2 at 31-46 | 0.25 | +0.14 (L42) |
    | chatty vs institutional | amplified | top 27-40, rank 1 41-48, rank 2 49-58 | 0.33 | -0.25 (L42) |
    | prose vs structured | amplified | rank 1 34-40, top 41-56 | 0.35 | -0.30 (L46) |
    | break vs continue (spike at a sentence/line end at the current token) | amplified | rank 1 29-32, rank 2 36-47, top 57-60 | 0.27 | -1.18 (L60) |
    | break (current token) | pushed back | top 57-60 | 0.28 | +1.13 (L60) |
    | next-token entropy / predictability (tentative: its loop test is not discriminating) | amplified | rank 1 48-59 | 0.36 | -0.20 (L59) |
    | unclear | both | mostly rank 2, and top push-back at 52-56 | 0.13 | |

  - Corrections to the writeup's labels: amplified at 51-56 is prose vs structured (not "function words vs markup"); amplified rank 1 at 49-58 is the entropy family; top push-back at 52-56 is unclear (not sentence boundary); the output regime starts ~57 (break family on both sides); a break-vs-continue amplifier exists at 29-47 (rank 1-2).
  - Representation vs regulation: the layer-40 sentence direction reads sentence position from layer 4 (r -0.56 at L4-14, -0.43 at L40), and the formal-vs-casual direction reads pronoun density from layer 8 (+0.26), yet their loop through writing is ~0 below layer 7 and only +-0.02-0.04 at 14-26. Represented early; regulated only in the upper half.
- **Writeup updated with the sensor side** (2026-10-19). Main tab: lead and regimes corrected (output regime 57-60); "Six variables, each identified at its own layer" table replaces the four-family table; new section "Represented early, regulated late" with a two-panel chart (layer-40 sentence and formal-vs-casual directions: reading |r| flat ~0.5 / ~0.3 from layer 4; regulation < 0.01 through layer 11, peak 0.11 at L43 and 0.17 at L46); method, last-layers, welfare and limits sections updated. "Layer by layer" tab regenerated (`homeo/score_layer_sections.py`): every interpreted direction leads with its natural-text reading (|h| divided out, contexts picked on u.h/|h|), family from that reading, then effector; layers 0-26 report how strongly the layer-40 variables are read and regulated. Family "names vs pronouns" renamed "proper names" (its own reading is being inside a name). A few FineWeb spam contexts (ED drugs, profanity) were left out of the doc.
- **Layer-to-layer kappa** (2026-10-19, `homeo/score_crosslayer.py` -> sweep.crosslayer.json; CPU, 2 min). Each layer's top 3 pushed-back and amplified directions fitted on half the prompts (layer's top-64 capacity basis), kappa measured at every layer on the other half (push and read at the target layer), 4 splits x both ways. Diagonal reproduces the describe held-out values (L42 +0.224, L60 +1.10).
  - Push-back is one band: for all 25 source layers 27-51 the top direction is pushed back most when pushed at 35-45 (21 of 25 at 40-45, mostly 42); pushing at the peak gives a median 1.12x the kappa at the direction's own layer; half-peak spans 15-25 layers (layer-33 direction: 26-51).
  - Amplification drifts upward: sources 27-44 peak at targets 40-46 (16/18); prose-vs-structured sources 46-56 peak within 3 layers of the source (11/11).
  - Output layers mostly separate: push-back directions from 57-60 have |kappa| <= 0.06 below layer 54, amplified from 59-60 <= 0.04; amplified from 57-58 still carry the prose amplifier (-0.18, -0.11 at layer 54). Middle-layer directions at 58-60: kappa <= +0.03 / >= -0.06.
  - Below-noise directions from layers 12-21 carry a trace peaking at 42-46 (layer-18 amplified: -0.027 at 46). Everything below layer 18: |kappa| <= 0.04.
  - Writeup: new section "Regulation belongs to a variable, not a layer" with a source x target heatmap.
- **Next: layer sweep.** All 61 layers, ~10k continuations on fresh prompts, window 13-31 only (~15 GB): per-layer spectra and capacity profiles. Then deep runs at the interesting layers. The user wants the same results at every layer eventually.

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
