"""Headless Firefox over WebDriver BiDi: load the scratch loom, pick a direction probe, screenshot.

Safety: localStorage points the loom at :8056 before any page script runs, and every request to port 8055
(the user's lazy launcher) is failed at the network layer.
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import time

import websockets

S = os.path.dirname(os.path.abspath(__file__))
PORT = 9333
TEXT = ("The committee approved the annual budget on Tuesday. According to the report, spending on infrastructure "
        "will rise by 4.2 percent over the next fiscal year, while the education budget remains flat.\n\n"
        "lol I can't believe you actually did that!! I'm so proud of you, honestly. You should come over this weekend "
        "and we'll celebrate, ok?\n\n"
        "Ingredients:\n- 2 cups flour\n- 1 tsp salt\n- 3 eggs\n\n"
        "John Smith, director of the National Research Center in Boulder, said the results were encouraging but that "
        "more work was needed before the method could be used in hospitals.")
STEPS = json.loads(sys.argv[1]) if len(sys.argv) > 1 else [{'layer': 40, 'dir': 'L40.pushback.0', 'shot': 'l40_pb0'}]


class Bidi:
    def __init__(self, ws):
        self.ws, self.n, self.pending, self.handlers = ws, 0, {}, []

    async def reader(self):
        async for msg in self.ws:
            m = json.loads(msg)
            if 'id' in m and m['id'] in self.pending:
                self.pending.pop(m['id']).set_result(m)
            elif m.get('type') == 'event':
                for h in self.handlers:
                    asyncio.create_task(h(m))

    async def cmd(self, method, params):
        self.n += 1
        fut = asyncio.get_event_loop().create_future()
        self.pending[self.n] = fut
        await self.ws.send(json.dumps({'id': self.n, 'method': method, 'params': params}))
        r = await asyncio.wait_for(fut, 120)
        if r.get('type') == 'error':
            raise RuntimeError(f'{method}: {r.get("error")}: {r.get("message")}')
        return r['result']


async def main():
    prof = os.path.join(S, 'ffprof')
    os.makedirs(prof, exist_ok=True)
    ff = subprocess.Popen(['firefox', '--headless', '--no-remote', '--profile', prof, f'--remote-debugging-port={PORT}',
                           '--window-size=1400,1000'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                ws = await websockets.connect(f'ws://127.0.0.1:{PORT}/session', max_size=64 << 20)
                break
            except OSError:
                time.sleep(0.5)
        b = Bidi(ws)
        asyncio.create_task(b.reader())
        await b.cmd('session.new', {'capabilities': {}})
        ctx = (await b.cmd('browsingContext.getTree', {}))['contexts'][0]['context']
        await b.cmd('browsingContext.setViewport', {'context': ctx, 'viewport': {'width': 1400, 'height': 1000}})

        blocked = []

        async def on_event(m):
            if m['method'] == 'network.beforeRequestSent' and m['params'].get('isBlocked'):
                blocked.append(m['params']['request']['url'])
                await b.cmd('network.failRequest', {'request': m['params']['request']['request']})
        b.handlers.append(on_event)
        await b.cmd('session.subscribe', {'events': ['network.beforeRequestSent']})
        for host in ('localhost', '127.0.0.1'):
            await b.cmd('network.addIntercept', {'phases': ['beforeRequestSent'],
                                                 'urlPatterns': [{'type': 'pattern', 'hostname': host, 'port': '8055'}]})
        await b.cmd('script.addPreloadScript', {'functionDeclaration':
            "() => { try { localStorage.setItem('loomui:serverUrl', 'http://127.0.0.1:8056/completion'); } catch (e) {} }"})
        async def ev(expr):
            r = await b.cmd('script.evaluate', {'expression': expr, 'target': {'context': ctx}, 'awaitPromise': True})
            if r.get('type') != 'success':
                raise RuntimeError(f'evaluate failed: {r.get("exceptionDetails", r)}')
            return r['result'].get('value')

        # same origin, no page scripts: set the server url and check it stuck before the loom page ever loads
        await b.cmd('browsingContext.navigate', {'context': ctx, 'url': 'http://127.0.0.1:5055/no-such-page', 'wait': 'complete'})
        await ev("localStorage.setItem('loomui:serverUrl', 'http://127.0.0.1:8056/completion')")
        url = await ev("localStorage.getItem('loomui:serverUrl')")
        assert url == 'http://127.0.0.1:8056/completion', url
        await b.cmd('browsingContext.navigate', {'context': ctx, 'url': 'http://127.0.0.1:5055/', 'wait': 'complete'})

        await asyncio.sleep(1.5)
        await ev(f"(() => {{ const p = document.getElementById('pad'); p.value = {json.dumps(TEXT)}; p.dispatchEvent(new Event('input', {{bubbles: true}})); }})()")
        print('section visible:', await ev("!document.getElementById('dirSection').hidden"))
        print('layers:', await ev("document.getElementById('dirLayer').options.length"))
        for st in STEPS:
            if st.get('color'):
                await ev(f"""(() => {{ const t = document.getElementById('valueToggle'); if (!t.checked) {{ t.checked = true; t.dispatchEvent(new Event('change')); }}
                    const s = document.getElementById('valueColor'); s.value = '{st['color']}'; s.dispatchEvent(new Event('change')); }})()""")
                for _ in range(120):
                    if await ev("document.querySelectorAll('#highlight .tok[style]').length"):
                        break
                    await asyncio.sleep(0.25)
                await asyncio.sleep(0.5)
                print(st['color'], 'tinted', await ev("document.querySelectorAll('#highlight .tok[style]').length"), 'of', await ev("document.querySelectorAll('#highlight .tok').length"))
                if st.get('hover') is not None:
                    await ev(f"""(() => {{ const sp = document.querySelector('#highlight .tok[data-i="{st['hover']}"]'); const r = sp.getBoundingClientRect();
                        sp.dispatchEvent(new MouseEvent('mousemove', {{bubbles: true, clientX: r.left + 2, clientY: r.top + 2}})); }})()""")
                    await asyncio.sleep(0.5)
                    print('  tip:', (await ev("document.getElementById('lensTip').innerText") or '')[:1400])
                if st.get('shot'):
                    img = (await b.cmd('browsingContext.captureScreenshot', {'context': ctx}))['data']
                    open(os.path.join(S, st['shot'] + '.png'), 'wb').write(base64.b64decode(img))
                continue
            await ev(f"(() => {{ const s = document.getElementById('dirLayer'); s.value = '{st['layer']}'; s.dispatchEvent(new Event('change')); }})()")
            if st.get('dir'):
                await ev(f"(() => {{ const s = document.getElementById('dirPick'); s.value = '{st['dir']}'; s.dispatchEvent(new Event('change')); }})()")
            t0 = time.time()
            for _ in range(240):
                n = await ev("document.querySelectorAll('#highlight .tok[style]').length")
                if n:
                    break
                await asyncio.sleep(0.25)
            print(f"{st}: {n} tinted tokens of", await ev("document.querySelectorAll('#highlight .tok').length"),
                  f'after {time.time() - t0:.1f} s; error:', await ev("document.querySelector('#lensTip') && (document.body.innerText.match(/direction probe error.*/) || [''])[0]"))
            if st.get('flip'):
                await ev("document.getElementById('dirFlip').click()")
                await asyncio.sleep(0.3)
            print('  picker:', await ev("document.getElementById('dirPick').selectedOptions[0]?.textContent"), '| button:', await ev("document.getElementById('dirFlip').textContent"))
            print('  orange/blue tokens:', await ev("[...document.querySelectorAll('#highlight .tok[style]')].filter(x => x.style.background.includes('251')).length"),
                  await ev("[...document.querySelectorAll('#highlight .tok[style]')].filter(x => x.style.background.includes('96')).length"),
                  '| first tokens:', await ev("[...document.querySelectorAll('#highlight .tok')].slice(0, 4).map(x => x.style.background.includes('251') ? 'O' : x.style.background.includes('96') ? 'B' : '-').join('')"))
            print('  info:', (await ev("document.getElementById('dirInfo').innerText") or '')[:900].replace('\n', ' / '))
            if st.get('hover') is not None:
                await ev(f"""(() => {{ const sp = document.querySelector('#highlight .tok[data-i="{st['hover']}"]'); const r = sp.getBoundingClientRect();
                    sp.dispatchEvent(new MouseEvent('mousemove', {{bubbles: true, clientX: r.left + 2, clientY: r.top + 2}})); }})()""")
                await asyncio.sleep(0.5)
                print('  tip:', (await ev("document.getElementById('lensTip').innerText") or '')[:1200])
            if st.get('steer') is not None:
                await ev(f"""(() => {{ const sp = document.querySelector('#highlight .tok[data-i="{st['steer']}"]'); const r = sp.getBoundingClientRect();
                    sp.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true, clientX: r.left + 2, clientY: r.top + 2}})); }})()""")
                for _ in range(60):
                    if await ev("!!document.getElementById('steerRun')"):
                        break
                    await asyncio.sleep(0.25)
                await ev("document.getElementById('steerRun').click()")
                t1 = time.time()
                for _ in range(600):
                    st_html = await ev("document.getElementById('steerOut') ? document.getElementById('steerOut').innerHTML : ''")
                    if '<svg' in st_html or 'lt-err' in st_html:
                        break
                    await asyncio.sleep(0.25)
                print(f'  steer after {time.time() - t1:.1f} s:', (await ev("document.getElementById('steerOut').innerText") or '')[:1500])
            if st.get('settings'):
                await ev("document.getElementById('settingsToggle').click()")
                await asyncio.sleep(0.3)
            if st.get('shot'):
                img = (await b.cmd('browsingContext.captureScreenshot', {'context': ctx}))['data']
                open(os.path.join(S, st['shot'] + '.png'), 'wb').write(base64.b64decode(img))
            if st.get('settings'):
                await ev("document.getElementById('settingsToggle').click()")
        print('blocked 8055 requests:', blocked)
    finally:
        ff.terminate()

asyncio.run(main())
