#!/usr/bin/env python3
import argparse
import logging
import pickle
import time

import yaml

from cbn_based_rca import loop_retrieve_training_step
from generate_cbn import train_model
from metric import get_service_graph
from models.exception import NewMetricFound
from sla import get_trails, get_service_level_agreements
from test_data import get_test_data_from_live_system, test_stored_data, check_metrics

LOG_LEVEL = "INFO"
TIME_FORMAT = '%H:%M:%S'
LOGGING_FORMAT = "%(asctime)s.%(msecs)03d-> %(message)s"

SERVICE_SELECTED = "edgex-core-data"

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
    # trained_model = None
    start_time = time.time()
    trained_model = train_model(config)
    training_end_time = time.time()
    training_completion_time = training_end_time - start_time
    logger.info(f"Training completed in {training_completion_time} seconds.")
    while True:
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
                check_metrics(config, trained_model, new_data, sla_data=sla_data)
        except Exception as e:
            logging.exception(e)
        logging.debug("Checked system")


def start(configs):
    global is_initialization_required
    while True:
        logging.info('GRALAF is starting...')
        try:
            if is_initialization_required:
                get_service_graph(configs['prometheus_url'])
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
    logging.basicConfig(level=getattr(logging, LOG_LEVEL),
                        format=LOGGING_FORMAT, datefmt=TIME_FORMAT)
    with open(args.config) as f:
        app_config = yaml.load(f, Loader=yaml.FullLoader)
    if app_config["training_data"]:
        is_initialization_required = False
    start(app_config)
