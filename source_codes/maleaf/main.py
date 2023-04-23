#!/usr/bin/env python3

import logging
import argparse

import yaml

logger = logging.getLogger(__name__)


def parse_args():
    """Parse the args."""
    parser = argparse.ArgumentParser(
        description='Root cause analysis for microservices')

    parser.add_argument('--config', type=str, required=False,
                        default='config.yaml',
                        help='Location of config file')
    return parser.parse_args()


def start(configs):
    if configs["test_variable"]:
        logging.info('The value of test_variable is: ', configs["test_variable"])
    else:
        logging.info('test_variable is empty...')


if __name__ == '__main__':
    args = parse_args()
    with open(args.config) as f:
        app_config = yaml.load(f, Loader=yaml.FullLoader)
    logging.basicConfig(level=getattr(logging, app_config["log_level"]),
                        format=app_config["logging_format"], datefmt=app_config["time_format"])

    start(app_config)
