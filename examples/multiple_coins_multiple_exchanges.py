from peregrinearb import create_weighted_multi_exchange_digraph, bellman_ford_multi, \
    print_profit_opportunity_for_path_multi


#graph = create_weighted_multi_exchange_digraph(['bittrex', 'gemini', 'kraken'], log=True)
#VOLUME = None
VOLUME = 70

graph = create_weighted_multi_exchange_digraph(['bittrex', 'kraken'], log=True, volume=VOLUME)

#graph, paths = bellman_ford_multi(graph, 'ETH', loop_from_source=False, unique_paths=True)
graph, paths = bellman_ford_multi(graph, 'ETH', loop_from_source=False, unique_paths=True)
for path in paths:
    print_profit_opportunity_for_path_multi(graph, path, volume=VOLUME)
