import datetime
import glob
import json
import logging
import pickle
import random
from enum import Enum
from statistics import mean, stdev

import numpy as np
import pandas as pd

import config as c

PRECISION_LEVELS = [1, 2, 3, 4]
SKIPPED_DATASETS = []

# RESULT_FOLDERS = ["results_dual", "results_v2"]
# RESULT_FOLDERS = ["results_dual"]
RESULT_FOLDERS = ["results_v3"]
# RESULT_FOLDERS = ["results_with_4_services"]
logger = logging.getLogger(__name__)
DECISION_THRESHOLD = 0.184
EXPERIMENT_NAMES = {
    1: "delay",
    2: "cpu",
    3: "memory",
    4: "availability"
}


class State(Enum):
    TRUE_POSITIVE = 0
    TRUE_NEGATIVE = 1
    FALSE_POSITIVE = 2
    FALSE_NEGATIVE = 3


def read_json_from_file(filename):
    with open(filename, "r") as outfile:
        return json.load(outfile)


def check_dataset_skipped(file_path):
    for skipped_dataset in SKIPPED_DATASETS:
        if skipped_dataset in file_path:
            return True


def get_results():
    all_results = []
    for result_folder in RESULT_FOLDERS:
        list_of_files = glob.glob(result_folder + "/*")
        for file_path in list_of_files:
            data_set_results = read_json_from_file(file_path)
            if len(data_set_results['test_results']) < 48:
                logger.info(f"Number of incidents in this file {file_path}: {len(data_set_results['test_results'])}")
            if check_dataset_skipped(file_path):
                logger.info(f"Skipping this dataset: {file_path}")
                continue
            all_results.append(data_set_results)
    return all_results


def get_training_time(all_results):
    training_completion_times = []
    for dataset_result in all_results:
        training_completion_times.append(dataset_result['training_completion_time'])
    logger.info(f"Training times: {training_completion_times}")
    logger.info(f"Average training time: {mean(training_completion_times):.2f} seconds with "
                f"std: {stdev(training_completion_times):.2f} for {len(training_completion_times)} datasets")
    return training_completion_times


def get_rca_time(incidents):
    rca_durations = []
    training_completion_times = []
    for incident in incidents:
        analysis_start_time = datetime.datetime.strptime(incident['analysis_start_time'], "%m/%d/%Y %H:%M:%S")
        root_cause_analysis_time = datetime.datetime.strptime(incident['root_cause_analysis_time'],
                                                              "%m/%d/%Y %H:%M:%S")
        rca_duration = root_cause_analysis_time - analysis_start_time
        rca_durations.append(rca_duration.seconds)
    logger.info(f"RCA times: {rca_durations}")
    logger.info(f"Average RCA time: {mean(rca_durations):.2f} seconds with std: {stdev(rca_durations):.2f}")
    return rca_durations


def calculate_optimal_threshold_value(incident_case_detection_confidences, no_incident_case_detection_confidences):
    threshold_value = 0
    best_threshold_value = 0
    best_score = 0
    incident_case_detection_confidences = np.array(incident_case_detection_confidences)
    no_incident_case_detection_confidences = np.array(no_incident_case_detection_confidences)
    while threshold_value < 1:
        threshold_value += 0.001
        score = sum(no_incident_case_detection_confidences < threshold_value) + sum(
            incident_case_detection_confidences > threshold_value)
        if score >= best_score:
            best_score = score
            best_threshold_value = threshold_value
    true_positive_count = sum(incident_case_detection_confidences > best_threshold_value)
    true_negative_count = sum(no_incident_case_detection_confidences < best_threshold_value)
    false_positive_count = len(no_incident_case_detection_confidences) - true_negative_count
    false_negative_count = len(incident_case_detection_confidences) - true_positive_count
    score_details = f"TP={true_positive_count}\tTN={true_negative_count}\t" \
                    f"FP={false_positive_count}\tFN={false_negative_count}"
    logger.info(f"The best threshold value= {best_threshold_value:.3f} with score {best_score}\n{score_details}")

    return best_threshold_value, best_score


