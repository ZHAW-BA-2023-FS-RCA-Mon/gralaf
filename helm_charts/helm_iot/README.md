## Deployment of MQTT-based virtual IoT device application

Create a namespace with: `kubectl create namespace iot-campus`

Set edgexServer.address/port parameteres in [values.yaml file](helm_charts/helm_iot/values.yaml) to the IP/port address of Edgex MQTT-broker service. 

Use the following commands to install/uninstall the applications.
```
microk8s.helm3 install iot-campus -n iot-campus .
microk8s.helm3 delete iot-campus -n iot-campus .
```
