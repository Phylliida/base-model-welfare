import json, time, urllib.request, sys
from concurrent.futures import ThreadPoolExecutor
S = 'http://127.0.0.1:8056'
def post(path, p):
    r = urllib.request.Request(S + path, data=json.dumps(p).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(r, timeout=3600) as f:
        return json.load(f)
N, T = int(sys.argv[1]), int(sys.argv[2])
ids = post('/tokenize', {'content': 'The history of the'})['tokens'][:3]
def run(i):
    return post('/completion', {'prompt': ids, 'n_predict': T, 'temperature': 1.0, 'samplers': ['temperature'], 'top_k': 0, 'top_p': 1.0,
                                'min_p': 0.0, 'typical_p': 1.0, 'repeat_penalty': 1.0, 'seed': 1000 + i, 'return_tokens': True, 'cache_prompt': False})
t0 = time.time()
with ThreadPoolExecutor(N) as ex:
    outs = list(ex.map(run, range(N)))
dt = time.time() - t0
n = sum(len(o['tokens']) for o in outs)
print(f'{N} x {T}: {n} tokens in {dt:.1f} s = {n/dt:.0f} tok/s; stop types', {o.get("stop_type") for o in outs}, 'lens', sorted(len(o['tokens']) for o in outs)[:5])
print(outs[0]['generation_settings']['samplers'] if 'generation_settings' in outs[0] else '', outs[0]['content'][:200].replace('\n', ' '))
