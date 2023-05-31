import logging

import networkx as nx
import numpy as np
import pandas as pd
import requests

NAMESPACE = "edgex"
METRIC_TIME_INTERVAL = "1m"
NODE_DICT = {
    '10.0.11.7:10250': 'm1',
    '10.0.11.8:10250': 'm2',
    '10.0.11.9:10250': 'm3'
}
logger = logging.getLogger(__name__)
session = requests.Session()


def convert_to_usage_by_container(results):
    usage_by_container = {}
    for result in results:
        metric = result["metric"]
        if "container" not in metric:
            continue
        usage_by_container[metric["container"]] = result["value"][1]
    return usage_by_container


def convert_to_availability_by_container(results):
    availabilities = {}
    for result in results:
        metric = result["metric"]
        availabilities[metric["org_edgexfoundry_service"]] = result["value"][1]
    return availabilities


def prometheus_query(prom_url, query):
    response = session.get(prom_url + "/api/v1/query",
                           params={'query': query}, timeout=5)
    return response.json()['data']['result']


def get_response_times(config):
    prom_url = config['prometheus_url']
    latency_df = pd.DataFrame()

    # Istio request duration

    query = 'histogram_quantile(0.95, sum(irate(istio_request_duration_milliseconds_bucket{reporter=\"source\", ' \
            'destination_workload_namespace=\"' + NAMESPACE + \
            '\"}[' + METRIC_TIME_INTERVAL + '])) by (destination_workload, source_workload, le))'
    results = prometheus_query(prom_url, query)

    # Add all values to Dataframe
    for result in results:
        # logger.info(result)
        dest_svc = result['metric']['destination_workload']
        src_svc = result['metric']['source_workload']
        name = "latency_" + src_svc + '_' + dest_svc
        values = result['value']
        if src_svc == 'unknown' or dest_svc == 'unknown':
            logger.debug("Skipped unknown")
            continue
        if src_svc in config["services_skipped"] or dest_svc in config["services_skipped"]:
            logger.debug(f"Skipped {name}")
            continue

        if 'timestamp' not in latency_df:
            timestamp = values[0]
            latency_df['timestamp'] = pd.Series(timestamp)
            latency_df['timestamp'] = latency_df['timestamp'].astype('datetime64[s]')
        metric = values[1]
        if metric == "NaN":
            metric = np.NaN

        latency_df[name] = float(metric)
        # latency_df[name] = latency_df[name]
    if 'timestamp' in latency_df:
        latency_df.set_index('timestamp')
    return latency_df


def get_request_error_rates(config):
    prom_url = config['prometheus_url']

    request_error_rates = pd.DataFrame()

    query = 'sum(irate(istio_requests_total{destination_service_namespace="' + NAMESPACE + \
            '",response_code!~"200|0|201|207|202"}[' + METRIC_TIME_INTERVAL + \
            '])) by (destination_service_name) / sum(irate(istio_requests_total{destination_service_namespace="' + \
            NAMESPACE + '"}[' + METRIC_TIME_INTERVAL + '])) by (destination_service_name)'
    results = prometheus_query(prom_url, query)
    for result in results:
        # logger.info(result)
        dest_svc = result['metric']['destination_service_name']
        name = "error_" + dest_svc
        error_rate = result['value'][1]
        if dest_svc in config["services_skipped"] or not dest_svc.startswith("edgex"):
            logger.debug(f"Skipped {name}")
            continue

        if error_rate == "NaN":
            error_rate = np.NaN
        request_error_rates[name] = pd.Series(float(error_rate))
    return request_error_rates


def get_container_cpu_usages(prom_url):
    query = 'sum(irate(container_cpu_usage_seconds_total{namespace="%s", container!~\'POD|istio-proxy|\'}[%s])) ' \
            'BY(container) * 100' % (NAMESPACE, METRIC_TIME_INTERVAL)
    results = prometheus_query(prom_url, query)
    usage_by_container = convert_to_usage_by_container(results)
    return usage_by_container


def get_container_availabilities(prom_url):
    query = 'avg_over_time((sum without() (up{namespace="%s"}) or ' \
            '(0 * sum_over_time(up{namespace="edgex"}[%s])))[%s:5s])' \
            % (NAMESPACE, METRIC_TIME_INTERVAL, METRIC_TIME_INTERVAL)
    results = prometheus_query(prom_url, query)
    availability_by_container = convert_to_availability_by_container(results)
    return availability_by_container


def get_container_memory_usages(prom_url):
    query = 'sum(container_memory_working_set_bytes{namespace="%s", container!~\'POD|istio-proxy|\'}) ' \
            'BY(container) / 1000000' % NAMESPACE
    results = prometheus_query(prom_url, query)
    usage_by_container = convert_to_usage_by_container(results)
    return usage_by_container


