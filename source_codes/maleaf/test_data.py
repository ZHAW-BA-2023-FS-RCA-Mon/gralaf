import json
import logging
from datetime import datetime
from os import path

import pandas as pd
import yaml
from pandas import Series
import numpy as np

from anomaly_detection import discretize_with_trained_mode
from rca import get_step_data
from data_manipulation import filter_columns_by_inference_engine, remove_columns_unavailable_on_training_data, \
    remove_previously_deleted_columns
from generate_model import filter_data, get_raw_data
from lasm_utils import send_incident

logger = logging.getLogger(__name__)


def get_test_data_from_live_system(config):
    services_with_anomaly = {}
    row_dataframe = get_step_data(config, services_with_anomaly)
    return row_dataframe


def save_json_to_file(filename, data):
    with open(filename, "w") as outfile:
        json.dump(data, outfile, indent=2)


def read_json_from_file(filename):
    with open(filename, "r") as outfile:
        return json.load(outfile)


def print_row_with_discrete_value(series_data, discrete_values):
    table_text = "\n"
    for column, value in series_data.items():
        if isinstance(value, float):
            value = f"{value:.2f}"
        if column in discrete_values:
            value = f"{value} ({discrete_values[column]})"
        table_text += f"{column}\t{value}\n"
    logger.info(f"Row to be checked:{table_text}")


