import glob
import logging
import random

import yaml

import config as c
import main
from generate_model import train_model

TRAINING_DATASET_START_INDEX = 0
TEST_DATASET_START_INDEX = 1
NUMBER_OF_DATASETS_FOR_TRAINING = 1
TRAINING_DATASET_FOLDER = "dataset"
TEST_DATASET_FOLDER = "dataset"
MAX_NUMBER_OF_SERVICES = 8
logger = logging.getLogger(__name__)
original_set_of_services_for_fault_injection = []
original_services_skipped = []
shapes=[]

def loop_datasets():
    list_of_training_datasets = list(glob.iglob(f'{TRAINING_DATASET_FOLDER}/*.csv'))
    list_of_training_datasets = sorted(list_of_training_datasets)
    list_of_test_datasets = list(glob.iglob(f'{TEST_DATASET_FOLDER}/*.csv'))
    list_of_test_datasets = sorted(list_of_test_datasets)
    original_set_of_services_for_fault_injection.extend(app_config["services_for_fault_injection"])
    original_services_skipped.extend(app_config["services_skipped"])
    for file_index in range(len(list_of_training_datasets)):
        if file_index < TRAINING_DATASET_START_INDEX:
            continue
        app_config["training_data"] = list_of_training_datasets[file_index:file_index + NUMBER_OF_DATASETS_FOR_TRAINING]
        if len(app_config["training_data"]) < NUMBER_OF_DATASETS_FOR_TRAINING:
            app_config["training_data"].extend(
                list_of_training_datasets[:NUMBER_OF_DATASETS_FOR_TRAINING - len(app_config["training_data"])])
        app_config["test_data"] = [
            list_of_test_datasets[(file_index + TEST_DATASET_START_INDEX) % len(list_of_test_datasets)]]
        logger.info(f"\nTraining files:\t{app_config['training_data']}\nTest files:\t{app_config['test_data']}")
        if len(original_set_of_services_for_fault_injection) >= MAX_NUMBER_OF_SERVICES:
            services_for_fault_injection = random.sample(original_set_of_services_for_fault_injection,
                                                         MAX_NUMBER_OF_SERVICES)
            skipped_services = set(original_set_of_services_for_fault_injection) - set(services_for_fault_injection)
            skipped_services.update(original_services_skipped)
            app_config["services_for_fault_injection"] = services_for_fault_injection
            app_config["services_skipped"] = list(skipped_services)
        logger.info(f"Services for fault injection: {app_config['services_for_fault_injection']}")
        logger.info(f"Skipped services: {app_config['services_skipped']}")
        try:
            pass
            main.run(app_config)
            training_data_shape = train_model(app_config)
            shapes.append(training_data_shape)
        except Exception as e:
            logger.exception(f"Error occurred for datasets '{app_config['training_data']}':\n{e}")
    logger.info(f"\n{shapes}")

if __name__ == '__main__':
    logging.basicConfig(level=getattr(logging, c.LOG_LEVEL),
                        format=c.LOGGING_FORMAT, datefmt=c.TIME_FORMAT)
    with open('config.yaml') as f:
        app_config = yaml.load(f, Loader=yaml.FullLoader)
    loop_datasets()
