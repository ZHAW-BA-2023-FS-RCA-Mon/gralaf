import argparse
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import gevent.monkey

gevent.monkey.patch_all()
from locust import HttpUser, task, between
import logging

from locust.env import Environment

from data import device_event

TARGET_ADDRESS = "http://127.0.0.1:30880"
THREAD_NUMBER = 100
DEVICE_NUMBER = 1
DEVICE_NAME_PREFIX = "iot-device"
LOG_LEVEL = "INFO"
TIME_FORMAT = '%H:%M:%S'
LOGGING_FORMAT = "%(asctime)s.%(msecs)03d-> %(message)s"
IOT_DEVICE_PROFILE_NAME = "iot-device-profile"
IOT_DEVICE_PROFILE = '''name: "%s"
manufacturer: "ZHAW"
model: "MQTT-DEVICE"
description: "IoT application profile"
labels:
  - "mqtt"
  - "iot"
deviceResources:
  -
    name: randnum
    isHidden: true
    description: "device random number"
    properties:
      valueType: "Float32"
      readWrite: "R"
  -
    name: ping
    isHidden: true
    description: "device awake"
    properties:
      valueType: "String"
      readWrite: "R"
  -
    name: message
    isHidden: false
    description: "device message"
    properties:
      valueType: "String"
      readWrite: "RW"
  -
    name: json
    isHidden: false
    description: "JSON message"
    properties:
      valueType: "Object"
      readWrite: "RW"
      mediaType: "application/json"

deviceCommands:
  -
    name: values
    readWrite: "R"
    isHidden: false
    resourceOperations:
      - { deviceResource: "randnum" }
      - { deviceResource: "ping" }
      - { deviceResource: "message" }
''' % IOT_DEVICE_PROFILE_NAME

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=THREAD_NUMBER, thread_name_prefix="trader")