def get_metric_services(config):
    prom_url = config['prometheus_url']

    aggregated_results = {}
    container_availabilities = get_container_availabilities(prom_url)
    container_cpu_usages = get_container_cpu_usages(prom_url)
    container_memory_usages = get_container_memory_usages(prom_url)
    container_names = container_cpu_usages.keys() | container_memory_usages.keys() | container_availabilities.keys()
    for container_name in container_names:
        container_usage = {}
        if container_name in config["services_skipped"]:
            continue
        if container_name in container_availabilities:
            container_usage['availability'] = float(container_availabilities[container_name])
        else:
            container_usage['availability'] = np.NaN
        if container_name in container_cpu_usages:
            container_usage['cpu'] = float(container_cpu_usages[container_name])
        else:
            container_usage['cpu'] = np.NaN
        if container_name in container_memory_usages:
            container_usage['memory'] = float(container_memory_usages[container_name])
        else:
            container_usage['memory'] = np.NaN
        aggregated_results[container_name] = container_usage
    return aggregated_results


def ctn_network(prom_url, pod):
    query = 'sum(rate(container_network_transmit_packets_total{namespace="' + NAMESPACE + \
            '", pod="%s"}[' + METRIC_TIME_INTERVAL + \
            '])) / 1000 * sum(rate(container_network_transmit_packets_total{namespace="' + \
            NAMESPACE + '", pod="%s"}[' + METRIC_TIME_INTERVAL + '])) / 1000'
    query = query % (pod, pod)
    results = prometheus_query(prom_url, query)

    values = results[0]['value']
    # logger.info(values)

    metric = pd.Series(values[1])
    return metric


def node_network(prom_url, instance):
    query = 'rate(node_network_transmit_packets_total{device="enp0s3", instance="%s"}[%s]) / 1000' % (
        instance, METRIC_TIME_INTERVAL)
    results = prometheus_query(prom_url, query)

    values = results[0]['value']

    return pd.Series(values[1])


def node_cpu(prom_url, instance):
    query = 'sum(rate(node_cpu_seconds_total{mode != "idle",  mode!= "iowait", mode!~"^(?:guest.*)$", ' \
            'instance="%s" }[%s])) / count(node_cpu_seconds_total{mode="system",' \
            ' instance="%s"})' % (instance, METRIC_TIME_INTERVAL, instance)
    results = prometheus_query(prom_url, query)

    values = results[0]['value']

    return pd.Series(values[1])


def node_memory(prom_url, instance):
    query = '1 - sum(node_memory_MemAvailable_bytes{instance="%s"}) / sum(node_memory_MemTotal_bytes{instance="%s"})' % (
        instance, instance)
    results = prometheus_query(prom_url, query)

    values = results[0]['value']

    return pd.Series(values[0])


# add connection to dataframe and graph
def mpg_add_connection(df, dg, results):
    for result in results:
        metric = result['metric']
        rate_value = float(result['value'][1])
        source = metric['source_workload']
        destination = metric['destination_workload']
        if not rate_value > 0:
            logger.warning(f"{source} -> {destination} traffic rate is {rate_value}. Skipping...")
        elif source != 'unknown' and destination != 'unknown':
            # df = df.append({'source': source, 'destination': destination}, ignore_index=True)
            df = pd.concat([df, pd.DataFrame.from_records([{'source': source, 'destination': destination}])],
                           ignore_index=True)
            dg.add_edge(source, destination)
            dg.nodes[source]['type'] = 'service'
            dg.nodes[destination]['type'] = 'service'
        else:
            logger.warning(f"Unknown source({source}) or destination({destination}) is detected. Skipping...")
    return dg, df


# Create Graph
def get_service_graph(prom_url):
    dg = nx.DiGraph()
    df = pd.DataFrame(columns=['source', 'destination'])
    response = session.get(prom_url + "/api/v1/query",
                           params={
                               'query': 'sum(rate(istio_tcp_received_bytes_total[' + METRIC_TIME_INTERVAL +
                                        '])) by (source_workload, destination_workload)'
                           }, timeout=5)
    results1 = response.json()['data']['result']
    dg, df = mpg_add_connection(df, dg, results1)

    response = session.get(prom_url + "/api/v1/query",
                           params={
                               'query': 'sum(rate(istio_requests_total{destination_workload_namespace="' + NAMESPACE +
                                        '"}[' + METRIC_TIME_INTERVAL + '])) by (source_workload, destination_workload)'
                           }, timeout=5)
    results = response.json()['data']['result']

    dg, df = mpg_add_connection(df, dg, results)

    options = {
        'node_size': 9000,
        'node_shape': 'H',
        'node_color': '#00ffff',
        'width': 1,
        'arrowstyle': '-|>',
        'arrowsize': 18,
        "font_size": 36,
        "edgecolors": 'black'
    }
    dg.add_edge("edgex-exporter-fledge", "edgex-redis")
    dg.add_edge("edgex-device-rest", "edgex-core-data")
    dg.add_edge("edgex-core-metadata", "edgex-device-rest")
    # dg.remove_node("edgex-core-consul")
    mapping = {old_label: old_label.replace("edgex-", "") for old_label in dg.nodes()}
    renamed_graph = nx.relabel_nodes(dg, mapping)
    pos = nx.circular_layout(renamed_graph)
    nx.draw_networkx(renamed_graph, pos=pos, arrows=True, **options)
    # nx.draw_networkx(renamed_graph, arrows=True, **options)
    # plt.show()

    filename = 'current_links_mpg.csv'
    # df.set_index('timestamp')
    df.to_csv(filename)
    return dg