def get_ml_metrics(incidents, decision_threshold=DECISION_THRESHOLD, calculate_threshold=False):
    actual_incidents = []
    actual_no_incidents = []
    incident_case_detection_confidences = []
    no_incident_case_detection_confidences = []

    for incident in incidents:
        is_it_actually_incident = len(incident['actual_results']) > 0
        predicted_services = [prediction['service_name'] for prediction in incident["predictions"] if
                              prediction['probability'] >= decision_threshold]
        actual_services = incident['actual_results']
        is_flagged_as_incident = len(predicted_services) > 0
        if is_it_actually_incident:
            are_actual_services_at_top = set(actual_services).issubset(predicted_services[:len(actual_services) + 1])
            actual_incidents.append(are_actual_services_at_top)
            actual_service_probabilities = [prediction['probability'] for prediction in incident["predictions"] if
                                            prediction['service_name'] in actual_services]
            incident_case_detection_confidences.append(min(actual_service_probabilities))
        else:
            actual_no_incidents.append(not is_flagged_as_incident)
            highest_incident_probability = max([prediction['probability'] for prediction in incident["predictions"]])
            no_incident_case_detection_confidences.append(highest_incident_probability)
    true_positive_count = actual_incidents.count(True)
    true_negative_count = actual_no_incidents.count(True)
    false_positive_count = actual_no_incidents.count(False)
    false_negative_count = actual_incidents.count(False)

    accuracy = (true_positive_count + true_negative_count) / len(incidents)
    actual_incidents_len = len(actual_incidents)
    if actual_incidents_len == 0:
        actual_incidents_len = 1

    actual_no_incidents_len = len(actual_no_incidents)
    if actual_no_incidents_len == 0:
        actual_no_incidents_len = 1

    recall = true_positive_count / actual_incidents_len
    fpr = false_positive_count / actual_no_incidents_len
    fnr = false_negative_count / actual_incidents_len
    logger.debug(f"\nAccuracy = {accuracy:.3f}\nRecall = {recall:.3f}")
    results = {"accuracy": accuracy, "recall": recall, "fpr": fpr, "fnr": fnr}
    if calculate_threshold:
        best_threshold_value, best_score = calculate_optimal_threshold_value(incident_case_detection_confidences,
                                                                             no_incident_case_detection_confidences)
        results["best_threshold_value"] = best_threshold_value
    return results


def get_ml_metrics_per_service(incidents, service_names, decision_threshold=DECISION_THRESHOLD):
    global_accuracy_and_recall = get_ml_metrics(incidents, decision_threshold)
    accuracy_results = {"All": global_accuracy_and_recall["accuracy"]}
    recall_results = {"All": global_accuracy_and_recall["recall"]}
    fpr_results = {"All": global_accuracy_and_recall["fpr"]}
    fnr_results = {"All": global_accuracy_and_recall["fnr"]}
    for service_name in service_names:
        filtered_incidents = filter_incidents_by_service(incidents, service_name)
        if not filtered_incidents:
            continue
        service_accuracy = get_ml_metrics(filtered_incidents, decision_threshold)
        accuracy_results[service_name.replace("edgex_", "")] = service_accuracy["accuracy"]
        recall_results[service_name.replace("edgex_", "")] = service_accuracy["recall"]
        fpr_results[service_name.replace("edgex_", "")] = service_accuracy["fpr"]
        fnr_results[service_name.replace("edgex_", "")] = service_accuracy["fnr"]
    return accuracy_results, recall_results, fpr_results, fnr_results


def print_latex_table(results, columns=None):
    df = pd.DataFrame(data=results, columns=columns)
    logger.info(f"\n{df.to_string()}")
    df = df.style.format(precision=3)
    latex_string = df.to_latex().replace('\\\\', '\\\\\hline').replace('_', '\\_')
    logger.info(f"\n{latex_string}")


