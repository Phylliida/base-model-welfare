export const meta = {
  name: 'autointerp-directions',
  description: 'Explain 36 regulated directions of a base model from activation windows and steering examples, then score explainer and baseline descriptions with blind judges',
  phases: [
    { title: 'Explain', detail: '4 explainers x 9 directions; the 2 baseline judges start at once' },
    { title: 'Judge', detail: '2 judges score the explainer descriptions on held-out items' },
  ],
}

const DIR = args.dir
const N_DET = 12, N_INT = 12

const EXPL = { type: 'object', properties: { directions: { type: 'array', items: { type: 'object', properties: {
  id: { type: 'string' }, label: { type: 'string' }, reads_high: { type: 'string' }, reads_low: { type: 'string' },
  push_toward_high: { type: 'string' }, push_toward_low: { type: 'string' }, reading_vs_writing: { type: 'string' },
  confidence: { type: 'integer', minimum: 1, maximum: 5 } },
  required: ['id', 'label', 'reads_high', 'reads_low', 'push_toward_high', 'push_toward_low', 'reading_vs_writing', 'confidence'] } } },
  required: ['directions'] }

const JUDGE = { type: 'object', properties: { results: { type: 'array', items: { type: 'object', properties: {
  id: { type: 'string' },
  detect: { type: 'array', items: { type: 'string', enum: ['A', 'B'] }, minItems: N_DET, maxItems: N_DET },
  intervene: { type: 'array', items: { type: 'string', enum: ['A', 'B'] }, minItems: N_INT, maxItems: N_INT } },
  required: ['id', 'detect', 'intervene'] } } }, required: ['results'] }

const explainPrompt = (batch, k) => `You are interpreting directions in the hidden state of a pretrained (not instruction-tuned) language model.

Read the file ${DIR}/explain_${k}.md. It contains evidence for directions ${batch.join(', ')}: activation windows (each token annotated with the direction's value) and steering examples (continuations written with the hidden state pushed toward HIGH or LOW values of the direction, next to an unpushed continuation with the same random numbers). Use only that file: do not open any other file, search the filesystem, or run code.

For each direction, write a description that someone who never sees this evidence could use to:
1. tell which of two text contexts has the HIGHER value of the direction at a marked token, and
2. tell which of two continuations of a prefix was written with the state pushed toward HIGH rather than toward LOW.

So be concrete and discriminative. Name the observable features of the context that make values high or low (position in the sentence or line, punctuation, register, formatting, kinds of tokens, topic, and so on), and the observable changes a push causes in the writing (sentence length, line breaks, punctuation, pronouns, vocabulary, topic, coherence, ending the document, and so on). Report what the evidence shows rather than a tidy single concept: if a direction mixes several things, or if what it reads differs from what pushing it writes, say so. Some directions may be subtle or noisy; say that too, and still give your best discriminative description.

Fields per direction (one to three sentences each unless noted):
- id: as in the file (e.g. D07)
- label: at most six words
- reads_high: contexts and tokens where the value is high
- reads_low: where it is low
- push_toward_high: how the writing differs from the unpushed continuation when pushed toward HIGH
- push_toward_low: the same for LOW
- reading_vs_writing: one sentence on whether the reading side and the writing side are the same thing
- confidence: 1 (guess) to 5 (clear)

Return all ${batch.length} directions.`

const descBlock = (id, d) => `### ${id}\nLabel: ${d.label}\nHigh values: ${d.reads_high}\nLow values: ${d.reads_low}\nPushed toward HIGH, the model writes: ${d.push_toward_high}\nPushed toward LOW, the model writes: ${d.push_toward_low}\nItems to answer: ${N_DET} detection pairs, ${N_INT} intervention pairs`

const judgePrompt = (ids, h, descText) => `You are scoring descriptions of directions in a pretrained language model's hidden state. Each description says where the direction's value is high or low, and how the model's writing changes when its state is pushed toward high or low values.

${descText}

Then read the file ${DIR}/judge_items_${h}.md, which holds the test items. Use only the descriptions and that file: do not open any other file, search the filesystem, or run code.

For each of these directions: ${ids.join(', ')}. Answer every detection pair (which context, A or B, has the HIGHER value at its «marked» token) and every intervention pair (which continuation, A or B, was pushed toward HIGH), in the order given, using only that direction's description. Every item has a correct answer; if you are unsure, make your best guess rather than skipping. Return one result per direction, with exactly ${N_DET} detection answers and ${N_INT} intervention answers. Ignore directions in the file that are not listed here.`

phase('Explain')
const baseJudges = args.judge_halves.map((half, h) =>
  agent(judgePrompt(half, h, `The descriptions are in the file ${DIR}/baseline_desc_${h}.md; read it first.`),
    { label: `judge baseline ${h}`, phase: 'Explain', schema: JUDGE }))

const expl = await parallel(args.explain_batches.map((b, k) => () =>
  agent(explainPrompt(b, k), { label: `explain ${k}`, phase: 'Explain', schema: EXPL })))
const auto = {}
for (const r of expl.filter(Boolean)) for (const d of r.directions) auto[d.id] = d
const all = args.judge_halves.flat()
const missing = all.filter(id => !auto[id])
if (missing.length) log(`no explainer description for ${missing.join(' ')}`)
log(`${Object.keys(auto).length} of ${all.length} directions described`)

phase('Judge')
const autoJudges = args.judge_halves.map((half, h) => {
  const ids = half.filter(id => auto[id])
  return agent(judgePrompt(ids, h, 'Descriptions:\n\n' + ids.map(id => descBlock(id, auto[id])).join('\n\n')),
    { label: `judge explainer ${h}`, phase: 'Judge', schema: JUDGE })
})

const merge = rs => {
  const o = {}
  for (const r of rs.filter(Boolean)) for (const x of r.results) o[x.id] = { detect: x.detect, intervene: x.intervene }
  return o
}
const bj = await Promise.all(baseJudges)
const aj = await Promise.all(autoJudges)
return { explanations: auto, judgments: { auto: merge(aj), baseline: merge(bj) } }
