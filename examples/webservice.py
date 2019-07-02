#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sys import version_info
if not (version_info[0] >= 3 and version_info[1] >= 7):
    raise Exception('python3.7 or higher required')


import ssl
import asyncio
from aiohttp import web
import nest_asyncio
import argparse
from peregrinearb import create_weighted_multi_exchange_digraph, bellman_ford_multi, \
    print_profit_opportunity_for_path_multi


parser = argparse.ArgumentParser(description="peregrine webservice")
parser.add_argument('--port')


def ask_peregrine(exchanges: list, volume: int) -> list:
    graph = create_weighted_multi_exchange_digraph(exchanges, log=True, volume=volume)
    graph, paths = bellman_ford_multi(graph, 'ETH', loop_from_source=False, unique_paths=True)
    results = list()
    for path in paths:
        results.append(print_profit_opportunity_for_path_multi(graph, path, volume=volume))
    return results


async def handle(req):
    try:
        incoming = await req.json()
        print("incoming: %s" % incoming)
        exchanges = incoming["exchanges"]
        volume = incoming["volume"]
        print("processing...")
        results = ask_peregrine(exchanges, volume)
        print("responded: %s" % str(results))
        resp = {"data": results}
    except Exception as e:
        print("An error occured:")
        print(e)
        resp = {"error": str(e)}
    return web.json_response(resp)


if __name__ == "__main__":
    args = parser.parse_args()
    nest_asyncio.apply()

    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain('cert.crt', 'cert.key')

    app = web.Application()
    app.add_routes([web.get("/peregrine", handle)])
    web.run_app(app, port=args.port, ssl_context=ssl_context)
