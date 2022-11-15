# GRALAF
Images:
onurklngc/load-generator:0.0.1
onurklngc/gralaf:0.0.1
onurklngc/mqtt_client:0.0.1
onurklngc/lasm-server:0.0.1 


```sh
microk8s.helm3 install gralaf  -n gralaf .
microk8s.helm3 delete gralaf -n gralaf
'''
