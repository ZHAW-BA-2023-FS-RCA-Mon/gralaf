import logging
import os
import pickle
import time
import random

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import export_graphviz

logger = logging.getLogger(__name__)


class TrainedModelRandomForest:

    def __init__(self, config, clustering_instances, sort_indices, normalization_factors, training_data,
                 mean_ground_truth_values, dataset_tag=None):
        self.partial_structure_models = None
        self.independent_nodes = []
        self.normalization_factors = normalization_factors
        self.sort_indices = sort_indices
        self.clustering_instances = clustering_instances
        self.training_data = training_data
        self.mean_ground_truth_values = mean_ground_truth_values
        self.dataset_tag = dataset_tag
        self.all_service_statuses = self.get_all_service_statuses(config, training_data)
        self.all_metrics = list(training_data.drop(columns=self.all_service_statuses))
        logger.info("Starting to construct random forest structure model...")
        if not dataset_tag:
            filename = time.strftime("%Y%m%d_%H%M%S") + "_random_forest"
        else:
            filename = dataset_tag + "_random_forest"
        if os.path.exists(f"structure_models/{filename}.pickle"):
            self.structure_model = TrainedModelRandomForest.read_from_file(f"structure_models/{filename}.pickle")
        else:
            self.structure_model = self.learn_from_data(config, training_data, self.all_service_statuses)
            TrainedModelRandomForest.save_data_to_file(self.structure_model,
                                                       filename=f"structure_models/{filename}.pickle")
            self.save_example_tree(config, self.structure_model,
                                   training_data.drop(columns=self.all_service_statuses).columns, filename=filename)
        logger.info("Structure model is constructed.")
        logger.info("Training complete.")

    @staticmethod
    def get_all_service_statuses(config, training_dataframe):
        service_statuses = []

        for service_name in config["services_for_fault_injection"]:
            service_name = service_name.replace('-', '_')
            service_statuses.extend([service_name, f"{service_name}_delay", f"{service_name}_cpu",
                                     f"{service_name}_memory", f"{service_name}_failure"])
        for service_status in service_statuses.copy():
            if service_status not in training_dataframe.columns:
                service_statuses.remove(service_status)
        return set(service_statuses)

    @staticmethod
    def learn_from_data(config, training_dataframe, all_service_statuses):
        Y = []
        for i in range(config["number_of_initial_steps"]):
            Y = np.append(Y, 'no_fault')

        for index, row in training_dataframe.iterrows():
            for service_status in all_service_statuses.copy():
                fault_status = row[service_status]
                if fault_status != 0:
                    Y = np.append(Y, (service_status + '_' + str(fault_status)))

        X = training_dataframe.drop(columns=all_service_statuses)

        classifier = RandomForestClassifier(n_estimators=config["number_of_trees"],
                                            random_state=config["random_state_rf"])
        classifier.fit(X, Y)

        matched = 0
        for index, row in X.iterrows():
            actual = Y[index]
            predicted = classifier.predict([row.values])
            match = actual == predicted
            if match:
                matched += 1
            logger.info('actual: ' + str(actual) + ', predicted: ' + str(predicted) + ', its match: ' + str(match))

        accuracy = matched / int(config["number_of_training_data"])
        logger.info('accuracy: ' + str(accuracy) + ' for rows: ' + str(config["number_of_training_data"]))
        return classifier

    @staticmethod
    def save_example_tree(config, sm, feature_names, filename=None):
        tree_to_export = random.randrange(0, config["number_of_trees"] - 1)
        if filename is None:
            filename = time.strftime("%Y%m%d-%H%M%S")
        filename = f'{filename}_tree_{tree_to_export}'
        export_graphviz(sm.estimators_[tree_to_export], feature_names=feature_names.array,
                        out_file=f'random_forest_tree/{filename}.dot', filled=True, rounded=True)
        os.system(f'dot -Tpng random_forest_tree/{filename}.dot -o random_forest_tree/{filename}.png')

    @staticmethod
    def save_data_to_file(data, filename="sm_random_forest.pickle"):
        logger.info(f"Saving model to {filename}")
        with open(filename, "wb+") as sm_file:
            pickle.dump(data, sm_file)

    @staticmethod
    def read_from_file(filename="sm_random_forest.pickle"):
        logger.info(f"Reading model from {filename}")
        with open(filename, "rb") as sm_file:
            return pickle.load(sm_file)
