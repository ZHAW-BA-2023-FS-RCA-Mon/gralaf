import logging
import time

import requests
import yaml

import config as c

logger = logging.getLogger(__name__)


def get_trails(server_addresses):
    for server_address in server_addresses:
        url = f"{server_address}/trails"
        try:
            response = requests.get(url, timeout=5)
        except Exception as e:
            logger.error(f"Couldn't get TRAILS data from {url} :\n{e}")
            continue
        if response.status_code == 200:
            trails_yaml_data = response.text
            trails_yaml_data = yaml.load(trails_yaml_data, Loader=yaml.FullLoader)
            logger.info(f"Got TRAILS data from {url}")
            return trails_yaml_data
        else:
            logger.error(f"Couldn't get TRAILS data from {url}")
    logger.error(f"Couldn't get TRAILS data from {server_addresses}, will try again in 10 seconds.")
    time.sleep(10)
    return get_trails(server_addresses)


def get_service_level_agreements(trails_yaml_data):
    service_level_agreements = {}
    service_list = trails_yaml_data['topology_template']['node_templates']
    for service_name, service_data in service_list.items():
        service_name = service_name.lower().replace("-", "_")
        service_level_agreements[service_name] = {"provider": service_data['properties']['authors'][0]['name']}
        commitments = service_data['properties']['commitment']
        for commitment in commitments:
            sla_list = commitment['sla']
            for sla in sla_list:
                slo_list = sla['slo']
                for slo in slo_list:
                    slo_name = slo['slo_name'].lower()
                    service_level_agreements[service_name][slo_name] = {}
                    if 'slo_min_value' in slo:
                        service_level_agreements[service_name][slo_name]['min'] = slo['slo_min_value']
                    if 'slo_max_value' in slo:
                        service_level_agreements[service_name][slo_name]['max'] = slo['slo_max_value']
    return service_level_agreements


if __name__ == '__main__':
    logging.basicConfig(level=getattr(logging, c.LOG_LEVEL),
                        format=c.LOGGING_FORMAT, datefmt=c.TIME_FORMAT)
    with open('config.yaml') as f:
        app_config = yaml.load(f, Loader=yaml.FullLoader)
    trails_data = get_trails(app_config['trails_server_urls'])
