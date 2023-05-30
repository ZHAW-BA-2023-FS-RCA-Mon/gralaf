#!/usr/bin/env python3
import argparse
import logging
import pickle
import time

import yaml

from rca import loop_retrieve_training_step, wait_rest_of_interval_time
from data_manipulation import remove_previously_deleted_columns, fill_empty_cells_with_ground_truth_data, \
    remove_columns_unavailable_on_training_data, filter_and_fill_with_ground_truth_data
from generate_model import train_model
from lasm_utils import send_metrics
from models.exception import NewMetricFound
from sla import get_trails, get_service_level_agreements
from test_data import get_test_data_from_live_system, test_stored_data, check_metrics

logger = logging.getLogger(__name__)
sla_data = {}
is_initialization_required = True


def parse_args():
    """Parse the args."""
    parser = argparse.ArgumentParser(
        description='Root cause analysis for microservices')

    parser.add_argument('--config', type=str, required=False,
                        default='config.yaml',
                        help='Location of config file')
    return parser.parse_args()


def read_from_file(file_name="sm.pickle"):
    with open(file_name, "rb") as sm_file:
        return pickle.load(sm_file)


def run(config):
    global sla_data
    step_interval = config['step_interval']
    start_time = time.time()
    trained_model = train_model(config)
    training_end_time = time.time()
    training_completion_time = training_end_time - start_time
    logger.info(f"Training of {config['rca_algorithm']} model completed in {training_completion_time} seconds.")

    while True:
        step_start_time = time.time()
        try:
            trails_data = get_trails(config['trails_server_urls'])
            logger.debug(trails_data)
            sla_data = get_service_level_agreements(trails_data)
            logger.debug(sla_data)
            if config["use_archive"]:
                test_stored_data(config, trained_model, training_completion_time=training_completion_time,
                                 training_dataset_tag=trained_model.dataset_tag, sla_data=sla_data)
                break
            else:
                new_data = get_test_data_from_live_system(config)

                new_step_data = filter_and_fill_with_ground_truth_data(new_data, trained_model.mean_ground_truth_values)
                send_metrics(new_step_data, config['lasm_server_urls'], config['reporting_identifier'])

                new_data.columns = new_data.columns.str.replace('-', '_')
                new_data = remove_columns_unavailable_on_training_data(new_data, trained_model.training_data)
                new_data = new_data.squeeze()
                new_data = remove_previously_deleted_columns(new_data)
                fill_empty_cells_with_ground_truth_data(new_data, trained_model.mean_ground_truth_values)
                check_metrics(config, trained_model, new_data, sla_data=sla_data)
        except Exception as e:
            logging.exception(e)
        logging.debug("Checked system")
        wait_rest_of_interval_time(step_start_time, step_interval)


def start(configs):
    global is_initialization_required
    while True:
        logging.info('GRALAF is starting...')
        logging.info('Chosen algorithm: ' + configs['rca_algorithm'])
        try:
            if is_initialization_required:
                # get_service_graph(configs['prometheus_url'])
                loop_retrieve_training_step(configs)
                is_initialization_required = False
            run(configs)
        except (KeyboardInterrupt, InterruptedError):
            logging.info('Preparing to terminate...')
            break
        except NewMetricFound as newMetricDetection:
            logging.info(newMetricDetection)
            is_initialization_required = True
            logging.info('New metric is found, GRALAF is reinitializing...')
        except Exception as err:
            logging.exception(err)


if __name__ == '__main__':
    args = parse_args()
    with open(args.config) as f:
        app_config = yaml.load(f, Loader=yaml.FullLoader)
    logging.basicConfig(level=getattr(logging, app_config["log_level"]),
                        format=app_config["logging_format"], datefmt=app_config["time_format"])
    if app_config["training_data"]:
        is_initialization_required = False
    start(app_config)
