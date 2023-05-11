#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
import random
import time

import pandas as pd
import requests
import yaml

from chaos_mesh_utils import get_chaos_experiments, add_chaos_mesh_experiment_delay, \
    add_chaos_mesh_experiment_cpu, add_chaos_mesh_experiment_failure, add_chaos_mesh_experiment_memory
from data_manipulation import fill_empty_cells_with_ground_truth_data
from lasm_utils import send_metrics
from metric import get_response_times, get_request_error_rates, get_metric_services

# MAX_NUMBER_OF_CONCURRENT_FAULT_INJECTIONS = 1

available_experiments = ["delay", "cpu", "memory", "failure"]
experiment_methods = [add_chaos_mesh_experiment_delay, add_chaos_mesh_experiment_cpu,
                      add_chaos_mesh_experiment_memory, add_chaos_mesh_experiment_failure]
# kubectl get nodes -o wide | awk -F ' ' '{print $1 " : " $6":9100"}'

FAULT_STATUS = {"delay": 1, "cpu": 2, "memory": 3, "failure": 4}
LOG_LEVEL = "INFO"
TIME_FORMAT = '%H:%M:%S'
LOGGING_FORMAT = "%(asctime)s.%(msecs)03d-> %(message)s"

len_second = 60
logger = logging.getLogger(__name__)
session = requests.Session()


def parse_args():
    """Parse the args."""
    parser = argparse.ArgumentParser(
        description='Root cause analysis for microservices')

    parser.add_argument('--folder', type=str, required=False,
                        default='1',
                        help='folder name to store csv file')

    parser.add_argument('--length', type=int, required=False,
                        default=150,
                        help='length of time series')
    return parser.parse_args()


def get_metrics(config):
    latency_df_source = get_response_times(config)
    request_error_rates = get_request_error_rates(config)
    service_dict_temp = get_metric_services(config)

    return latency_df_source, service_dict_temp, request_error_rates


def wait_rest_of_interval_time(start_time, interval_time):
    end_time = time.time()
    if end_time < start_time + interval_time:
        time.sleep(start_time + interval_time - end_time)


def store_metrics_to_files(dataframe_to_save, training_data_filename):
    dataframe_to_save.to_csv(training_data_filename)
    # dataframe_to_save.to_html(f'{training_data_filename}.html')


def get_step_data(config, services_with_anomaly):
    latency_df_source, service_dict_temp, request_error_rates = get_metrics(config)
    service_metrics_frame = pd.DataFrame()
    service_dict = {}

    for service_name, service_metrics in service_dict_temp.items():
        if service_name in service_dict:
            service_dict[service_name] = pd.concat([service_dict[service_name], service_metrics], ignore_index=True)
        else:
            service_dict[service_name] = service_metrics
        for metric_name, metric in service_metrics.items():
            service_abnormality = services_with_anomaly[service_name] if service_name in services_with_anomaly else 0
            service_metrics_frame[service_name] = service_abnormality
            service_metrics_frame[metric_name + "_" + service_name] = pd.Series(metric)
    row_dataframe = pd.concat([latency_df_source, service_metrics_frame, request_error_rates], axis=1)
    return row_dataframe