def check_metrics(config, trained_model, new_step_data, sla_data=None):
    query_results = {}
    analysis_start_time = datetime.now().strftime("%m/%d/%Y %H:%M:%S.%f")
    # logger.info(f"Row to be checked:\n{new_step_data}")
    for column in new_step_data.index.copy():
        try:
            if column.startswith("edgex"):
                new_step_data.pop(column)
        except:
            print("")
    metric_retrieval_time = new_step_data["timestamp"]
    if isinstance(metric_retrieval_time, datetime):
        metric_retrieval_time = metric_retrieval_time.strftime('%Y-%m-%d %H:%M:%S')
    new_step_data.pop("timestamp")
    discrete_test_step_data = new_step_data.copy()
    discrete_data_by_metric = discretize_with_trained_mode(new_step_data, trained_model)
    for metric, states in discrete_data_by_metric.items():
        for step_no, state in enumerate(states):
            if isinstance(discrete_test_step_data, Series):
                discrete_test_step_data[metric] = state
            else:
                discrete_test_step_data.loc[step_no, metric] = state
    discrete_test_step_data.astype("int32")
    print_row_with_discrete_value(new_step_data, discrete_test_step_data)
    # logger.info(f"Row to be checked after anomaly detection:\n{discrete_test_step_data}")

    discrete_test_step_data = discrete_test_step_data.to_dict()
    for node_name in trained_model.independent_nodes:
        if node_name in discrete_test_step_data:
            discrete_test_step_data.pop(node_name)
    delay_violations = {}
    availability_violations = {}
    for metric_name, state in discrete_test_step_data.items():
        if metric_name.startswith('availability') and state != 0:
            raw_value = new_step_data[metric_name]
            related_service_name = metric_name.lstrip("availability_")
            if related_service_name in sla_data and raw_value < sla_data[related_service_name]['availability']["min"]:
                availability_violations[related_service_name] = {
                    "violation_type": 'availability',
                    "reported_value": raw_value,
                    "expected_value": sla_data[related_service_name]['availability'],
                    "responsible_provider": sla_data[related_service_name]['provider']
                }
        elif metric_name.startswith('latency') and state != 0:
            raw_value = new_step_data[metric_name]
            related_service_name = "edgex" + metric_name.split("edgex")[-1]
            if related_service_name in sla_data and \
                    raw_value > sla_data[related_service_name]['max_service_delay']["max"]:
                delay_violations[related_service_name] = {
                    "violation_type": 'max_service_delay',
                    "reported_value": raw_value,
                    "expected_value": sla_data[related_service_name]['max_service_delay'],
                    "responsible_provider": sla_data[related_service_name]['provider']
                }

    rca_algorithm = config['rca_algorithm']
    if rca_algorithm in ('svm', 'random_forest'):
        data = np.array([], dtype=int)
        for column in trained_model.all_metrics:
            if column in discrete_test_step_data:
                data = np.append(data, discrete_test_step_data[column])
            else:
                data = np.append(data, 0)

        prediction = trained_model.structure_model.predict([data])[0]
        prediction_proba = trained_model.structure_model.predict_proba([data])[0]
        root_cause_analysis_time = datetime.now().strftime("%m/%d/%Y %H:%M:%S.%f")

        classes = np.array(trained_model.structure_model.classes_)
        predictions = []
        i = 0
        for class_ in classes:
            if class_ != "no_fault":
                service_name = class_[:-2]
                if not [x for x in predictions if x['service_name'] == service_name]:
                    predictions.append(
                        {"service_name": service_name, "probability": 0.0,
                         "fault_distribution": {}})
                for j in range(0, len(predictions)):
                    if predictions[j]['service_name'] == service_name:
                        predictions[j]['fault_distribution'][class_[-1]] = float(f"{prediction_proba[i]:.3f}")
                        break
            i = i + 1

        for i in range(0, len(predictions)):
            probability_of_service = 0.0
            for fault_type in predictions[i]['fault_distribution']:
                probability_of_service = probability_of_service + predictions[i]['fault_distribution'][fault_type]
            for fault_type in predictions[i]['fault_distribution']:
                if probability_of_service == 0:
                    predictions[i]['fault_distribution'][fault_type] =\
                        round(1 / len(predictions[i]['fault_distribution']), 3)
                else:
                    predictions[i]['fault_distribution'][fault_type] = \
                        round(predictions[i]['fault_distribution'][fault_type] / probability_of_service, 3)
            predictions[i]['probability'] = round(probability_of_service, 3)

        predictions = sorted(predictions, key=lambda i: i['probability'], reverse=True)
        result_table = "\n"
        for result in predictions:
            result_table += f"{result['service_name']}: {result['probability']} ({result['fault_distribution']})\n"
        logger.info(result_table)

        if prediction != 'no_fault':
            predicted_fault = int(prediction[-1])
            main_responsible_service_name = prediction[:-2]
            main_responsible_data = None
            if predicted_fault == 1 and main_responsible_service_name in delay_violations:
                main_responsible_data = delay_violations[main_responsible_service_name]
            elif predicted_fault == 4 and main_responsible_service_name in availability_violations:
                main_responsible_data = availability_violations[main_responsible_service_name]
            if main_responsible_data:
                data_to_send = {"violation_details": {"violation_time": metric_retrieval_time,
                                                      "violation_type": main_responsible_data['violation_type'],
                                                      "expected_value": main_responsible_data['expected_value'],
                                                      "reported_value": main_responsible_data['reported_value'],
                                                      "contract_info": {
                                                          "service": main_responsible_service_name.replace("_", "-"),
                                                          "responsible_provider":
                                                              main_responsible_data["responsible_provider"]
                                                      },
                                                      },
                                "root_causes": predictions,
                                "violation_evidence": discrete_test_step_data,
                                "root_cause_analysis_time": root_cause_analysis_time
                                }
                logger.info(f"Sending incident report...")
                logger.debug(f"Incident report:\n{data_to_send}")
                send_incident(data_to_send, config['lasm_server_urls'], config['reporting_identifier'])
        return {"predictions": predictions,
                "violation_time": metric_retrieval_time,
                "analysis_start_time": analysis_start_time,
                "root_cause_analysis_time": root_cause_analysis_time,
                "discrete_data": discrete_test_step_data,
                "raw_data": new_step_data.to_dict(),
                }

    elif rca_algorithm == 'cbn':
        for inference_engine in trained_model.inference_engines:
            partial_test_data = filter_columns_by_inference_engine(discrete_test_step_data, inference_engine)
            query_result = inference_engine.query(partial_test_data, parallel=True)
            query_results.update(query_result)
        predictions = []
        for metric, result in query_results.items():
            if metric.startswith("edgex"):
                fault_distribution = {}
                for fault_type, probability in result.items():
                    fault_distribution[int(fault_type)] = float(f"{probability:.3f}")
                fault_probability = 1 - result[0]
                if fault_probability > 0:
                    predictions.append(
                        {"service_name": metric, "probability": 1 - result[0],
                         "fault_distribution": fault_distribution})

        predictions = sorted(predictions, key=lambda i: i['probability'], reverse=True)
        result_table = "\n"
        for result in predictions:
            result_table += f"{result['service_name']}: {result['probability']} ({result['fault_distribution']})\n"
        logger.info(result_table)
        root_cause_analysis_time = datetime.now().strftime("%m/%d/%Y %H:%M:%S.%f")
        if predictions:
            main_responsible = predictions[0]
            main_responsible_data = None
            predicted_fault = sorted(main_responsible['fault_distribution'],
                                     key=main_responsible['fault_distribution'].get, reverse=True)[0]
            if predicted_fault == 1 and main_responsible['service_name'] in delay_violations:
                main_responsible_data = delay_violations[main_responsible['service_name']]
            elif predicted_fault == 4 and main_responsible['service_name'] in availability_violations:
                main_responsible_data = availability_violations[main_responsible['service_name']]
            if main_responsible_data:
                data_to_send = {"violation_details": {"violation_time": metric_retrieval_time,
                                                      "violation_type": main_responsible_data['violation_type'],
                                                      "expected_value": main_responsible_data['expected_value'],
                                                      "reported_value": main_responsible_data['reported_value'],
                                                      "contract_info": {
                                                          "service": main_responsible['service_name'].replace("_", "-"),
                                                          "responsible_provider":
                                                              main_responsible_data["responsible_provider"]
                                                      },
                                                      },
                                "root_causes": predictions,
                                # "metrics": raw_test_data.to_dict(),
                                "violation_evidence": discrete_test_step_data,
                                "root_cause_analysis_time": root_cause_analysis_time
                                }
                logger.info(f"Sending incident report...")
                logger.debug(f"Incident report:\n{data_to_send}")
                send_incident(data_to_send, config['lasm_server_urls'], config['reporting_identifier'])
        return {"predictions": predictions,
                "violation_time": metric_retrieval_time,
                "analysis_start_time": analysis_start_time,
                "root_cause_analysis_time": root_cause_analysis_time,
                "discrete_data": discrete_test_step_data,
                "raw_data": new_step_data.to_dict(),
                }
    else:
        logger.error('rca algorithm not specified')


