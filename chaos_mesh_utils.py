import json
import logging
import random
import time
import datetime

import requests

import config as c

logger = logging.getLogger(__name__)
chaos_mesh_experiments = {}
session = requests.Session()
NAMESPACE = "edgex"
chaos_mesh_address = "http://127.0.0.1:30568"


def archive_chaos_experiment(experiment_name, experiment_id):
    url = f"{chaos_mesh_address}/api/experiments/{experiment_id}"
    response = session.request("DELETE", url, timeout=10)
    if response.status_code == 200:
        logger.info(f"Archived chaos mesh experiment {experiment_name}")
    else:
        logger.error(
            f"Unable to archive chaos mesh experiment {experiment_name}. "
            f"Response: {response.status_code} - {response.text}")


def send_experiment(service_name, event_counter, experiment_type, payload, load_info=""):
    experiment_name = f"{experiment_type}_delay"

    url = f"{chaos_mesh_address}/api/experiments"
    chaos_mesh_experiments[str(event_counter)] = service_name
    response = session.request("POST", url, data=payload, timeout=5)
    if response.status_code == 200:
        logger.info(f"Created chaos mesh {experiment_type} experiment for {experiment_name} ({load_info})")
    else:
        logger.error(f"Unable to create chaos mesh {experiment_type} experiment for {experiment_name} ({load_info}). "
                     f"Response: {response.status_code} - {response.text}")
        get_chaos_experiments()
        send_experiment(service_name, event_counter, experiment_type, payload, load_info)
    return response.json()

def add_chaos_mesh_experiment_delay(service_name, event_counter, experiment_duration="70s", namespace=NAMESPACE,
                                    load_size=None):
    experiment_type = "delay"
    if load_size is None:
        load_size = random.randint(400, 800)
    payload = json.dumps({
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "NetworkChaos",
        "metadata": {
            "name": str(event_counter),
            "namespace": namespace
        },
        "spec": {
            "selector": {
                "namespaces": [
                    namespace
                ],
                "labelSelectors": {
                    "org.edgexfoundry.service": service_name
                }
            },
            "mode": "all",
            "duration": experiment_duration,
            "action": "delay",
            "delay": {
                "latency": f"{load_size}ms"
            },
            "direction": "to"
        }
    })
    load_info = f"load {load_size}ms"
    return send_experiment(service_name, event_counter, experiment_type, payload, load_info)


def add_chaos_mesh_experiment_cpu(service_name, event_counter, experiment_duration="70s", namespace=NAMESPACE,
                                  load_size=None):
    experiment_type = "cpu"
    if load_size is None:
        load_size = random.randint(90, 100)
    payload = json.dumps({
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "StressChaos",
        "metadata": {
            "name": str(event_counter),
            "namespace": namespace
        },
        "spec": {
            "selector": {
                "namespaces": [
                    namespace
                ],
                "labelSelectors": {
                    "org.edgexfoundry.service": service_name
                }
            },
            "mode": "all",
            "duration": experiment_duration,
            "stressors": {
                "cpu": {
                    "workers": 12,
                    "load": load_size
                }
            }
        }
    })
    load_info = f"load {load_size}*12"
    return send_experiment(service_name, event_counter, experiment_type, payload, load_info)


def add_chaos_mesh_experiment_memory(service_name, event_counter, experiment_duration="70s", namespace=NAMESPACE,
                                     load_size=None):
    experiment_type = "memory"
    if load_size is None:
        load_size = random.randint(400, 600)
    payload = json.dumps({
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "StressChaos",
        "metadata": {
            "name": str(event_counter),
            "namespace": namespace
        },
        "spec": {
            "selector": {
                "namespaces": [
                    namespace
                ],
                "labelSelectors": {
                    "org.edgexfoundry.service": service_name
                }
            },
            "mode": "all",
            "duration": experiment_duration,
            "stressors": {
                "memory": {
                    "workers": 10,
                    "size": f"{load_size}MB"
                }
            }
        }
    })
    load_info = f"load {load_size}MB"
    return send_experiment(service_name, event_counter, experiment_type, payload, load_info)


def add_chaos_mesh_experiment_failure(service_name, event_counter, experiment_duration="35s", namespace=NAMESPACE):
    experiment_type = "failure"
    payload = json.dumps({
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {
            "name": str(event_counter),
            "namespace": namespace
        },
        "spec": {
            "selector": {
                "namespaces": [
                    namespace
                ],
                "labelSelectors": {
                    "org.edgexfoundry.service": service_name
                }
            },
            "mode": "all",
            "duration": experiment_duration,
            "action": "pod-failure"
        }
    })
    return send_experiment(service_name, event_counter, experiment_type, payload)


def get_chaos_experiments(wait_after_archived_experiments=True):
    url = f"{chaos_mesh_address}/api/experiments"

    response = session.request("GET", url, timeout=5)
    is_any_experiment_archived = False
    if response.status_code == 200:
        active_experiments = response.json()
        for experiment in active_experiments.copy():
            if experiment["status"] in ["paused", "finished"]:
                archive_chaos_experiment(experiment["name"], experiment["uid"])
                active_experiments.remove(experiment)
                is_any_experiment_archived = True
            else:
                creation_timeline = experiment["created_at"]
                creation_timeline = datetime.datetime.strptime(creation_timeline, '%Y-%m-%dT%H:%M:%SZ')
                if creation_timeline < datetime.datetime.now() - datetime.timedelta(seconds=120):
                    archive_chaos_experiment(experiment["name"], experiment["uid"])
                    active_experiments.remove(experiment)
                    is_any_experiment_archived = True
        if is_any_experiment_archived and wait_after_archived_experiments:
            time.sleep(10)
        return active_experiments
    else:
        logger.error(
            f"Unable to get chaos mesh experiments. Response: {response.status_code} - {response.text}")
        return []


if __name__ == '__main__':
    logging.basicConfig(level=getattr(logging, c.LOG_LEVEL),
                        format=c.LOGGING_FORMAT, datefmt=c.TIME_FORMAT)
    service_selected = "edgex-core-data"
    get_chaos_experiments()
    add_chaos_mesh_experiment_delay(service_selected, 25,load_size=500)
    # add_chaos_mesh_experiment_cpu(service_selected, 25, load_size=100)
    # add_chaos_mesh_experiment_memory(service_selected, 25, load_size=500)