def loop_retrieve_training_step(config):
    initialization_start_time = time.strftime("%Y%m%d-%H%M%S")
    training_data_filename = f"dataset/training_data_{initialization_start_time}.csv"
    number_of_training_data = config['number_of_training_data']
    number_of_initial_steps = config['number_of_initial_steps']
    step_interval = config['step_interval']
    columns_to_skip = []
    mean_ground_truth_values = {}
    all_dataframe = pd.DataFrame()
    event_counter = 0
    step_no = 0
    while True:
        try:
            logger.info(f"Starting step #{step_no}")
            row_dataframe, event_counter = retrieve_training_step(config, step_no, event_counter)
            step_start_time = time.time()
            processed_dataframe = row_dataframe.drop(
                columns=set(columns_to_skip).intersection(set(row_dataframe.columns)))

            all_dataframe = pd.concat([all_dataframe, processed_dataframe], ignore_index=True)

            if step_no + 1 > number_of_initial_steps:
                # Print anomaly detections during fault injections
                # anomaly_states_by_metric, clustering_instances, sort_indices, normalization_factors = birch_ad(all_dataframe)
                # abnormal_metrics = []
                # for metric, discrete_metric_values in anomaly_states_by_metric.items():
                #     if discrete_metric_values[-1] not in discrete_metric_values[:config["number_of_initial_steps"]]:
                #         abnormal_metrics.append(metric)
                # logger.info(f"Anomalies:\n {abnormal_metrics}")
                # if abnormal_metrics:
                #     logger.info(all_dataframe[abnormal_metrics])
                pass
            elif step_no + 1 == number_of_initial_steps:
                logger.info("Initial ground truth data is collected.")
                for column in all_dataframe.columns.copy():
                    if len(pd.unique(all_dataframe[column])) == 1 and pd.isnull(all_dataframe[column][0]):
                        # Remove columns only with null value
                        columns_to_skip.append(column)
                        all_dataframe.pop(column)
                    elif column != "timestamp":
                        column_mean_value = all_dataframe[column].mean()
                        mean_ground_truth_values[column] = column_mean_value
                        # all_dataframe[column].fillna(column_mean_value, inplace=True)
                # logger.info("Columns with only NaN values are removed and NaN values are filled with mean.")
                logger.info("Columns with only NaN values are removed.")
            store_metrics_to_files(all_dataframe, training_data_filename)
            last_metrics = all_dataframe.iloc[-1].copy()
            fill_empty_cells_with_ground_truth_data(last_metrics, mean_ground_truth_values)
            last_metrics["timestamp"] = last_metrics["timestamp"].strftime('%Y-%m-%d %H:%M:%S')
            send_metrics(last_metrics, config['lasm_server_urls'], config['reporting_identifier'])
            wait_rest_of_interval_time(step_start_time, step_interval)
            step_no += 1
            if step_no >= number_of_training_data:
                logger.info(f"Completing data collection after step #{step_no}")
                config["training_data"] = [training_data_filename]
                break
        except Exception:
            logger.exception("Error during loop_retrieve_training_step")


def retrieve_training_step(config, step_no, event_counter):
    number_of_initial_steps = config['number_of_initial_steps']
    services_with_anomaly = {}
    if step_no < number_of_initial_steps:
        logger.info(f"Initialization step #{step_no}")
    else:
        active_experiments = get_chaos_experiments()
        if active_experiments:
            time.sleep(5)
            logger.info(f"There are active experiments:{active_experiments}")
            return retrieve_training_step(config, step_no, event_counter)
        # else:
        # number_of_concurrent_injections = random.randint(1, MAX_NUMBER_OF_CONCURRENT_FAULT_INJECTIONS)
        # selected_services = random.sample(SERVICES_FOR_FAULT_INJECTION, number_of_concurrent_injections)
        experiment_step_no = step_no - config["number_of_initial_steps"]
        selected_service_index = experiment_step_no % len(config["services_for_fault_injection"])
        selected_service_indices = [selected_service_index]
        for i in range(config["number_of_concurrent_faults"] - 1):
            selected_next_service_index = selected_service_index
            while selected_next_service_index in selected_service_indices:
                selected_next_service_index = random.randint(0, len(config["services_for_fault_injection"]) - 1)
            selected_service_indices.append(selected_next_service_index)
        services_with_anomaly = {}
        selected_services = [config["services_for_fault_injection"][i] for i in selected_service_indices]

        for service_index, selected_service in enumerate(selected_services):
            if service_index == 0:
                # First experiment periodically changes
                # so every service-fault type combination is applied at least once.
                selected_experiment_index = int((experiment_step_no / len(
                    config["services_for_fault_injection"])) + selected_service_index) % len(available_experiments)
            else:
                # Additional experiments are randomized.
                selected_experiment_index = random.randint(0, len(available_experiments) - 1)
            event_counter += 1
            experiment_methods[FAULT_STATUS[available_experiments[selected_experiment_index]] - 1](selected_service,
                                                                                                   event_counter)
            services_with_anomaly[selected_service] = FAULT_STATUS[available_experiments[selected_experiment_index]]
        logger.info(f"Anomaly selection for experiment step #{experiment_step_no}: {services_with_anomaly}")
        time.sleep(60)
    row_dataframe = get_step_data(config, services_with_anomaly)
    return row_dataframe, event_counter


if __name__ == '__main__':
    args = parse_args()
    logging.basicConfig(level=getattr(logging, LOG_LEVEL),
                        format=LOGGING_FORMAT, datefmt=TIME_FORMAT)
    folder = args.folder
    len_second = args.length

    with open('config.yaml') as f:
        config_from_yaml = yaml.load(f, Loader=yaml.FullLoader)
    experiments = get_chaos_experiments(wait_after_archived_experiments=False)
    if experiments:
        logger.error("Please archive all the active chaos mesh experiments")
        # sys.exit(1)
    loop_retrieve_training_step(config_from_yaml)
