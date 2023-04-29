# Graph Based Liability Analysis Framework (GRALAF)

-----------------------------------------

GRALAF [[1]](#1) tracks metrics and compares them with the given Service Level Agreement (SLA) data from TRAILS. 

In the case of an SLA violation, it performs RCA based on CBN and reports to an external liability service about the corresponding violation with the estimated probability of fault types for each service being responsible for the incident. 

It is developed in Python and can be deployed in the same Kubernetes environment with the [Edgex](https://github.com/edgexfoundry/edgex-go) services.

## :computer: Testbed Architecture

<img src="images_for_git/useCase.png" alt="use case"/>

We utilized five VMs for the entire test setup in an OpenStack cloud infrastructure.

The resource specifications for VM1, VM2, and VM3 are 4 vCPU, 8GB RAM, and 50GB SSD storage.<br />
For VM4 and VM5, each has 1 vCPU, 2GB RAM, and 30GB SSD.

Three of them (VM1-3) are used to deploy a MicroK8s cluster environment which hosts Edgex and GRALAF microservices along with all the necessary system components such as Prometheus, Chaos Mesh, and Istio. 



VM4 hosts another MicroK8s environment where 25 MQTT-based virtual IoT device applications are deployed.

VM5 hosts Fledge server. You may follow [the official page](https://github.com/fledge-iot/fledge) for the installation. Pay attention on the version of the server OS since Fledge does not always support the newest releases and you may need to use an older version of the chosen OS. Afterwards, install the *http-south* plugin from the UI. In order to send sensor data from Edgex, we add a *http-south* service with the following configurations:
```
Host: 0.0.0.0
Port: 6683
URI: sensor-reading
Asset Name Prefix: edgex-
Enable: HTTP
HTTPS Port: -
Certificate Name: fledge
```
## :hammer: Building the containers
The microK8's local repository can be activated with `microk8s enable registry` command so that we can upload our locally build containers. 

Install docker if it is not available on VM1 or VM4 with `sudo snap install docker`

Then, the following commands can be used to build a docker image and upload it to the microK8's local repository from the related folders in [source_codes](source_codes)
```
# On gralaf folder 
sudo docker build -f Dockerfile-gralaf -t localhost:32000/gralaf:0.0.1 .
sudo docker push localhost:32000/gralaf:0.0.1
# On load-generator folder
sudo docker build -f Dockerfile-gralaf -t localhost:32000/load-generator:0.0.1 .
sudo docker push localhost:32000/load-generator:0.0.1
# On mock-lasm-server folder
sudo docker build -f Dockerfile-lasm-server -t localhost:32000/lasm-server:0.0.1 .
sudo docker push localhost:32000/lasm-server:0.0.1
# On virtual-iot-device folder for VM4
sudo docker build -f Dockerfile-mqtt-client -t localhost:32000/mqtt-client:0.0.1 .
sudo docker push localhost:32000/mqtt-client:0.0.1
```

## :wrench: Deployment

Following deployment instructions are valid for Ubuntu 22.04.

On all machines you want to have a kubernetes (VM1-3,VM4), install MicroK8s with `sudo snap install microk8s --classic`

Run `microk8s add-node` on VM1 which is going to be master node and follow the printed instructions. 
Note: You may need to add the ip address-hostname pair to /etc/hosts for the master node. 

**Example '/etc/hosts' file:**
```
127.0.0.1 localhost
10.0.11.2 vm1
10.0.11.13 vm2
10.0.11.15 vm3
...
```

On master node(VM1), activate required add-ons with `microk8s enable community istio dns metrics-server`

To have the Kubernetes Dashboard available (optionally), install the add-on with `microk8s enable dashboard`. 
To access it, run `microk8s dashboard-proxy` in the terminal, open your browser, navigate to `https://your_ip:10443/` and enter the key provided in the terminal.

In order to use **kubectl** instead of **microk8s.kubectl** `sudo snap alias microk8s.kubectl kubectl`

Edgex/GRALAF/Prometheus/Chaos Mesh can be deployed by using the helm charts with the given instructions available under [gralaf_infrastructure](helm_charts/gralaf_infrastructure).

Similarly, MQTT-based virtual IoT device applications can be deployed by using the helm charts with the given instructions available under [helm_iot](helm_charts/helm_iot).


<a id="1">[1]</a>  O. Kalinagac, W. Soussi, Yacine Anser, Chrystel Gaber, and G. Gür, "Root Cause and Liability Analysis in the Microservices Architecture for Edge IoT Services," [In progress]
