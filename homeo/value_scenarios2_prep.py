#!/usr/bin/env python3
"""Scenario set 2 for the value lens: does stakes order model-written text the way the group predicted
(rich worldbuilding > boring prose > loops)? Set 1 compared 12 model-written fiction windows with human
fineweb text; here every group is model-written by the same procedure, so authorship is not a confound:

- fiction:    worldbuilding openings (the 12 from set 1 plus 24 new)
- boring:     SEO filler, policies, listings, corporate prose (36)
- structured: procedures, recipes, lists, verse, math (24); VL1's highest-stakes fineweb windows were like this

Each prompt is continued by the base model itself through llama-server (unsteered, temperature 1, no
truncation, no penalties), 2 continuations per prompt (seeds tried in order until 2 reach 192 tokens). The
window is the exact token ids the model saw and produced: prompt ids + generated ids, first 192.

Writes OUT/scenario_ids.bin (i32, back to back), OUT/manifest.json, OUT/texts.jsonl.

usage: value_scenarios2_prep.py [--out /mnt/models/homeo/value_scen2] [--per-prompt 2] [--pause 2]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_scenarios_prep import PROMPTS as FICTION1  # noqa: E402

ROOT = '/home/bepis/prog/llm-tests'
MODEL = '/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf'
BIN = f'{ROOT}/llama.cpp/build-avx2/bin'
T = 192
PORT = 8097

FICTION2 = [
    "The salt witches of Orrin Bay measured time in tides, not hours, and so when the tide failed to come in on the morning of",
    "Beneath the glacier city of Hesk, the miners had found a second sky, complete with its own stars and weather. The first expedition",
    "My mother was a cartographer for the Guild of Unfinished Roads, which meant that every map she drew",
    "In the republic of Lanterns, citizens vote by lighting candles in their windows, and the night of the great election",
    "The dragon's accountant had three rules, and the first was never to let the dragon see the ledger. The second",
    "Long after the bells stopped ringing in Calder, people still set a place at the table for the Bellkeeper, because",
    "The forest of Ysmere moves one step east every century, and the villages that live at its edge have learned to",
    "Station Halcyon orbited a gas giant whose storms sang in frequencies only the station's oldest engineer could hear.",
    "When the king outlawed music, the river barges of the Velt began to carry a new kind of cargo:",
    "The glassmakers of Murrow could trap a single afternoon inside a bottle, and the wealthy paid fortunes to open",
    "On the island where the clocks run backward, the oldest woman in the village was also the youngest, and she",
    "Every hundred years the sea gives back one thing it has taken. This year, on the shingle below the lighthouse,",
    "The Order of the Ninth Bell trained its novices to listen to stone. By her third year, Sister Aurel could hear",
    "The archive of lost recipes was kept by a family of mice who had been cooks to the old emperor, and",
    "In Teshmar the dead are allowed one visit home each year, on the night of the copper moon, and my grandfather",
    "The airship Meridian carried mail between the floating cities, and its captain had never once set foot on the ground below.",
    "The weavers of the high valley wove their history into a single tapestry that grew longer every winter. The newest panel showed",
    "Our village had a contract with the wind: we would never build higher than the old oak, and in return",
    "The cartography of dreams was a respected science in Ostrava, and the Academy's newest map had a blank space in the middle that",
    "The last train out of Verrin ran only at midnight, and only for passengers who could pay with a memory.",
    "The kingdom's borders were drawn in chalk, renewed every spring by the Border Choir, and the year the rains came early",
    "When the stars over Kell began to go out one by one, the astronomers' guild sent its youngest apprentice to find out",
    "The lighthouse keeper's daughter could speak to ships, and the ships, it turned out, had a great deal to say about",
    "In the underground markets of Sorrow's End, you could buy anything with a secret, and the most expensive stall belonged to",
]

BORING = [
    "When it comes to choosing the right insurance policy for your needs, there are many factors to consider. First of all,",
    "Our company is committed to providing the highest quality products and services to our valued customers. We believe that",
    "This Privacy Policy describes how we collect, use, and disclose information about you when you use our website and services.",
    "We use cookies to improve your experience on our website. By continuing to browse this site, you agree to our use of cookies.",
    "Looking for the best carpet cleaning services in your area? Look no further! Our team of experienced professionals",
    "Product Description: This stainless steel water bottle is perfect for everyday use. It features a durable design and",
    "Terms and Conditions. 1. Acceptance of Terms. By accessing and using this website, you accept and agree to be bound by",
    "Spacious 3 bedroom, 2 bathroom home located in a quiet neighborhood. This property features an updated kitchen,",
    "Are you looking to improve your website's search engine rankings? Search engine optimization, or SEO, is the process of",
    "FOR IMMEDIATE RELEASE. The company today announced the appointment of a new Vice President of Sales, effective",
    "Thank you for contacting customer support. We have received your request and a member of our team will respond",
    "In today's fast-paced business environment, it is more important than ever to have an effective marketing strategy.",
    "Meeting Minutes. The meeting was called to order at 10:00 a.m. Present were the members of the committee. The minutes",
    "Before you buy a new laptop, it is a good idea to think about what you will be using it for. There are many",
    "Shipping Information: Orders are processed within 1-2 business days. Orders placed on weekends or holidays",
    "Welcome to our website! We are a family-owned business that has been serving the local community for over",
    "Disclaimer: The information provided on this website is for general informational purposes only. All information on",
    "Job Description: We are seeking a highly motivated and detail-oriented Administrative Assistant to join our team.",
    "Home improvement projects can add value to your home and make it a more comfortable place to live. Whether you",
    "Frequently Asked Questions. Q: How do I reset my password? A: To reset your password, click on the",
    "The quarterly report shows that revenue increased compared to the same period last year, driven primarily by",
    "Return Policy: If you are not completely satisfied with your purchase, you may return it within 30 days of",
    "Dental hygiene is an important part of your overall health. It is recommended that you brush your teeth at least",
    "Our team of dedicated professionals works hard to ensure that every client receives personalized service and",
    "Choosing the right hotel can make or break your vacation. Here are some tips to help you find the perfect",
    "This article will discuss the benefits of regular exercise. Exercise is important for maintaining good health and",
    "Installation Instructions: Before beginning installation, please read all instructions carefully and make sure",
    "Dear Valued Customer, We are writing to inform you of some upcoming changes to our service. Beginning next month,",
    "There are many different types of flooring available for your home, including hardwood, laminate, tile, and",
    "Employee Handbook. Section 4: Attendance. Employees are expected to arrive on time for their scheduled shifts.",
    "If you are planning a wedding, one of the first things you will need to do is set a budget. Weddings can",
    "Car maintenance is essential to keep your vehicle running smoothly. Regular oil changes, tire rotations, and",
    "Subscribe to our newsletter to receive the latest news, updates, and special offers delivered directly to your inbox.",
    "Our mission is to empower businesses of all sizes with innovative solutions that drive growth and efficiency.",
    "Moving to a new city can be both exciting and stressful. There are many things to consider when planning",
    "The board of directors met on Tuesday to review the annual budget. After a brief discussion, the board voted",
]

STRUCTURED = [
    "How to change a bicycle tire:\n1. Shift to the smallest cog and open the brake.\n2.",
    "Recipe: Lentil soup\nIngredients:\n- 1 cup dried lentils\n- 1 onion, diced\n-",
    "Proof that the square root of 2 is irrational. Suppose, for contradiction, that",
    "Sonnet\n\nWhen winter lays its silver on the hill,\nAnd every branch bends low beneath the snow,\n",
    "To solve the equation 3x^2 - 12x + 9 = 0, first divide both sides by 3 to get",
    "Algorithm for binary search on a sorted array:\n1. Set low = 0 and high = n - 1.\n2.",
    "Chess opening notes: the Queen's Gambit.\n1. d4 d5 2. c4. White offers a pawn to",
    "Instructions for assembling the bookshelf:\nStep 1: Attach side panel A to the base panel B using four cam bolts.\nStep 2:",
    "The thirteen colonies, in order of founding:\n1. Virginia (1607)\n2.",
    "Haiku sequence: the four seasons\n\nSpring\nfirst warm rain at dusk\n",
    "def fibonacci(n):\n    \"\"\"Return the n-th Fibonacci number.\"\"\"\n    if n < 2:\n",
    "Lab protocol: DNA extraction from strawberries.\nMaterials: 2 strawberries, dish soap, salt, cold ethanol.\nProcedure:\n1.",
    "Theorem. Every finite group of prime order is cyclic.\nProof. Let G be a group of order p, where p is prime.",
    "Knitting pattern: simple scarf\nCast on 30 stitches.\nRow 1:",
    "The planets of the solar system, with their distances from the Sun:\n- Mercury: 0.39 AU\n-",
    "A villanelle\n\nThe tide returns to take what it once gave,\n",
    "How to make sourdough starter:\nDay 1: Mix 50 g whole wheat flour with 50 g water in a clean jar.\nDay 2:",
    "Glossary of sailing terms:\nAft - toward the stern of the boat.\nBeam -",
    "Derivation of the quadratic formula. Start with ax^2 + bx + c = 0 and divide by a:",
    "Itinerary: three days in Kyoto\nDay 1, morning: Fushimi Inari shrine, arriving early to",
    "The rules of the game are as follows. Each player begins with seven cards. On your turn, you must",
    "Translation exercise. Translate each sentence into French.\n1. The cat is under the table. - Le chat est sous la table.\n2.",
    "First aid for a minor burn:\n1. Cool the burn under cool running water for",
    "Ballad of the miller's son\n\nThe miller's son went down to town\nWith flour upon his sleeve,\n",
]


def post(path, body):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='/mnt/models/homeo/value_scen2')
    ap.add_argument('--per-prompt', type=int, default=2)
    ap.add_argument('--pause', type=float, default=2.0, help='seconds between requests (quieter GPU)')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    groups = [('fiction', FICTION1 + FICTION2), ('boring', BORING), ('structured', STRUCTURED)]
    srv = subprocess.Popen([f'{BIN}/llama-server', '-m', MODEL, '-ngl', '99', '-c', '2048', '-np', '1', '--port', str(PORT),
                            '--no-webui'], stdout=open(f'{a.out}/server.log', 'w'), stderr=subprocess.STDOUT)
    try:
        for _ in range(600):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=5)
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError('llama-server did not come up')
        windows, manifest = [], []
        tf = open(f'{a.out}/texts.jsonl', 'w')
        for group, prompts in groups:
            for pi, prompt in enumerate(prompts):
                pids = post('/tokenize', {'content': prompt, 'add_special': False})['tokens']
                got = 0
                for seed in range(2000, 2008):
                    if got == a.per_prompt:
                        break
                    r = post('/completion', {'prompt': pids, 'n_predict': 240, 'temperature': 1.0, 'top_k': 0, 'top_p': 1.0,
                                             'min_p': 0.0, 'typical_p': 1.0, 'repeat_penalty': 1.0, 'presence_penalty': 0.0,
                                             'frequency_penalty': 0.0, 'dry_multiplier': 0.0, 'xtc_probability': 0.0,
                                             'top_n_sigma': -1.0, 'mirostat': 0, 'seed': seed, 'cache_prompt': False,
                                             'return_tokens': True})
                    ids = pids + r['tokens']
                    time.sleep(a.pause)
                    if len(ids) < T:
                        print(f'{group} {pi} seed {seed}: only {len(ids)} tokens, skipped', flush=True)
                        continue
                    windows.append(ids[:T])
                    manifest.append(dict(scenario=group, prompt=pi, seed=seed, n_prompt=len(pids)))
                    tf.write(json.dumps(dict(scenario=group, prompt=pi, seed=seed, text=prompt + r['content'])) + '\n')
                    tf.flush()
                    got += 1
                    print(f'{group} {pi} seed {seed}: {(prompt + r["content"])[:100]!r}', flush=True)
    finally:
        srv.terminate()
        srv.wait()
    import numpy as np
    np.array([t for w in windows for t in w], dtype=np.int32).tofile(f'{a.out}/scenario_ids.bin')
    json.dump(manifest, open(f'{a.out}/manifest.json', 'w'), indent=1)
    print(f'wrote {len(windows)} windows to {a.out}/scenario_ids.bin')


if __name__ == '__main__':
    main()