def test_stored_data(config, trained_model, training_completion_time=None, training_dataset_tag=None, sla_data=None):
    start_row = 0
    all_test_data, test_dataset_tag = get_raw_data(config, is_test_data=True)
    if training_dataset_tag:
        test_dataset_tag = f"{training_dataset_tag}_{test_dataset_tag}"
    # if config["test_false_positive"]:
    #     test_dataset_tag += "_false_positive"
    record_filename = f"{config['output_folder']}/{test_dataset_tag}_{config['rca_algorithm']}.json"
    if path.exists(record_filename):
        all_results = read_json_from_file(record_filename)
        start_row = len(all_results["test_results"])
    else:
        all_results = {"training_completion_time": training_completion_time, "test_results": []}
    all_test_data = filter_data(config, all_test_data)
    all_test_data.columns = all_test_data.columns.str.replace('-', '_')
    all_test_data = remove_columns_unavailable_on_training_data(all_test_data, trained_model.training_data)
    for index, test_step in all_test_data.iterrows():
        logger.info(f"Test step #{index}")
        if index < start_row:
            continue
        actual_faulty_service_columns = [col for col in all_test_data if
                                         col.startswith('edgex') and test_step[col] != 0]
        actual_results = test_step[actual_faulty_service_columns]
        test_step = remove_previously_deleted_columns(test_step)
        results = check_metrics(config, trained_model, test_step, sla_data=sla_data)
        results["actual_results"] = actual_results.to_dict()
        all_results["test_results"].append(results)
        if not actual_results.empty:
            logger.info(f"Actual results:\n{actual_results.to_string()}\n")
        else:
            logger.info("There was no fault injection")
        save_json_to_file(record_filename, all_results)
    logger.info("Completed testing the given dataset")
    return all_results


if __name__ == '__main__':
    with open('config.yaml') as f:
        config_from_yaml = yaml.load(f, Loader=yaml.FullLoader)
    len_second = 60
    initial_data_file_name = "dataset/training_data_20220506-120819.csv"
    training_data = pd.read_csv(initial_data_file_name)
    test_data = get_test_data_from_live_system(config_from_yaml)
    print(test_data)