def get_kpis(incidents, decision_threshold=DECISION_THRESHOLD):
    results_accuracy = {}
    results_hit_rate = {}
    inverse_of_rank_score = {}
    miss_counter = 0
    hit_rate_data = {}
    inverse_of_rank_data = {}
    fault_type_precision_data = {}
    all_fault_type_precision_data = []
    # results["FNR"] = None

    for precision_level in PRECISION_LEVELS:
        hit_rate_data[precision_level] = {}

    for incident in incidents:
        predictions = [prediction for prediction in incident["predictions"] if
                       prediction['probability'] >= decision_threshold]
        predicted_services = [prediction['service_name'] for prediction in predictions]
        is_it_actually_incident = len(incident['actual_results']) > 0
        actual_failed_services = list(incident['actual_results'].keys())
        if is_it_actually_incident and predicted_services:
            logger.debug("It is true positive.")
            if len(actual_failed_services) < len(predictions):
                miss_counter += 1
        elif not is_it_actually_incident and not predicted_services:
            logger.debug("It is true negative.")
            continue
        elif is_it_actually_incident and not predicted_services:
            logger.debug(f"It is false negative. Actual incidents on {incident['actual_results']}")
            miss_counter += 1
        else:
            logger.debug(f"It is false positive, predicted services: {predicted_services}")
            # actual_failed_services = ["FalsePositive"]
            continue
        for precision_level in PRECISION_LEVELS:
            if len(actual_failed_services) > 1:
                actual_failed_service = "Multiple"
            else:
                actual_failed_service = actual_failed_services[0]
            if actual_failed_service not in hit_rate_data[precision_level]:
                hit_rate_data[precision_level][actual_failed_service] = []
                inverse_of_rank_data[actual_failed_service] = []

            are_services_hit = set(actual_failed_services).issubset(predicted_services[:precision_level])
            ranks = []
            for service in actual_failed_services:
                if service in predicted_services:
                    rank = predicted_services.index(service) + 1
                else:
                    rank = np.inf
                ranks.append(rank)
            inverse_of_rank_sum = 1 / ((sum(ranks) - len(ranks) + 1) / len(ranks))
            hit_rate_data[precision_level][actual_failed_service].append(are_services_hit)
            inverse_of_rank_data[actual_failed_service].append(inverse_of_rank_sum)
            # service_precision_data[precision_level][actual_failed_service].append(
            #     actual_failed_service in predicted_services[:precision_level])
        for actual_failed_service in actual_failed_services:
            if actual_failed_service not in fault_type_precision_data:
                fault_type_precision_data[actual_failed_service] = []

        are_actual_services_predicted = set(actual_failed_services).issubset(
            predicted_services[:len(actual_failed_services) + 1])
        if predictions and are_actual_services_predicted:
            correct_service_predictions = [prediction for prediction in incident["predictions"] if
                                           prediction['service_name'] in actual_failed_services]
            for prediction in correct_service_predictions:
                actual_failed_service_type = incident['actual_results'][prediction['service_name']]
                fault_distribution = prediction['fault_distribution']
                if str(actual_failed_service_type) not in fault_distribution:
                    is_fault_type_predicted_right = False
                    logger.warning(f"Fault type {actual_failed_service_type} not in "
                                   f"node {prediction['service_name']} states!")
                else:
                    fault_distribution = sorted(fault_distribution, key=fault_distribution.get, reverse=True)
                    first_prediction_fault_type = fault_distribution[0]
                    is_fault_type_predicted_right = int(first_prediction_fault_type) == int(actual_failed_service_type)

                fault_type_precision_data[prediction['service_name']].append(is_fault_type_predicted_right)
                all_fault_type_precision_data.append(is_fault_type_predicted_right)

    for precision_level in PRECISION_LEVELS:
        all_service_precision_data = []
        all_inverse_of_rank_data = []
        results_hit_rate[f"HR@{precision_level}"] = {}
        for service_name, values in hit_rate_data[precision_level].items():
            if not values:
                continue
            shortened_service_name = service_name.replace("edgex_", "")
            results_hit_rate[f"HR@{precision_level}"][shortened_service_name] = mean(values)
            all_service_precision_data.extend(values)
            inverse_of_rank_score[shortened_service_name] = mean(inverse_of_rank_data[service_name])
            all_inverse_of_rank_data.extend(inverse_of_rank_data[service_name])
        #results_hit_rate[f"HR@{precision_level}"]["All"] = mean(all_service_precision_data)
        mean_all = 0
        if len(all_inverse_of_rank_data) > 0:
            mean_all = mean(all_inverse_of_rank_data)
        inverse_of_rank_score["All"] = mean_all

    results_accuracy["Fault type recall"] = {}
    for service_name, values in fault_type_precision_data.items():
        if not values:
            continue
        service_name = service_name.replace("edgex_", "")
        results_accuracy["Fault type recall"][service_name] = mean(values)
    service_names = fault_type_precision_data.keys()
    accuracy_results, recall_results, fpr_results, fnr_results = get_ml_metrics_per_service(incidents, service_names,
                                                                                            decision_threshold)
    results_accuracy["Accuracy"] = accuracy_results
    results_accuracy["Recall"] = recall_results
    results_accuracy["FPR"] = fpr_results
    # results["FNR"] = fnr_results
    average_fault_type_precision_data = mean(all_fault_type_precision_data) if all_fault_type_precision_data else 0
    results_accuracy["Fault type recall"]["All"] = average_fault_type_precision_data

    return {"results_accuracy": results_accuracy, "results_hit_rate": results_hit_rate, "miss_counter": miss_counter,
            "inverse_of_rank": inverse_of_rank_score}


