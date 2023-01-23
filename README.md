# Graph Based Liability Analysis Framework (GRALAF)

-----------------------------------------

GRALAF [[1]](#1) tracks metrics and compares them with the given Service Level Agreement (SLA) data from TRAILS. 

In the case of an SLA violation, it performs RCA based on CBN and reports to an external liability service about the corresponding violation with the estimated probability of fault types for each service being responsible for the incident. 

It is developed in Python and can be deployed in the same Kubernetes environment with the [Edgex](https://github.com/edgexfoundry/edgex-go) services.

## :wrench: Deployment

<img src="images_for_git/useCase.png" alt="use case"/>

We utilized five VMs for the entire test setup in an OpenStack cloud infrastructure.

Three of them (VM1-3) are used to deploy a MicroK8s cluster environment which hosts Edgex and GRALAF microservices along with all the necessary system components such as Prometheus, Chaos Mesh, and Istio. 
These services can be deployed with the helm charts available under [gralaf_infrastructure](helm_charts/gralaf_infrastructure).

VM4 hosted another MicroK8s environment where 25 MQTT-based virtual IoT device applications are deployed. The applications can be deployed with [helm_iot](helm_charts/helm_iot) helm chart.

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


Following deployment is valid for Ubuntu 22.04.

On all machines you want to have a cluster, install MicroK8s with 
- ```sudo snap install microk8s --classic```


Run `microk8s add-node` on the first VM which is going to be master node and follow the printed instructions. 
Note: You may need to add the ip address-hostname pair to /etc/hosts for the master node. Example /etc/hosts  file:
```
127.0.0.1 localhost
127.0.1.1 vm1
10.0.11.13 vm2

# The following lines are desirable for IPv6 capable hosts
::1     ip6-localhost ip6-loopback
fe00::0 ip6-localnet
ff00::0 ip6-mcastprefix
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
```

- On master node, activate add-ons with
  - ```microk8s enable istio```
  - ```microk8s enable community```

In order to use kubectl instead of microk8s.kubectl: 
- ```sudo snap alias microk8s.kubectl kubectl```

### Building the containers
The microK8's local repository can be activated with the following command so that we can upload our locally build containers. 
```microk8s enable registry```



Then, the following commands can be used to build a docker image and upload it to the microK8's local repository
```
docker build -f Dockerfile-gralaf -t localhost:32000/load-generator:0.0.3 .
docker push localhost:32000/load-generator:0.0.3
```


The resource specifications for VM1, VM2, and VM3 are 4 vCPU, 8GB RAM, and 160GB SSD storage.<br />
For VM4 and VM5, each has 1 vCPU, 2GB RAM, and 120GB SSD.


<a id="1">[1]</a>  O. Kalinagac, W. Soussi, Yacine Anser, Chrystel Gaber, and G. Gür, "Root Cause and Liability Analysis in the Microservices Architecture for Edge IoT Services," [In progress]
