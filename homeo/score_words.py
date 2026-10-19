"""Shared wording for the layer-sweep directions: family names, the reading sentence, token lists and contexts.

Used by score_layer_sections.py (the writeup's layer sections) and score_probe_export.py (the loom's direction probes),
so both describe a direction the same way.
"""
import json
import sys

import torch  # noqa: F401  (before numpy: this venv's numpy needs torch's libz)
import numpy as np

O = '/mnt/models/homeo/score'
MODEL = '/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf'

DOC = {'|', '_of', '_text', 'end', 'begin', '><', '<', '>', '<|endoftext|>'}
NSFW = ('sex', 'porn', 'escort', 'nude', 'fuck', 'viagra', 'casino', 'xxx', 'dating', 'cock', 'pussy', 'slut', 'erotic', 'naked')
FNAME = {'sentence': 'sentence position', 'name': 'proper names', 'chatty': 'chatty vs institutional',
         'prose/struct': 'prose vs structured text', 'break': 'break vs continue', 'entropy': 'predictability', 'unclear': 'unidentified'}
PHRASE = {'since_end': ('deep into sentences', 'near sentence ends'), 'at_end': ('at sentence or line ends', 'mid-clause'),
          'markup16': ('in structured text (newlines, digits, symbols)', 'in running prose'),
          'pron32': ('in chatty first- and second-person text', 'in impersonal text'),
          'func16': ('where function words are dense', 'where function words are sparse'),
          'name': ('inside names', 'away from names'), 'entropy': ('where the next token is uncertain', 'where the next token is predictable'),
          'surprisal': ('right after surprising tokens', 'right after expected tokens'), 'newline': ('at line breaks', 'within lines')}
FSHORT = {'since_end': 'tokens since sentence end', 'at_end': 'sentence end', 'markup16': 'markup', 'pron32': 'I/you/!',
          'func16': 'function words', 'name': 'names', 'entropy': 'entropy', 'surprisal': 'surprisal', 'newline': 'newline'}


def f2(v):
    return f'{v:+.2f}'.replace('-', '−')


def f3(v):
    return f'{v:+.3f}'.replace('-', '−')


def tk(t):
    if t in DOC:
        return '‹doc-end›'
    s = t.replace('\n', '⏎')
    return '␣' if s.strip() == '' else s.strip()


def toks(lst, common, k=5, filt=True):
    out = []
    for t in lst:
        if filt and t not in common and t not in DOC:
            continue
        s = tk(t)
        if s not in out:
            out.append(s)
        if len(out) == k:
            break
    return out


def reading_feats(sr):
    """the (up to 3) context features a direction tracks, strongest first (|r| >= 0.15 with |h| divided out)"""
    c = sr['corr_cos']
    feats = [f for f in sorted(c, key=lambda f: -abs(c[f])) if f != 'norm' and abs(c[f]) >= 0.15]
    if 'at_end' in feats and 'newline' in feats:
        feats.remove('newline')
    return feats[:3]


def poles(sr):
    """(where it is high, where it is low) as phrases, from the features it tracks"""
    c = sr['corr_cos']
    feats = reading_feats(sr)
    hi = [PHRASE[f][0 if c[f] > 0 else 1] for f in feats]
    lo = [PHRASE[f][1 if c[f] > 0 else 0] for f in feats]
    join = lambda x: ', '.join(x[:-1]) + (' and ' if len(x) > 1 else '') + x[-1] if x else ''
    return join(hi), join(lo)


def reading(sr, fam):
    c = sr['corr_cos']
    feats = reading_feats(sr)
    if not feats:
        f = max((f for f in c if f != 'norm'), key=lambda f: abs(c[f]))
        return f'In ordinary text it tracks none of the features clearly (largest: {FSHORT[f]} r {f2(c[f])}).'
    hi = [PHRASE[f][0 if c[f] > 0 else 1] for f in feats]
    s = f'In ordinary text it is high {", ".join(hi[:-1]) + (" and " if len(hi) > 1 else "") + hi[-1]} (r with |h| divided out: ' + \
        ', '.join(f'{FSHORT[f]} {f2(c[f])}' for f in feats) + ')'
    if fam == 'sentence':
        s += ', rising steadily through a sentence' if c['since_end'] > 0 else ', highest just after a sentence end and falling through the sentence'
    elif fam == 'break':
        s += ', a spike at the token itself rather than a running count'
    return s + '.'


def ctx(lst):
    for x in lst:
        if not any(w in x.lower() for w in NSFW):
            return x[-52:]
    return None


def families(path=f'{O}/sense/families.json'):
    """{(layer, side, rank): (family, score)}"""
    out = {}
    for k, v in json.load(open(path)).items():
        L, side, rank = k.split('_')
        out[int(L), side, int(rank)] = v
    return out


def common_tokens(run):
    """token pieces written in >= 25% of the sweep prompts (rarer ones are prompt-specific topic words)"""
    sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
    import gguf
    rd = gguf.GGUFReader(MODEL)
    fld = rd.fields['tokenizer.ggml.tokens']
    vocab = [bytes(fld.parts[i]).decode('utf-8', 'replace') for i in fld.data]
    bs = list(range(33, 127)) + list(range(0xA1, 0xAD)) + list(range(0xAE, 0x100))
    cs, k_ = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b); cs.append(256 + k_); k_ += 1
    dec = {chr(c): b for b, c in zip(bs, cs)}
    piece = lambda i: bytes(dec.get(ch, 63) for ch in vocab[i]).decode('utf-8', 'replace')
    tok = np.array(run.recs['tok']); pr = run.prompt
    cov = {}
    for q in np.unique(pr):
        for t in set(np.unique(tok[pr == q]).tolist()):
            p = piece(t); cov[p] = cov.get(p, 0) + 1
    return {p for p, c in cov.items() if c >= 0.25 * len(np.unique(pr))}


def layer_resolved(r):
    """a layer whose extreme in-sample kappa beats the shuffled null and whose strongest held-out kappa passes 0.03"""
    return (((r['kappa'][0] > r['null_top95']) or (r['kappa'][-1] < r['null_bottom5']))
            and max(r['heldout_pushback'][0], -r['heldout_amplify'][0]) > 0.03)


def clears(side, ho):
    return ho >= 0.03 if side == 'pushback' else ho <= -0.03
