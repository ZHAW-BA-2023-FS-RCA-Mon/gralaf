import argparse
import json
import logging
import random
import socket
import threading
import time

import paho.mqtt.client as mqtt

DEVICE_NAME = ""
MQTT_SERVER_IP = ""
MQTT_SERVER_PORT = "30883"
COMMAND_TOPIC = "CommandTopic"
RESPONSE_TOPIC = "ResponseTopic"
DATA_TOPIC = "DataTopic"
LOG_LEVEL = "INFO"
TIME_FORMAT = '%H:%M:%S'
LOGGING_FORMAT = "%(asctime)s.%(msecs)03d-> %(message)s"
THREAD_NUMBER = 100
TIME_INTERVAL = 15

logger = logging.getLogger(__name__)
device_id = ""
response_text_message = "test-message"
response_json_message = {"name": "My JSON"}

last_time_packet_is_received = time.time()


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    logger.info("Connected with result code " + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(COMMAND_TOPIC)
    client.subscribe("$SYS/#")


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    global response_text_message, response_json_message, last_time_packet_is_received
    last_time_packet_is_received = time.time()
    if msg.topic == COMMAND_TOPIC:
        logger.info(msg.topic + " " + str(msg.payload))
        payload = json.loads(msg.payload.decode())
        method = payload["method"]
        cmd = payload["cmd"]
        if method == "set":
            if cmd == "message":
                response_text_message = payload["message"]
            elif cmd == "json":
                response_json_message = payload["json"]
            else:
                logger.error(f"Unhandled method: {payload}")
        else:
            if cmd == "ping":
                payload["ping"] = "pong"
            elif cmd == "message":
                payload["message"] = response_text_message
            elif cmd == "json":
                payload["json"] = response_json_message
            elif cmd == "randnum":
                payload["randnum"] = float("{:.2f}".format(random.random() * 100))
            else:
                logger.error(f"Unhandled method: {payload}")
        logger.info(f"Response: {payload}")
        client.publish(RESPONSE_TOPIC, payload=json.dumps(payload))


def on_disconnect(client, userdata, rc):
    logger.error("Disconnected with result code  " + str(rc))
    time.sleep(15)
    client.disconnect()


def send_data(client, time_interval=TIME_INTERVAL):
    while True:
        if last_time_packet_is_received + 60 < time.time():
            logger.error(
                "Didn't get any message for a while, probably connection is lost. Shall terminate in 15 seconds...")
            time.sleep(15)
            client.disconnect()
        payload = {
            "name": DEVICE_NAME,
            "cmd": "randnum",
            "randnum": float("{:.2f}".format(random.random() * 100))
        }
        result = client.publish(DATA_TOPIC, payload=json.dumps(payload))
        logger.info(f"Sent data: result->{result} payload->{payload}")
        time.sleep(time_interval)


def initialize_client():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_SERVER_IP, MQTT_SERVER_PORT, 60)
    client.on_disconnect = on_disconnect
    return client


if __name__ == '__main__':
    logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOGGING_FORMAT, datefmt=TIME_FORMAT)
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', help='MQTT server port', default=MQTT_SERVER_PORT)
    parser.add_argument('-i', '--ip', help='MQTT server IP', default=MQTT_SERVER_IP)
    parser.add_argument('-n', '--name', help='Device name', default=DEVICE_NAME)
    args = parser.parse_args()
    MQTT_SERVER_PORT = int(args.port)
    MQTT_SERVER_IP = args.ip
    DEVICE_NAME = args.name
    if DEVICE_NAME == "":
        DEVICE_NAME = socket.gethostname()
        device_id = DEVICE_NAME.split("-")[-1]
    COMMAND_TOPIC += device_id
    logger.info(args)
    logger.info(f"Device name is {DEVICE_NAME}, command topic:{COMMAND_TOPIC}")
    mqtt_client = initialize_client()
    informer_thread = threading.Thread(target=send_data, args=(mqtt_client,))
    informer_thread.daemon = True
    informer_thread.start()
    # Blocking call that processes network traffic, dispatches callbacks and
    # handles reconnecting.
    # Other loop*() functions are available that give a threaded interface and a
    # manual interface.
    mqtt_client.loop_forever()
