# Graph Based Liability Analysis Framework (GRALAF)

-----------------------------------------

GRALAF tracks metrics and compares them with the given Service Level Agreement (SLA) data from TRAILS. 

In the case of an SLA violation, it performs RCA based on CBN and reports to an external liability service about the corresponding violation with the estimated probability of fault types for each service being responsible for the incident. 

It is developed in Python and can be deployed in the same Kubernetes environment with the [Edgex](https://github.com/edgexfoundry/edgex-go) services.

## :wrench: Deployment

<img src="images/useCase.png" alt="use case"/>

We utilized five VMs for the entire test setup in an OpenStack cloud infrastructure.

Three of them (VM1-3) are used to deploy a MicroK8s cluster environment which hosts Edgex and GRALAF microservices along with all the necessary system components such as Prometheus, Chaos Mesh, and Istio. 
These services can be deployed with the helm charts available under [gralaf_infrastructure](helm_charts/gralaf_infrastructure).

VM4 hosted another MicroK8s environment where 25 MQTT-based virtual IoT device applications are deployed. The applications can be deployed with [helm_iot](helm_charts/helm_iot) helm chart

VM5 hosted Fledge server. You may follow [the official page](https://github.com/fledge-iot/fledge) for the installation. After installing *http_south* plugin from the UI. In order to send sensor data from Edgex, we also added a *http_south* service with the following configurations:
```
Host: 0.0.0.0
Port: 6683
URI: sensor-reading
Asset Name Prefix: edgex-
Enable: HTTP
HTTPS Port: 6684
Certificate Name: fledge
```


The resource specifications for VM1, VM2, and VM3 are 4 vCPU, 8GB RAM, and 160GB SSD storage.<br />
For VM4 and VM5, each has 1 vCPU, 2GB RAM, and 120GB SSD.
