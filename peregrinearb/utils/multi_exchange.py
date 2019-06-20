import asyncio
import math
import networkx as nx
from ccxt import async_support as ccxt
import warnings
import numpy as np
import logging


logging.basicConfig(filename="search.log", filemode='w', level=logging.ERROR, format=("%(message)s"))
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.info("Starting logger...")


def create_multi_exchange_graph(exchanges: list, digraph=False):
    """
    Returns a MultiGraph representing the markets for each exchange in exchanges. Each edge represents a market.
    Note: does not add edge weights using the ticker's ask and bid prices.
    exchange.load_markets() must have been called for each exchange in exchanges. Will throw a ccxt error if it has not.

    todo: check which error.
    """
    if digraph:
        graph = nx.MultiDiGraph()
    else:
        graph = nx.MultiGraph()

    for exchange in exchanges:
        for market_name in exchange.symbols:
            try:
                base_currency, quote_currency = market_name.split('/')
            # if ccxt returns a market in incorrect format (e.g FX_BTC_JPY on BitFlyer)
            except ValueError:
                continue

            graph.add_edge(base_currency,
                           quote_currency,
                           market_name=market_name,
                           exchange_name=exchange.name.lower())
            if digraph:
                graph.add_edge(quote_currency,
                               base_currency,
                               market_name=market_name,
                               exchange_name=exchange.name.lower())

    return graph


def create_weighted_multi_exchange_digraph(exchanges: list, name=True, log=False, fees=False, suppress=None, volume=None):
    """
    Not optimized (in favor of readability). There is multiple iterations over exchanges.
    """
    if suppress is None:
        suppress = ['markets']

    if name:
        exchanges = [{'object': getattr(ccxt, exchange)()} for exchange in exchanges]
    else:
        exchanges = [{'object': exchange} for exchange in exchanges]

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.get_running_loop()
    futures = [asyncio.ensure_future(exchange_dict['object'].load_markets()) for exchange_dict in exchanges]
    loop.run_until_complete(asyncio.gather(*futures))

    if fees:
        for exchange_dict in exchanges:
            if 'maker' in exchange_dict['object'].fees['trading']:
                # we always take the maker side because arbitrage depends on filling orders
                exchange_dict['fee'] = exchange_dict['object'].fees['trading']['maker']
            else:
                if 'fees' not in suppress:
                    warnings.warn("The fees for {} have not yet been implemented into the library. "
                                  "Values will be calculated using a 0.2% maker fee.".format(exchange_dict['object'].id))
                exchange_dict['fee'] = 0.002
    else:
        # todo: is there a way to do this with list/ dict comprehension?
        for exchange_dict in exchanges:
            exchange_dict['fee'] = 0

    graph = nx.MultiDiGraph()
    futures = [_add_exchange_to_multi_digraph(graph, exchange, log=log, suppress=suppress, volume=volume) for exchange in exchanges]
    loop.run_until_complete(asyncio.gather(*futures))
    return graph


async def _add_exchange_to_multi_digraph(graph: nx.MultiDiGraph, exchange, log=True, suppress=None, volume=None):
    tasks = [_add_market_to_multi_digraph(exchange, symbol, graph, log=log, suppress=suppress, volume=volume)
             for symbol in exchange['object'].symbols]
    await asyncio.wait(tasks)
    await exchange['object'].close()


async def calc_average_price_for_volume(orders, volume_pair_desired):
    # 19 June 2019, Alisher Khassanov, <a.khssnv@gmail.com>:
    # We replace a ticker price here by average price you will have whlie buy orders for given volume
    """returns weighted average price from orders up to given volume
    """
    avg_price = None
    considered = list()
    prices, volumes = list(), list()
    cum_vol_pair = 0
    for (pri, vol), (next_pri, next_vol) in zip(orders, orders[1:]):
        #logger.info("price: %s, volume: %s", str(pri), str(vol))
        considered.append((pri,vol))
        if pri*vol > volume_pair_desired: # all from first order
            prices.append(pri)
            volumes.append(volume_pair_desired)
            cum_vol_pair = volume_pair_desired
            logging.info('')
            break
        prices.append(pri)
        volumes.append(vol)
        cum_vol_pair += pri * vol
        if cum_vol_pair + next_pri*next_vol > volume_pair_desired:
            prices.append(next_pri)
            volumes.append(volume_pair_desired - cum_vol_pair) # take the rest from next order to reach volume
            cum_vol_pair += volume_pair_desired - cum_vol_pair
            break

    avg_price = np.average(prices, weights=volumes)

    return avg_price, cum_vol_pair, considered


