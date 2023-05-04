import datetime
import json
import logging
import random
import time

import requests

import config as c

SERVICE_SELECTED = "edgex-core-data"
# DEFAULT_CHAOS_MESH_ADDRESS = "http://localhost:30535"
DEFAULT_CHAOS_MESH_ADDRESS = "http://chaos-dashboard.chaos-mesh.svc.cluster.local:2333"
DEFAULT_DURATION = "70s"

NAMESPACE = "edgex"

logger = logging.getLogger(__name__)
chaos_mesh_experiments = {}
session = requests.Session()


def add_pod_selector(payload, specific_pods, namespace="edgex"):
    payload["spec"]["selector"]["pods"] = {namespace: specific_pods}


def get_related_pods(service_name, namespace="edgex", chaos_mesh_address=DEFAULT_CHAOS_MESH_ADDRESS):
    url = f"{chaos_mesh_address}/api/common/pods"

    payload = json.dumps({
        "namespaces": [
            namespace
        ],
        "labelSelectors": {
            "org.edgexfoundry.service": service_name
        },
        "annotationSelectors": {}
    })

    response = session.request("POST", url, data=payload, timeout=5)
    if not response.status_code == 200:
        logger.info(f"Could not get pods (Response: {response.status_code} - {response.text}")
        pods = []
    else:
        pods = response.json()
        pods = [service_pod["name"] for service_pod in pods]
    return pods


def archive_chaos_experiment(experiment_name, experiment_id, chaos_mesh_address=DEFAULT_CHAOS_MESH_ADDRESS):
    url = f"{chaos_mesh_address}/api/experiments/{experiment_id}"
    response = session.request("DELETE", url, timeout=10)
    if response.status_code == 200:
        logger.info(f"Archived chaos mesh experiment {experiment_name}")
    else:
        logger.error(
            f"Unable to archive chaos mesh experiment {experiment_name}. "
            f"Response: {response.status_code} - {response.text}")


def send_experiment(service_name, event_counter, experiment_type, payload, load_info="",
                    chaos_mesh_address=DEFAULT_CHAOS_MESH_ADDRESS):
    experiment_name = f"{event_counter}_{service_name}_delay"

    url = f"{chaos_mesh_address}/api/experiments"
    chaos_mesh_experiments[str(event_counter)] = service_name
    response = session.request("POST", url, data=payload, timeout=5)
    if response.status_code == 200:
        logger.info(f"Created chaos mesh {experiment_type} experiment for {experiment_name} ({load_info})")
    else:
        logger.error(f"Unable to create chaos mesh {experiment_type} experiment for {experiment_name} ({load_info}). "
                     f"Response: {response.status_code} - {response.text}")
        get_chaos_experiments()
        send_experiment(service_name, event_counter, experiment_type, payload, load_info, chaos_mesh_address)
    return response.json()


def add_chaos_mesh_experiment_delay(service_name, event_counter, experiment_duration=DEFAULT_DURATION,
                                    namespace=NAMESPACE,
                                    load_size=None, specific_pods=None, chaos_mesh_address=DEFAULT_CHAOS_MESH_ADDRESS):
    experiment_type = "delay"
    if load_size is None:
        load_size = random.randint(400, 800)
    payload = {
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
                },
                "pods": {
                    "edgex": [
                        "edgex-core-data-77cf5984df-jzvb8"
                    ]
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
    }
    if specific_pods:
        add_pod_selector(payload, specific_pods)
    payload = json.dumps(payload)
    load_info = f"load {load_size}ms"
    return send_experiment(service_name, event_counter, experiment_type, payload, load_info, chaos_mesh_address)


def add_chaos_mesh_experiment_cpu(service_name, event_counter, experiment_duration=DEFAULT_DURATION,
                                  namespace=NAMESPACE,
                                  load_size=None, chaos_mesh_address=DEFAULT_CHAOS_MESH_ADDRESS):
    experiment_type = "cpu"
    if load_size is None:
        load_size = random.randint(90, 100)
    payload = {
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
    }
    payload = json.dumps(payload)
    load_info = f"load {load_size}*12"
    return send_experiment(service_name, event_counter, experiment_type, payload, load_info, chaos_mesh_address)


def add_chaos_mesh_experiment_memory(service_name, event_counter, experiment_duration=DEFAULT_DURATION,
                                     namespace=NAMESPACE,
                                     load_size=None, chaos_mesh_address=DEFAULT_CHAOS_MESH_ADDRESS):
    experiment_type = "memory"
    if load_size is None:
        load_size = random.randint(400, 600)
    payload = {
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
    }
    payload = json.dumps(payload)
    load_info = f"load {load_size}MB"
    return send_experiment(service_name, event_counter, experiment_type, payload, load_info, chaos_mesh_address)


def add_chaos_mesh_experiment_failure(service_name, event_counter, experiment_duration="35s", namespace=NAMESPACE,
                                      chaos_mesh_address=DEFAULT_CHAOS_MESH_ADDRESS):
    experiment_type = "failure"
    payload = {
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
    }
    payload = json.dumps(payload)
    return send_experiment(service_name, event_counter, experiment_type, payload, chaos_mesh_address)


def get_chaos_experiments(wait_after_archived_experiments=True, chaos_mesh_address=DEFAULT_CHAOS_MESH_ADDRESS):
    url = f"{chaos_mesh_address}/api/experiments"
    try:
        response = session.request("GET", url, timeout=5)
    except:
        logger.error(f"Unable to get chaos mesh experiments. Will try in 5 seconds..")
        time.sleep(5)
        return get_chaos_experiments(wait_after_archived_experiments, chaos_mesh_address)
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
    service_pods = get_related_pods(SERVICE_SELECTED)
    get_chaos_experiments()
    add_chaos_mesh_experiment_delay(SERVICE_SELECTED, "script", load_size=800, specific_pods=service_pods)
    # add_chaos_mesh_experiment_cpu(service_selected, 25, load_size=100)
    # add_chaos_mesh_experiment_memory(service_selected, 25, load_size=500)
