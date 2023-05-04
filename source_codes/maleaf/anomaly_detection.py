import logging

import numpy as np
from sklearn.mixture import BayesianGaussianMixture

BIRCH_AD_THRESHOLD = 0.1  # 0.045
CLUSTER_NUMBER = 3
# BIRCH_AD_THRESHOLD = {"latency": 25, "memory": 100, "cpu": 10}
logger = logging.getLogger(__name__)
np.set_printoptions(precision=2)
np.set_printoptions(suppress=True)


def relabel_cluster_ids_by_value(result_distribution, prediction_results, is_reverse=False):
    first_elements_of_each_cluster = np.empty(len(result_distribution.keys()))
    for cluster_id, cluster_values in result_distribution.items():
        first_elements_of_each_cluster[cluster_id] = cluster_values[0]
    sort_index = np.argsort(first_elements_of_each_cluster)
    if is_reverse:
        sort_index = sort_index[::-1]
    new_prediction_results = np.empty_like(prediction_results)
    for index, value in enumerate(prediction_results):
        new_prediction_results[index] = sort_index[value]
    return new_prediction_results, sort_index


def discretize_with_trained_mode(metric_data, trained_model):
    return discretize_with_given_clustering_instances(metric_data, trained_model.clustering_instances,
                                                      trained_model.sort_indices, trained_model.normalization_factors,
                                                      trained_model.mean_ground_truth_values)


def discretize_with_given_clustering_instances(metric_data, clustering_instances, sort_indices, normalization_factors,
                                               mean_ground_truth_values=[]):
    anomaly_states_by_metric = {}
    for metric, metric_readings in metric_data.iteritems():
        if metric.startswith('edgex'):
            continue
        x = np.array(metric_readings)
        default_metric_value = mean_ground_truth_values[metric] if metric in mean_ground_truth_values else 0
        x = np.where(np.isnan(x), default_metric_value, x)
        if metric not in normalization_factors:
            logger.warning(f"New metric '{metric}' is detected.")
            continue
        x = x / normalization_factors[metric]
        x = x.reshape(x.size, 1)
        prediction_results = clustering_instances[metric].predict(x)
        new_prediction_results = np.empty_like(prediction_results)
        for index, value in enumerate(prediction_results):
            new_prediction_results[index] = sort_indices[metric][value]
        anomaly_states_by_metric[metric.replace('-', '_')] = new_prediction_results
    return anomaly_states_by_metric


def check_multiple_clusters_exists_in_base_data(prediction_results, base_data_size):
    n_clusters = np.unique(prediction_results[:base_data_size]).size
    return n_clusters > 1


def check_multi_clusters_exists(prediction_results):
    n_clusters = np.unique(prediction_results).size
    return n_clusters > 1


def cluster_data(metric, normalized_metric_readings, birch_threshold, base_data_size, no_cluster_found=False,
                 n_components=CLUSTER_NUMBER):
    # brc = Birch(branching_factor=50, n_clusters=CLUSTER_NUMBER, threshold=birch_threshold, compute_labels=True)
    # brc = DBSCAN(eps=0.1, min_samples=5)
    brc = BayesianGaussianMixture(n_components=n_components)
    brc.fit(normalized_metric_readings)
    prediction_results = brc.predict(normalized_metric_readings)
    n_clusters = np.unique(prediction_results).size
    if n_clusters != n_components:
        return cluster_data(metric, normalized_metric_readings, birch_threshold, base_data_size, no_cluster_found=False,
                            n_components=n_clusters)
    # prediction_results = brc.fit_predict(normalized_metric_readings)
    # if check_multiple_clusters_exists_in_base_data(prediction_results, base_data_size) and not no_cluster_found:
    #     new_threshold = birch_threshold * 1.05
    #     logger.debug(
    #         f"Multiple clusters exists in base data. Increasing BIRCH threshold for {metric} to {new_threshold:.4f}")
    #     return cluster_data(metric, normalized_metric_readings, new_threshold, base_data_size)
    # elif not check_multi_clusters_exists(prediction_results):
    #     new_threshold = birch_threshold * 0.95
    #     logger.debug(f"No cluster found. Decreasing BIRCH threshold for {metric} to {new_threshold:.4f}")
    #     return cluster_data(metric, normalized_metric_readings, new_threshold, base_data_size, no_cluster_found=True)
    return brc, prediction_results