def get_incidents(dataset_results):
    incidents = []
    for dataset_result in dataset_results:
        incidents.extend(dataset_result['test_results'])
    logger.info(f"Total number of incidents: {len(incidents)}")
    return incidents


def add_no_incidents(incidents, no_incident_cases):
    if len(incidents) < len(no_incident_cases):
        no_incident_cases_to_add = random.sample(no_incident_cases, len(incidents))
    else:
        no_incident_cases_to_add = no_incident_cases
    merged_incidents = [None] * (len(incidents) + len(no_incident_cases_to_add))
    merged_incidents[::2] = incidents
    merged_incidents[1::2] = no_incident_cases_to_add
    return merged_incidents


def filter_incidents_by_fault(incidents, service_state=0):
    filtered_incidents = []
    no_incident_cases = []
    for incident in incidents:
        if incident['actual_results']:
            experiment_type = list(incident['actual_results'].values())[0]
            if experiment_type == service_state:
                filtered_incidents.append(incident)
        else:
            no_incident_cases.append(incident)
    logger.info(f"Total number of filtered incidents: {len(filtered_incidents)}")
    if service_state == 0:
        filtered_incidents = no_incident_cases
    else:
        filtered_incidents = add_no_incidents(filtered_incidents, no_incident_cases)

    return filtered_incidents


def filter_incidents_by_service(incidents, service_name):
    filtered_incidents = []
    no_incident_cases = []
    for incident in incidents:
        faulty_services = incident["actual_results"].keys()
        if service_name in faulty_services:
            filtered_incidents.append(incident)
        elif not faulty_services:
            no_incident_cases.append(incident)
    logger.debug(f"Total number of incidents on {service_name}: {len(filtered_incidents)}")
    filtered_incidents = add_no_incidents(filtered_incidents, no_incident_cases)
    return filtered_incidents


def chunks(xs, n):
    n = max(1, n)
    return (xs[i:i + n] for i in range(0, len(xs), n))


def update_aggregated_result(aggregated_results, new_results, part_index):
    for kpi, rates in new_results.items():
        for service_name, value in rates.items():
            agg_value = 0
            if aggregated_results[kpi].keys().__contains__(service_name):
                agg_value = aggregated_results[kpi][service_name]
            new_value = (part_index * agg_value + value) / (
                    part_index + 1)
            aggregated_results[kpi][service_name] = new_value


