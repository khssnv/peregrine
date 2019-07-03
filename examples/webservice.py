#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sys import version_info
if not (version_info[0] >= 3 and version_info[1] >= 7):
    raise Exception('python3.7 or higher required')


import ast
import ssl
import asyncio
from aiohttp import web
import aiohttp_cors
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
        #incoming = await req.json()
        exchanges = ast.literal_eval(req.rel_url.query["exchanges"])
        volume = int(req.rel_url.query["volume"])
        #print("incoming: %s" % incoming)
        print("incoming req for exchanges: %s, volume: %s" % (exchanges, volume))
        #exchanges = incoming["exchanges"]
        #volume = incoming["volume"]
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

    #ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    #ssl_context.load_cert_chain('cert.crt', 'cert.key')

    app = web.Application()
    cors = aiohttp_cors.setup(app)
    resource = cors.add(app.add_resource("/peregrine"))
    route = cors.add(
        resource.add_route("GET", handle), {
            "http://gengix.com": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers=("X-Custom-Server-Header",),
                max_age=360,
            )
        }
    )
    #web.run_app(app, port=args.port, ssl_context=ssl_context)
    web.run_app(app, port=args.port)
