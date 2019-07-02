import aiohttp
import asyncio

async def fetch(s, u):
    #async with s.get(u, json={'jkey': 42, 'l': [1,2,3]}) as resp:
    async with s.get(u, json={'exchanges': ['bittrex', 'kraken'], 'volume': 10}) as resp:
        try:
            print(await resp.json())
        except:
            print(await resp.text())
        return await resp.text()

async def main():
    async with aiohttp.ClientSession() as s:
        html = await fetch(s, 'http://127.0.0.1:8080/peregrine')
        #print(html)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