def discretize(metric_data, birch_threshold=BIRCH_AD_THRESHOLD, base_data_size=30):
    anomaly_states_by_metric = {}
    clustering_instances = {}
    sort_indices = {}
    normalization_factors = {}
    metrics = list(metric_data.columns)
    metrics.sort()
    for metric in metrics:
        is_reverse = False
        if metric.startswith('availability'):
            is_reverse = True
        metric_readings = metric_data[metric]
        result_distribution = {}
        if metric.startswith('edgex') or metric.startswith('timestamp'):
            continue
        np_metric_readings = np.array(metric_readings)
        if np_metric_readings.max() <= 1 and np_metric_readings.min() >= 0:
            # logger.info(f"No normalization for {metric}")
            normalization_factors[metric] = 1
            np_metric_readings = np_metric_readings.reshape(-1, 1)
        else:
            # np_metric_readings = np.where(np.isnan(np_metric_readings), 0, np_metric_readings)
            normalization_factor = np_metric_readings.mean()
            normalized_metric_readings = np_metric_readings / normalization_factor
            std_deviation = normalized_metric_readings.std()
            birch_threshold = std_deviation if std_deviation > 0 else BIRCH_AD_THRESHOLD
            # normalized_metric_readings = preprocessing.normalize([np_metric_readings], norm="max")
            # if normalized_metric_readings[0, 0] == 0:
            #     nonzero_value_index = next((i for i, x in enumerate(normalized_metric_readings[0, :]) if x), None)
            #     if nonzero_value_index is None:
            #         logger.warning(f"Ignoring {metric} since it is zero")
            #         normalization_factor = 1
            #     else:
            #         logger.info(
            #             f"First nonzero value is at {nonzero_value_index} and "
            #             f"it is {np_metric_readings[nonzero_value_index]}")
            #         normalization_factor = np_metric_readings[nonzero_value_index] / normalized_metric_readings[
            #             0, nonzero_value_index]
            #
            # else:
            #     normalization_factor = np_metric_readings[0] / normalized_metric_readings[0, 0]
            # logger.info(f"Normalization factor is {normalization_factor}")
            # logger.info(f"birch_threshold is {birch_threshold}")
            normalization_factors[metric] = normalization_factor
            np_metric_readings = normalized_metric_readings.reshape(-1, 1)
        # birch_threshold = BIRCH_AD_THRESHOLD[metric.split("_")[0]]
        try:
            brc, prediction_results = cluster_data(metric, np_metric_readings, birch_threshold, base_data_size)
        except:
            pass
        for index, result in enumerate(prediction_results):
            if result in result_distribution:
                result_distribution[result].append(metric_readings[index])
            else:
                result_distribution[result] = [metric_readings[index]]

        n_clusters = np.unique(prediction_results).size
        logger.debug(f"{metric}: size={n_clusters}")
        for cluster_id, cluster_values in result_distribution.items():
            min_value, max_value = (round(min(cluster_values), 2), round(max(cluster_values), 2))
            if min_value == max_value:
                range_text = str(min_value)
            else:
                range_text = f"{min_value},{max_value}"
            rounded_values = [int(round(i, 0)) for i in cluster_values if not np.isnan(i)]
            unique_values = list(set(rounded_values))
            unique_values.sort()
            value_counter = {value: rounded_values.count(value) for value in unique_values}
            # logger.info(
            #     f"{cluster_id}:({range_text}) {[round(i, 2) for i in cluster_values]}")
            logger.debug(
                f"{cluster_id}<{len(cluster_values)}>:({range_text}) {value_counter}")
        prediction_results, sort_index = relabel_cluster_ids_by_value(result_distribution, prediction_results,
                                                                      is_reverse=is_reverse)
        pairs = "\n"
        for i in range(len(metric_readings)):
            pairs += f"{round(float(metric_readings[i]), 2)}|{prediction_results[i]}\t"
            if i % 10 == 9:
                pairs += "\n"
        logger.debug(pairs)
        anomaly_states_by_metric[metric] = prediction_results
        clustering_instances[metric] = brc
        sort_indices[metric] = sort_index
    return anomaly_states_by_metric, clustering_instances, sort_indices, normalization_factors