def print_kpis_based_on_chunk_threshold_calculation(incidents, available_thresholds=None):
    results_accuracy_aggregated = {}
    results_hit_rate_aggregated = {}
    miss_counter = 0
    incident_chunks = list(chunks(incidents, int(len(incidents) / 5)))[:5]
    if available_thresholds is None:
        available_thresholds = [-1] * len(incident_chunks)
    for chunk_index, incident_chunk in enumerate(incident_chunks):
        if available_thresholds[chunk_index] < 0:
            incidents_for_threshold_calculation = incident_chunks[(chunk_index - 1) % len(incident_chunks)]
            ml_metrics = get_ml_metrics(incidents_for_threshold_calculation, calculate_threshold=True)
            available_thresholds[chunk_index] = ml_metrics["best_threshold_value"]
        results_partial = get_kpis(incident_chunk, decision_threshold=available_thresholds[chunk_index])
        if not results_hit_rate_aggregated:
            results_hit_rate_aggregated = results_partial["results_hit_rate"]
            results_hit_rate_aggregated["MRR"] = results_partial['inverse_of_rank']
            results_accuracy_aggregated = results_partial["results_accuracy"]
            miss_counter = results_partial["miss_counter"]
        else:
            logger.info("hej")
            update_aggregated_result(results_hit_rate_aggregated, results_partial["results_hit_rate"], chunk_index)
            update_aggregated_result(results_hit_rate_aggregated, {"MRR": results_partial["inverse_of_rank"]},
                                     chunk_index)
            update_aggregated_result(results_accuracy_aggregated, results_partial["results_accuracy"], chunk_index)
    print_latex_table(results_accuracy_aggregated, ["Accuracy", "Recall", "FPR", "Fault type recall"])
    print_latex_table(results_hit_rate_aggregated)
    return available_thresholds, miss_counter


def get_mrr_for_different_threshold_values(incidents):
    mrr_results = {}
    for threshold in np.arange(0, 1.00, 0.01):
        results = get_kpis(incidents, decision_threshold=threshold)
        mrr_results[f"{threshold:.2f}"] = results['inverse_of_rank']["All"]
    return mrr_results


def get_accuracy_for_different_threshold_values(incidents):
    accuracy_results = {}
    for threshold in np.arange(0, 1.00, 0.01):
        results = get_kpis(incidents, decision_threshold=threshold)
        accuracy_results[f"{threshold:.2f}"] = results['results_accuracy']['Accuracy']["All"]
    return accuracy_results


def save_data_to_file(data, filename):
    logger.info(f"Saving data to {filename}")
    with open(filename, "wb+") as sm_file:
        pickle.dump(data, sm_file)


if __name__ == '__main__':
    logging.basicConfig(level=getattr(logging, c.LOG_LEVEL),
                        format=c.LOGGING_FORMAT, datefmt=c.TIME_FORMAT)
    all_dataset_results = get_results()
    training_times = get_training_time(all_dataset_results)
    all_incidents = get_incidents(all_dataset_results)
    mrr_by_threshold = get_mrr_for_different_threshold_values(all_incidents)
    save_data_to_file(mrr_by_threshold, f"mrr_results/{'_'.join(RESULT_FOLDERS)}")
    accuracy_by_threshold = get_accuracy_for_different_threshold_values(all_incidents)
    save_data_to_file(accuracy_by_threshold, f"accuracy_results/{'_'.join(RESULT_FOLDERS)}")
    rca_times = get_rca_time(all_incidents)
    save_data_to_file({"rca_times":rca_times,"training_times":training_times}, f"scalability_results/{'_'.join(RESULT_FOLDERS)}")

    general_thresholds, miss_counter_for_hit = print_kpis_based_on_chunk_threshold_calculation(all_incidents)
    logger.info(f"Thresholds:{general_thresholds}")

    no_incidents = filter_incidents_by_fault(all_incidents)
    number_of_incidents = len(all_incidents) - len(no_incidents)
    miss_ratio = miss_counter_for_hit / number_of_incidents
    logger.info(
        f"Miss_counter:{miss_counter_for_hit}|number_of_incidents:{number_of_incidents}|miss_ratio:{miss_ratio}")

    # if no_incidents:
    #     logger.info("No Incident Cases")
    #     get_kpis(no_incidents)

    logger.info("Traffic Related Cases")
    delay_incidents = filter_incidents_by_fault(all_incidents, 1)
    print_kpis_based_on_chunk_threshold_calculation(delay_incidents, general_thresholds)

    logger.info("Performance Related Cases")
    memory_incidents = filter_incidents_by_fault(all_incidents, 3)
    print_kpis_based_on_chunk_threshold_calculation(memory_incidents, general_thresholds)

    logger.info("Reliability Related Cases")
    availability_incidents = filter_incidents_by_fault(all_incidents, 4)
    print_kpis_based_on_chunk_threshold_calculation(availability_incidents, general_thresholds)
