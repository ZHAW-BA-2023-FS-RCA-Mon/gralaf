import argparse
import glob
import logging
import math
import re

import pandas as pd
import yaml

from anomaly_detection import discretize
from data_manipulation import remove_columns_with_single_value, filter_data, \
    fill_empty_cells_with_ground_truth_data, remove_columns_with_small_effect, remove_columns_with_unstable_output
from models.trained_model import TrainedModel

# import bnlearn as bn

LOG_LEVEL = "DEBUG"
TIME_FORMAT = '%H:%M:%S'
LOGGING_FORMAT = "%(asctime)s.%(msecs)03d-> %(message)s"
NUMBER_OF_INITIAL_STEPS = 15
logger = logging.getLogger(__name__)


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

    parser.add_argument('--url', type=str, required=False,
                        default='http://localhost:9090/api/v1/query',
                        help='url of prometheus query')

    return parser.parse_args()


def create_dag(training_dataframe):
    from pgmpy.estimators import HillClimbSearch

    training_dataframe = training_dataframe.astype("int32")
    hc = HillClimbSearch(training_dataframe)
    best_model = hc.estimate()
    print(best_model.edges())
    # DAG = bn.structure_learning.fit(training_dataframe.astype("int32"))
    # bn.print_CPD(DAG)
    # bn.plot(DAG, interactive=True)
    # q1 = bn.inference.fit(DAG, variables=['edgex-ui'], evidence={'latency_edgex-ui_edgex-core-command': 1})
    # print(q1.df)


def threshold_based_anomaly_detection(training_dataframe):
    normal_mode_max_values = training_dataframe.iloc[:15, :].max(axis=0)
    normal_mode_min_values = training_dataframe.iloc[:15, :].min(axis=0)
    for column in training_dataframe.columns:
        if not column.startswith("edgex"):
            for row_id, value in training_dataframe[column].items():
                if value < normal_mode_max_values[column] * 1.2:
                    training_dataframe[column][row_id] = 0
                else:
                    training_dataframe[column][row_id] = math.log10(value / normal_mode_max_values[column] + 10)
                    # training_dataframe[column][row_id] = 1


def discretize_data(training_data, birch_instances):
    training_data = clustering_based_anomaly_detection(training_data, birch_instances)
    return training_data


def clustering_based_anomaly_detection(training_dataframe):
    anomaly_states_by_metric, birch_instances, sort_indices, normalization_factors = discretize(training_dataframe)
    for metric, states in anomaly_states_by_metric.items():
        for step_no, state in enumerate(states):
            training_dataframe.loc[step_no, metric] = state
    return training_dataframe.astype("int32")


def get_training_data(training_data_files):
    training_dataframe = pd.DataFrame()
    for file_name in training_data_files:
        single_file_training_dataframe = pd.read_csv(file_name)
        training_dataframe = pd.concat([training_dataframe, single_file_training_dataframe], ignore_index=True)
    training_dataframe = training_dataframe.iloc[:, 1:]
    # training_dataframe = training_dataframe.fillna(0)
    return training_dataframe


def get_latest_simulation_file(folder_path="dataset"):
    list_of_csv_files = glob.glob(f'{folder_path}/*.csv')
    return max(list_of_csv_files)


def train_model(config):
    training_data, dataset_tag = get_raw_data(config)
    training_data = filter_data(config, training_data)
    training_data.pop("timestamp")
    training_data.columns = training_data.columns.str.replace('-', '_')
    training_data, mean_ground_truth_values = fill_empty_cells_with_ground_truth_data(training_data, config[
        "number_of_initial_steps"])
    training_data = remove_columns_with_single_value(training_data)
    anomaly_states_by_metric, clustering_instances, sort_indices, normalization_factors = \
        discretize(training_data, base_data_size=config["number_of_initial_steps"])
    remove_columns_with_small_effect(training_data, anomaly_states_by_metric)
    remove_columns_with_unstable_output(training_data, anomaly_states_by_metric, config["number_of_initial_steps"])
    # new_columns = []
    # for metric, metric_index in sort_indices.items():
    #     if len(metric_index) > 2:
    #         new_columns.extend([f"{metric}_{i + 2}" for i in range(len(metric_index) - 2)])
    # for new_column in new_columns:
    #     training_data[new_column] = 0
    # logger.info(f"Columns generated: {new_columns}")
    for metric, states in anomaly_states_by_metric.items():
        for step_no, state in enumerate(states):
            training_data.loc[step_no, metric] = state
            # if metric.startswith("edgex") or state <= 1:
            #     training_data.loc[step_no, metric] = state
            # else:
            #     for i in range(state):
            #         if i == 0:
            #             training_data.loc[step_no, metric] = 1
            #         else:
            #             training_data.loc[step_no, f"{metric}_{i + 1}"] = 1
    training_data = training_data.astype('int32')
    # training_data = make_service_columns_binary(training_data)
    training_data = remove_columns_with_single_value(training_data)

    logger.info(f"Shape of data: {training_data.shape}")
    trained_model = TrainedModel(config=config, clustering_instances=clustering_instances, sort_indices=sort_indices,
                                 normalization_factors=normalization_factors, training_data=training_data,
                                 mean_ground_truth_values=mean_ground_truth_values, dataset_tag=dataset_tag)
    return trained_model


def get_raw_data(config, is_test_data=False):
    if is_test_data:
        training_data_files = config["test_data"]
        number_of_rows = config["number_of_test_data"]
    else:
        training_data_files = config["training_data"]
        number_of_rows = config["number_of_training_data"]

    if not training_data_files:
        training_data_files = [get_latest_simulation_file()]
    retrieved_dataframe = get_training_data(training_data_files)
    if is_test_data:
        sliced_dataframe = retrieved_dataframe.tail(number_of_rows)
        if config["test_false_positive"]:
            sliced_dataframe = pd.concat(
                [retrieved_dataframe.head(config["number_of_test_false_positive_data"]), sliced_dataframe],
                ignore_index=True)
    else:
        sliced_dataframe = retrieved_dataframe.head(number_of_rows)
    dataset_tag = "_".join([re.sub(r'[^\w\d-]', '_', file_path) for file_path in training_data_files])
    logger.info(f"Dataset tag is {dataset_tag} for {'test' if is_test_data else 'training'}")
    return sliced_dataframe, dataset_tag


def get_final_data(config):
    training_dataframe, dataset_tag = get_raw_data(config)
    training_dataframe = filter_data(config, training_dataframe)
    training_dataframe = clustering_based_anomaly_detection(training_dataframe)

    training_dataframe.columns = training_dataframe.columns.str.replace('-', '_')

    return training_dataframe


if __name__ == '__main__':
    args = parse_args()
    logging.basicConfig(level=getattr(logging, LOG_LEVEL),
                        format=LOGGING_FORMAT, datefmt=TIME_FORMAT)
    folder = args.folder
    len_second = args.length
    prometheus_url = args.url
    faults_name = folder
    with open('config.yaml') as f:
        config_from_yaml = yaml.load(f, Loader=yaml.FullLoader)
    training_dataset = get_final_data(config_from_yaml)
    training_dataset = training_dataset[:-1]

    structure_model = TrainedModel.learn_from_data(config_from_yaml, training_dataset)
    pass