# todo: refactor. there is a lot of code repetition here with single_exchange.py's _add_weighted_edge_to_graph
# todo: write tests which prove market_name is always a ticker on exchange and exchange's load_markets has been called.
# this will validate that all exceptions thrown by await exchange.fetch_ticker(market_name) are solely because of
# ccxt's fetch_ticker
async def _add_market_to_multi_digraph(exchange, market_name: str, graph: nx.DiGraph, log=True, suppress=None, volume=None):
    if suppress is None:
        raise ValueError("suppress cannot be None. Must be a list with possible values listed in docstring of"
                         "create_weighted_multi_exchange_digraph. If this error shows, something likely went awry "
                         "during execution.")

    try:
        ticker = await exchange['object'].fetch_ticker(market_name)
    # any error is solely because of fetch_ticker
    except:
        if 'markets' not in suppress:
            warning = 'Market {} is unavailable at this time.'.format(market_name)
            warnings.warn(warning)
        return

    try:
        """
        ticker_ask = ticker['ask']
        ticker_bid = ticker['bid']
        """
        # 19 June 2019, Alisher Khassanov, <a.khssnv@gmail.com>:
        # We replace a ticker price here by average price you will have whlie buy orders for given volume
        if not volume:
            ticker_ask = ticker['ask']
            ticker_bid = ticker['bid']
        else:
            orderbook = await exchange['object'].fetch_l2_order_book(market_name)
            ticker_ask, ask_vol, asks_cons = await calc_average_price_for_volume(orderbook['asks'], volume)
            ticker_bid, bid_vol, bids_cons  = await calc_average_price_for_volume(orderbook['bids'], volume)
            logger.info('== Considering %s at %s : format [price, volume] ==', market_name, str(exchange['object']))
            logger.info('-- Considered %d asks: %s', len(asks_cons), str(asks_cons))
            logger.info('-- Considered %d bids: %s', len(bids_cons), str(bids_cons))
            if ask_vol < volume or bid_vol < volume: # insufficient volume in orderbook
                return

    # ask and bid == None if this market does not exist.
    except TypeError:
        return

    # prevent math error when Bittrex (GEO/BTC) or other API gives 0 as ticker price
    if ticker_ask == 0:
        return
    try:
        base_currency, quote_currency = market_name.split('/')
    # if ccxt returns a market in incorrect format (e.g FX_BTC_JPY on BitFlyer)
    except ValueError:
        return

    fee_scalar = 1 - exchange['fee']

    if log:
        graph.add_edge(base_currency, quote_currency,
                       market_name=market_name,
                       exchange_name=exchange['object'].id,
                       weight=-math.log(fee_scalar * ticker_bid))

        graph.add_edge(quote_currency, base_currency,
                       market_name=market_name,
                       exchange_name=exchange['object'].id,
                       weight=-math.log(fee_scalar * 1 / ticker_ask))
    else:
        graph.add_edge(base_currency, quote_currency,
                       market_name=market_name,
                       exchange_name=exchange['object'].id,
                       weight=fee_scalar * ticker_bid)

        graph.add_edge(quote_currency, base_currency,
                       market_name=market_name,
                       exchange_name=exchange['object'].id,
                       weight=fee_scalar * 1 / ticker_ask)


def multi_graph_to_log_graph(digraph: nx.MultiDiGraph):
    """
    This does not work with the default version of Networkx, but with the fork available at wardbradt/Networkx

    Given weighted MultiDigraph m1, returns a MultiDigraph m2 where for each edge e1 in each edge bunch eb1 of m1, the
    weight w1 of e1 is replaced with log(w1) and the weight w2 of each edge e2 in the opposite edge bunch of eb is
    log(1/w2)

    This function is not optimized.

    todo: allow this function to be used with Networkx DiGraph objects. Should not be that hard, simply return seen
    from self._report in the iterator for digraph's edges() in reportviews.py as it is done for multidigraph's
    edge_bunches()
    """
    result_graph = nx.MultiDiGraph()
    for bunch in digraph.edge_bunches(data=True, seen=True):
        for data_dict in bunch[2]:
            weight = data_dict.pop('weight')
            # if not seen
            if not bunch[3]:
                result_graph.add_edge(bunch[0], bunch[1], -math.log(weight), **data_dict)
            else:
                result_graph.add_edge(bunch[0], bunch[1], -math.log(1/weight), **data_dict)


