## Deployment of Edgex

Create a namespace with: `kubectl create namespace edgex`

Set the namespace for istio proxy injection `microk8s.kubectl label namespace edgex istio-injection=enabled`

Set FledgeSouthHTTPEndpoint parameter in [data exporter config file](helm_charts/gralaf_infrastructure/helm_edgex/templates/edgex-exporter-fledge/edgex-exporter-fledge-configmap.yaml) to the IP address of VM5 which hosts Fledge server. 

In helm_edgex directory, use `microk8s.helm3 install edgex-jakarta -n edgex .` to deploy edgex.

You can uninstall it with `microk8s.helm3 delete edgex-jakarta -n edgex
`
## Deployment of GRALAF

Create a namespace with: `kubectl create namespace gralaf`

Use the following commands to install/uninstall GRALAF
```
microk8s.helm3 install gralaf -n gralaf .
microk8s.helm3 delete gralaf -n gralaf
```

## Deployment of Other Components
Install microk8s-compatible chaos mesh tool with `curl -sSL https://mirrors.chaos-mesh.org/v2.3.0/install.sh | bash -s -- --microk8s`

Install pre-configured Prometheus with `kubectl apply -f edgex-prometheus.yaml`

For some extra monitoring metrics, install metrics-server with  `kubectl apply -f edgex-metrics-server.yaml`

Optionally, you may install Grafana with `kubectl apply -f edgex-grafana.yaml`

Optionally, you may install Kiali with `microk8s.helm3 install --namespace istio-system --set auth.strategy="anonymous" --repo https://kiali.org/helm-charts kiali-server `

