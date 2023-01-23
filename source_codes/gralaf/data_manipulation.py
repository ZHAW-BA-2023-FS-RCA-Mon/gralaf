import logging

import numpy as np
import pandas as pd
from pandas import Series

logger = logging.getLogger(__name__)
removed_columns = set()


def make_service_columns_binary(training_data):
    services = []
    new_columns = []
    for column_name in training_data.columns:
        if column_name.startswith("edgex"):
            services.append(column_name)
            new_columns.extend(
                [f"{column_name}_delay", f"{column_name}_cpu", f"{column_name}_memory", f"{column_name}_failure"])
    for new_column in new_columns:
        training_data[new_column] = 0
    for service_name in services:
        for index, value in training_data[service_name].items():
            if value == 1:
                training_data.loc[index, f"{service_name}_delay"] = 1
            elif value == 2:
                training_data.loc[index, f"{service_name}_cpu"] = 1
            elif value == 3:
                training_data.loc[index, f"{service_name}_memory"] = 1
            elif value == 4:
                training_data.loc[index, f"{service_name}_failure"] = 1
    training_data = training_data.drop(columns=services)
    return training_data


def remove_columns_with_single_value(given_dataframe):
    columns_to_remove = []
    for column in given_dataframe.columns.copy():
        if len(pd.unique(given_dataframe[column])) <= 1:
            columns_to_remove.append(column)
    if columns_to_remove:
        given_dataframe = given_dataframe.drop(columns=columns_to_remove)
        logger.info(f"These columns are removed since they have single value: {columns_to_remove}")
        removed_columns.update(columns_to_remove)
    return given_dataframe


def remove_columns_with_small_effect(given_dataframe, anomaly_states_by_metric):
    columns_to_remove = []
    for metric, states in anomaly_states_by_metric.items():
        median_value = np.median(states)
        median_occurrence = np.count_nonzero(states == median_value)
        data_size = given_dataframe.shape[0]
        median_ratio = median_occurrence / data_size
        if median_ratio > 0.98:
            columns_to_remove.append(metric)
            logger.info(f"This metric will be removed since it has small effect"
                        f"(Median ratio: {median_ratio:.2f}): {metric}")
    given_dataframe = given_dataframe.drop(columns=columns_to_remove)
    removed_columns.update(columns_to_remove)
    return given_dataframe


def remove_columns_with_unstable_output(given_dataframe, anomaly_states_by_metric, number_of_initial_steps=30):
    columns_to_remove = []
    for metric, states in anomaly_states_by_metric.items():
        median_value = np.median(states[:number_of_initial_steps])
        median_occurrence = np.count_nonzero(states[:number_of_initial_steps] == median_value)
        data_size = states[:number_of_initial_steps].shape[0]
        median_ratio = median_occurrence / data_size
        if median_ratio < 0.7:
            columns_to_remove.append(metric)
            logger.info(f"This metric will be removed since it has unstable output"
                        f"(Median ratio: {median_ratio:.2f}): {metric}")
    given_dataframe = given_dataframe.drop(columns=columns_to_remove)
    removed_columns.update(columns_to_remove)
    return given_dataframe


def remove_previously_deleted_columns(given_row):
    columns_to_remove = []
    for column in given_row.keys():
        if column in removed_columns:
            columns_to_remove.append(column)
    logger.info(f"These columns will be removed since they are removed before: {columns_to_remove}")
    given_row = given_row.drop(columns=columns_to_remove)
    removed_columns.update(columns_to_remove)
    return given_row


def remove_columns_unavailable_on_training_data(given_data, training_data):
    columns_to_remove = []
    if isinstance(given_data, Series):
        given_data_columns = given_data.keys()
    else:
        given_data_columns = given_data.columns
    for column in given_data_columns:
        if column == "timestamp":
            pass
        elif column not in training_data.columns:
            columns_to_remove.append(column)
    logger.info(f"These columns will be removed since they are removed before: {columns_to_remove}")
    given_row = given_data.drop(columns=columns_to_remove)
    return given_row


def filter_data(config, given_dataframe):
    rows_to_remove = []
    columns_to_remove = []
    for service_name in config["services_skipped"]:
        if service_name not in given_dataframe:
            continue
        for index, value in given_dataframe[service_name].items():
            if value != 0:
                rows_to_remove.append(index)
                logger.info(f"Row {index} is related to {service_name}")
    for experiment_type, experiment_status in config["experiments_skipped"].items():
        for service_name in config["services_for_fault_injection"]:
            if service_name not in given_dataframe:
                continue
            for index, value in given_dataframe[service_name].items():
                if value == experiment_status:
                    rows_to_remove.append(index)
                    logger.debug(f"Row {index} is related to experiment type {experiment_type} for {service_name}")

    logger.debug(f"These rows are gonna be removed: {rows_to_remove}")
    rows_to_remove = set(rows_to_remove)
    if rows_to_remove:
        given_dataframe.drop(rows_to_remove, inplace=True)
        given_dataframe.reset_index(inplace=True, drop=True)
    for column in given_dataframe.columns:
        for metric_name in config["metrics_skipped"]:
            if column.startswith(metric_name):
                columns_to_remove.append(column)
                continue
        for service_name in config["services_skipped"]:
            if service_name in column:
                columns_to_remove.append(column)
                break
        if "istio_init" in column:
            columns_to_remove.append(column)
    if columns_to_remove:
        columns_to_remove = set(columns_to_remove)
        given_dataframe = given_dataframe.drop(columns=columns_to_remove)
        logger.info(f"These columns are removed because of skip configurations: {columns_to_remove}")
        removed_columns.update(columns_to_remove)
    return given_dataframe


def fill_empty_cells_with_ground_truth_data(all_dataframe, ground_truth_data_size=30):
    mean_ground_truth_values = {}
    for column in all_dataframe.columns.copy():
        number_of_empty_rows_in_ground_truth = all_dataframe.head(ground_truth_data_size)[column].isna().sum()
        number_of_empty_rows_totally = all_dataframe[column].isna().sum()
        if number_of_empty_rows_in_ground_truth > ground_truth_data_size * 0.7:
            logger.info(
                f"Removing {column} since it has {number_of_empty_rows_in_ground_truth} empty results in ground truth "
                f"and {number_of_empty_rows_totally} in overall")
            removed_columns.add(column)
            all_dataframe.pop(column)
            continue
        if column == "timestamp":
            continue
        column_mean_value = all_dataframe.head(ground_truth_data_size)[column].mean()
        mean_ground_truth_values[column] = column_mean_value
        num_of_empty_cells = all_dataframe[column].isna().sum()
        logger.info(f"Filling {num_of_empty_cells} cells of column {column} with {column_mean_value}")
        all_dataframe[column].fillna(column_mean_value, inplace=True)
    return all_dataframe, mean_ground_truth_values


def filter_columns_by_inference_engine(given_data, inference_engine):
    partial_data = given_data.copy()
    for column in given_data.keys():
        if column not in inference_engine._cpds:
            partial_data.pop(column)
    return partial_data