class EdgexUser(HttpUser):
    wait_time = between(1, 2)

    def __init__(self, *args, host=TARGET_ADDRESS, **kwargs):
        self.host = host
        if "user_id" in kwargs:
            self.user_id = kwargs["user_id"]
            del kwargs["user_id"]
        else:
            self.user_id = -1
        super().__init__(*args, **kwargs)

    def config_edgex_profiles(self):
        self.add_iot_device_profile()
        for device_id in range(number_of_devices):
            device_name = f"{DEVICE_NAME_PREFIX}-{device_id}"
            self.add_device(device_name=device_name, profile_name=IOT_DEVICE_PROFILE_NAME, device_id=str(device_id),
                            labels=["mqtt", "iot"])
        self.add_device_service()
        self.add_camera_device_profile(profile_name="camera-monitor-profile")

    def on_start(self):
        self.add_device_for_events()
        logger.info(f"Locust user {self.user_id} started.")

    # @task(4)
    # def frontend(self):
    #     self.client.get("/")

    def get_basic(self, path):
        result = self.client.get(path)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")

    @task(5)
    def initializer_and_dashboard(self):
        paths = ["/api/v2/auth/securemode", "/core-data/api/v2/event/count", "/core-data/api/v2/reading/count",
                 "/core-metadata/api/v2/deviceservice/all?offset=0&limit=-1", "/core-metadata/api/v2/device/all",
                 "/core-metadata/api/v2/deviceprofile/all?offset=0&limit=-1",
                 "/support-scheduler/api/v2/interval/all?offset=0&limit=-1",
                 "/support-notifications/api/v2/notification/status/NEW?offset=0&limit=-1"]
        for path in paths:
            self.get_basic(path)
        logger.info(f"User#{self.user_id} visited dashboard")

    @task(1)
    def metadata(self):
        paths = ["/core-metadata/api/v2/deviceservice/all?offset=0&limit=-1",
                 "/core-metadata/api/v2/device/service/name/device-virtual?offset=0&limit=-1",
                 "/core-metadata/api/v2/device/service/name/device-virtual?offset=0&limit=20",
                 "/core-metadata/api/v2/device/service/name/device-rest?offset=0&limit=20"]
        for path in paths:
            self.get_basic(path)
        logger.info(f"User#{self.user_id} visited metadata")

    @task(1)
    def system(self):
        paths = ["/api/v2/registercenter/service/all",
                 "/sys-mgmt-agent/api/v2/system/health?services=support-notifications,core-command,core-data,"
                 "device-virtual,support-scheduler,sys-mgmt-agent,app-rules-engine,core-metadata,device-rest"]
        for path in paths:
            self.get_basic(path)
        logger.info(f"User#{self.user_id} visited service list")

    @task(1)
    def datacenter_event(self):
        path = "/core-data/api/v2/event/all?offset=0&limit=5"
        self.get_basic(path)
        logger.info(f"User#{self.user_id} got the last 5 event")

    @task(1)
    def datacenter_reading(self):
        path = "/core-data/api/v2/reading/all?offset=0&limit=5"
        self.get_basic(path)
        logger.info(f"User#{self.user_id} got the last 5 reading")

    @task(1)
    def notifications_notification(self):
        path = "/support-notifications/api/v2/notification/status/NEW?offset=0&limit=5"
        self.get_basic(path)
        logger.info(f"User#{self.user_id} got the last 5 notifications")

    @task(1)
    def notifications_subscription(self):
        path = "/support-notifications/api/v2/notification/status/NEW?offset=0&limit=5"
        self.get_basic(path)
        logger.info("Got the last 5 readings")

    @task(1)
    def intervals_interval(self):
        path = "/support-scheduler/api/v2/interval/all?offset=0&limit=5"
        self.get_basic(path)
        logger.info(f"User#{self.user_id} got the last 5 intervals")

    @task(1)
    def intervals_action(self):
        path = "/support-scheduler/api/v2/intervalaction/all?offset=0&limit=5"
        self.get_basic(path)
        logger.info(f"User#{self.user_id} got the last 5 interval actions")

    @task(1)
    def add_camera_device_profile(self, profile_name=None):
        if profile_name is None:
            profile_name = f"test-profile-{self.user_id}"
        path = "/api/v2/profile/yaml"
        payload = "name: " + profile_name + "\nmanufacturer: \"IOTech\"\nmodel: \"Cam12345\"\nlabels: \n- \"camera\"\ndescription: \"Dummy profile\"\n\ndeviceResources:\n-\n  name: \"HumanCount\"\n  isHidden: false\n  description: \"Number of people on camera\"\n  properties:\n    valueType:  \"Int16\"\n    readWrite: \"R\"\n    defaultValue: \"0\"\n-\n  name: \"CanineCount\"\n  isHidden: false\n  description: \"Number of dogs on camera\"\n  properties:\n    valueType:  \"Int16\"\n    readWrite: \"R\"  #designates that this property can only be read and not set\n    defaultValue: \"0\"\n-\n  name: \"ScanDepth\"\n  isHidden: false\n  description: \"Get/set the scan depth\"\n  properties:\n    valueType:  \"Int16\"\n    readWrite: \"RW\"  #designates that this property can be read or set\n    defaultValue: \"0\"\n\n-\n  name: \"SnapshotDuration\"\n  isHidden: false\n  description: \"Get the snaphot duration\"\n  properties:\n    valueType:  \"Int16\"\n    readWrite: \"RW\"  #designates that this property can be read or set\n    defaultValue: \"0\"\n\ndeviceCommands:\n-\n  name: \"Counts\"\n  readWrite: \"R\"\n  isHidden: false\n  resourceOperations:\n  - { deviceResource: \"HumanCount\" }\n  - { deviceResource: \"CanineCount\" }\n"
        result = self.client.post(path, data=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Created device profile {profile_name}.")

    def add_iot_device_profile(self):
        path = "/api/v2/profile/yaml"
        payload = IOT_DEVICE_PROFILE
        result = self.client.post(path, data=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Created device profile {IOT_DEVICE_PROFILE_NAME}.")

    @task(1)
    def edit_device_profile(self):
        profile_name = f"test-profile-{self.user_id}"
        path = "/api/v2/profile/yaml"
        payload = "name: " + profile_name + "\nmanufacturer: IOTech\ndescription: Dummy profile (edited)\nmodel: Cam12345\nlabels: [camera]\ndeviceResources:\n- description: Number of people on camera 5\n  name: HumanCount\n  isHidden: false\n  tag: \"\"\n  properties:\n    valueType: Int16\n    readWrite: R\n    units: \"\"\n    minimum: \"\"\n    maximum: \"\"\n    defaultValue: \"0\"\n    mask: \"\"\n    shift: \"\"\n    scale: \"\"\n    offset: \"\"\n    base: \"\"\n    assertion: \"\"\n    mediaType: \"\"\n  attributes: {}\n- description: Number of dogs on camera\n  name: CanineCount\n  isHidden: false\n  tag: \"\"\n  properties:\n    valueType: Int16\n    readWrite: R\n    units: \"\"\n    minimum: \"\"\n    maximum: \"\"\n    defaultValue: \"0\"\n    mask: \"\"\n    shift: \"\"\n    scale: \"\"\n    offset: \"\"\n    base: \"\"\n    assertion: \"\"\n    mediaType: \"\"\n  attributes: {}\n- description: Get/set the scan depth\n  name: ScanDepth\n  isHidden: false\n  tag: \"\"\n  properties:\n    valueType: Int16\n    readWrite: RW\n    units: \"\"\n    minimum: \"\"\n    maximum: \"\"\n    defaultValue: \"0\"\n    mask: \"\"\n    shift: \"\"\n    scale: \"\"\n    offset: \"\"\n    base: \"\"\n    assertion: \"\"\n    mediaType: \"\"\n  attributes: {}\n- description: Get the snaphot duration\n  name: SnapshotDuration\n  isHidden: false\n  tag: \"\"\n  properties:\n    valueType: Int16\n    readWrite: RW\n    units: \"\"\n    minimum: \"\"\n    maximum: \"\"\n    defaultValue: \"0\"\n    mask: \"\"\n    shift: \"\"\n    scale: \"\"\n    offset: \"\"\n    base: \"\"\n    assertion: \"\"\n    mediaType: \"\"\n  attributes: {}\ndeviceCommands:\n- name: Counts\n  isHidden: false\n  readWrite: R\n  resourceOperations:\n  - deviceResource: HumanCount\n    defaultValue: \"\"\n    mappings: {}\n  - deviceResource: CanineCount\n    defaultValue: \"\"\n    mappings: {}\n"
        result = self.client.put(path, data=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Edited device profile {profile_name}.")

    @task(1)
    def delete_device_profile(self):
        profile_name = f"test-profile-{self.user_id}"
        path = f"/core-metadata/api/v2/deviceprofile/name/{profile_name}"
        result = self.client.delete(path)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Deleted device profile {profile_name}.")

    @task(1)
    def add_device_service(self):
        path = "/core-metadata/api/v2/deviceservice"
        payload = [
            {
                "apiVersion": "v2",
                "service": {
                    "name": "camera-device-service",
                    "description": "Manage cameras",
                    "adminState": "UNLOCKED",
                    "labels": [
                        "camera",
                        "counter"
                    ],
                    "baseAddress": "camera-device-service:59990"
                }
            }
        ]
        result = self.client.post(path, json=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info("Created camera-device-service device service.")

    def add_device_for_events(self):
        device_name = f"test-camera-{self.user_id}"
        path = "/core-metadata/api/v2/device"
        payload = [
            {
                "apiVersion": "v2",
                "device": {
                    "name": device_name,
                    "description": "human and dog counting camera #1",
                    "adminState": "UNLOCKED",
                    "operatingState": "UP",
                    "labels": [
                        "camera",
                        "counter"
                    ],
                    "location": "{lat:45.45,long:47.80}",
                    "serviceName": "camera-control-device-service",
                    "profileName": "camera-monitor-profile",
                    "protocols": {
                        "camera-protocol": {
                            "camera-address": "localhost",
                            "port": "1234",
                            "unitID": "1"
                        }
                    },
                    "notify": False
                }
            }
        ]
        result = self.client.post(path, json=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Added device {device_name} for events.")

    @task(1)
    def add_device(self, device_name=None, profile_name="Test-Device-MQTT-Profile", device_id="",
                   labels=None):
        if labels is None:
            labels = ["MQTT", "test"]
        if not device_name:
            device_name = f"MQTT-test-{self.user_id}"
        path = "/core-metadata/api/v2/device"
        payload = [
            {
                "apiVersion": "v2",
                "device": {
                    "name": device_name,
                    "description": "Mqtt device python script",
                    "adminState": "UNLOCKED",
                    "operatingState": "UP",
                    "labels": labels,
                    "serviceName": "device-mqtt",
                    "profileName": profile_name,
                    "autoEvents": [
                        {
                            "interval": "15s",
                            "onChange": False,
                            "sourceName": "randnum"
                        }
                    ],
                    "protocols": {
                        "mqtt": {
                            "CommandTopic": f"CommandTopic{device_id}"
                        }
                    }
                }
            }
        ]
        result = self.client.post(path, json=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Created device {device_name}.")

    @task(1)
    def edit_device(self):
        path = "/core-metadata/api/v2/device"
        device_name = f"MQTT-test-{self.user_id}"
        payload = [
            {
                "apiVersion": "v2",
                "device": {
                    "name": device_name,
                    "description": "Mqtt device python script (edited)",
                    "adminState": "UNLOCKED",
                    "operatingState": "UP",
                    "labels": [
                        "MQTT",
                        "test"
                    ],
                    "serviceName": "device-mqtt",
                    "profileName": "my-custom-device-profile",
                    "autoEvents": [
                    ],
                    "protocols": {
                        "mqtt": {
                            "CommandTopic": f"CommandTopicTest{self.user_id}"
                        }
                    }
                }
            }
        ]
        result = self.client.patch(path, json=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Edited device {device_name}.")

    @task(1)
    def delete_device(self):
        device_name = f"MQTT-test-{self.user_id}"
        path = f"/core-metadata/api/v2/device/name/{device_name}"
        result = self.client.delete(path)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Deleted device {device_name}.")

    @task(10)
    def send_event(self):
        device_name = f"test-camera-{self.user_id}"
        path = f"/core-data/api/v2/event/camera-monitor-profile/{device_name}/HumanCount"
        new_event = device_event.copy()
        new_event["event"]["id"] = str(uuid.uuid1())
        new_event["event"]["deviceName"] = device_name
        for reading in new_event["event"]["readings"]:
            reading["deviceName"] = device_name
        result = self.client.post(path, json=new_event)
        if result.status_code not in [200, 201, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Sent event for device {device_name}.")

    @task(1)
    def get_events_for_device(self):
        device_name = f"test-camera-{self.user_id}"
        path = f"/core-data/api/v2/event/device/name/{device_name}"
        result = self.client.get(path)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Received events for device {device_name}.")

    @task(1)
    def get_value_from_mqtt_device(self):
        device_id = random.randint(0, number_of_devices - 1)
        device_name = f"{DEVICE_NAME_PREFIX}-{device_id}"
        path = f"/core-command/api/v2/device/name/{device_name}/message"
        result = self.client.get(path)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Received value for device {device_name}.")

    @task(1)
    def send_device_command_for_mqtt_device(self):
        device_id = random.randint(0, number_of_devices - 1)
        device_name = f"{DEVICE_NAME_PREFIX}-{device_id}"
        path = f"/core-command/api/v2/device/name/{device_name}/message"
        payload = {"message": "message-inputed"}
        result = self.client.put(path, json=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Sent command to device {device_name}.")

    @task(1)
    def add_scheduler_interval(self):
        path = f"/support-scheduler/api/v2/interval"
        payload = [
            {
                "apiVersion": "v2",
                "interval": {
                    "name": "5min",
                    "interval": "5m",
                    "runOnce": False
                }
            }
        ]
        result = self.client.post(path, json=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Scheduler interval added.")

    @task(1)
    def add_scheduler_interval_action(self):
        path = f"/support-scheduler/api/v2/intervalaction"
        payload = [
            {
                "apiVersion": "v2",
                "action": {
                    "adminState": "UNLOCKED",
                    "address": {
                        "type": "REST",
                        "httpMethod": "DELETE",
                        "retained": False,
                        "autoReconnect": True,
                        "host": "edgex-core-data",
                        "port": 59880,
                        "path": "/api/v2/event/age/300000000000",
                        "recipients": [
                            ""
                        ]
                    },
                    "name": "5min_cleaning",
                    "intervalName": "5min"
                }
            }
        ]
        result = self.client.post(path, json=payload)
        if result.status_code not in [200, 207]:
            logger.info(f"{path}\nResponse code:{result.status_code}\nResponse text:{result.text}")
        logger.info(f"Scheduler interval action added.")


def start_user(user_id, target_address):
    user_env = Environment()
    new_user = EdgexUser(user_env, user_id=user_id, host=target_address)
    new_user.run()


if __name__ == '__main__':
    logging.basicConfig(level=getattr(logging, LOG_LEVEL),
                        format=LOGGING_FORMAT, datefmt=TIME_FORMAT)
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--target', help='Edgex UI address', default=TARGET_ADDRESS)
    parser.add_argument('-u', '--number_of_users', help='number of users', default=THREAD_NUMBER, type=int)
    parser.add_argument('-d', '--number_of_devices', help='number of devices', default=DEVICE_NUMBER, type=int)
    args = parser.parse_args()
    logger.info(args)
    target = args.target
    number_of_users = args.number_of_users
    number_of_devices = args.number_of_devices
    env = Environment()
    user_for_configuring_edgex = EdgexUser(env, user_id=-1, host=target)
    user_for_configuring_edgex.config_edgex_profiles()
    user_for_configuring_edgex.add_scheduler_interval()
    user_for_configuring_edgex.add_scheduler_interval_action()
    for i in range(args.number_of_users):
        executor.submit(start_user, i, target)
        time.sleep(0.01)
