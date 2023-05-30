## Run locally with example training data set

A example training data set is provided: [training data set](./dataset/training_data_20230521-202044.csv)

This training data set can be used to train the model. In the [config file](./config.yaml#L23) the correct training data set must be provided.
The correct IP must be specified for the configs `prometheus_url` and `lasm_server_urls`.

With the config `use_archive = false` the "live" mode is started and experiments with the chaos mesh dashboard can be injected. This results in a root cause analysis which is sent to the lasm server.

With the config `use_archive = true` and a valid test data set in the config file, the "test" mode is started.

To start just run the [main](./main.py) file.


