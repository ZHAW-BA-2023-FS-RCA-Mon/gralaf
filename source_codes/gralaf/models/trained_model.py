import logging
import pickle
import time
from os import path

import networkx as nx
from causalnex.inference import InferenceEngine
from causalnex.network import BayesianNetwork
from causalnex.plots import NODE_STYLE, plot_structure, EDGE_STYLE
from causalnex.structure.notears import from_pandas

# EXPERIMENTS_SKIPPED = {"cpu": 2, "memory": 3, "availability": 4}
# METRICS_SKIPPED = ["cpu", "error", "memory", "availability"]
logger = logging.getLogger(__name__)
CB_COLOR_CYCLE = ['#377eb8', '#ff7f00', '#4daf4a',
                  '#f781bf', '#a65628', '#984ea3',
                  '#999999', '#e41a1c', '#dede00']
# TABU_PARENTS = ["edgex_ui", 'edgex-exporter-fledge', 'edgex-support-scheduler']


class TrainedModel:

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
        logger.info("Starting to construct cbn structure model...")
        if not dataset_tag:
            filename = time.strftime("%Y%m%d_%H%M%S") + "_cbn"
        else:
            filename = dataset_tag + "_cbn"
        if path.exists(f"structure_models/{filename}.pickle"):
            self.structure_model = TrainedModel.read_from_file(f"structure_models/{filename}.pickle")
        else:
            self.structure_model = self.learn_from_data(config, training_data)
            TrainedModel.save_data_to_file(self.structure_model, filename=f"structure_models/{filename}.pickle")
        logger.info(f"Number of edges: {len(self.structure_model.edges)}")
        # self.structure_model.remove_edges_below_threshold(0.01)
        self.remove_weak_edges_from_nodes_with_many_edges(config)
        logger.info(f"Number of edges after edge removal: {len(self.structure_model.edges)}")
        self.remove_independent_nodes()
        self.save_cbn_graph(self.structure_model, filename=filename)
        logger.info("Structure model is constructed.")
        logger.info("Starting to construct inference engine...")
        self.inference_engines = self.get_inference_engines(self.structure_model, training_data)
        logger.info("Training complete.")

    def remove_independent_nodes(self):
        independent_nodes = []
        for (node_name, degree) in self.structure_model.degree:
            if degree < 1:
                independent_nodes.append(node_name)
        self.independent_nodes = independent_nodes
        for node_name in independent_nodes:
            self.structure_model.remove_node(node_name)
        logger.info(f"Removing the following independent nodes from SM: {independent_nodes}")

    def remove_weak_edges_from_nodes_with_many_edges(self,config):
        edges_to_remove = []
        for node_name, parents in self.structure_model.pred.items():
            edge_weights = {}
            for parent_name, edge_data in parents.items():
                edge_weights[parent_name] = edge_data["weight"]

            edges_sorted = sorted(edge_weights, key=edge_weights.get, reverse=True)
            for parent_name in edges_sorted[config["min_number_of_edges_per_node"]:]:
                if edge_weights[parent_name] < config["weak_link_threshold"]:
                    edges_to_remove.append((parent_name, node_name))
                    # edges_to_remove.append((node_name,parent_name))
        logger.info(f"Removing the following {len(edges_to_remove)} edges from SM: {edges_to_remove}")
        for edge_name in edges_to_remove:
            self.structure_model.remove_edge(*edge_name)

    def get_inference_engines(self, structure_model, training_data):
        inference_engines = []

        self.partial_structure_models = []
        for component in nx.weakly_connected_components(structure_model):
            partial_sm = structure_model.copy()
            for node in structure_model.nodes:
                if node not in component:
                    partial_sm.remove_node(node)
            self.partial_structure_models.append(partial_sm)
            logger.info(f"{len(component)} -> {component}")
        for partial_sm in self.partial_structure_models:
            bn = BayesianNetwork(partial_sm)
            bn.fit_node_states(training_data)
            bn = bn.fit_cpds(training_data, method="BayesianEstimator", bayes_prior="K2")
            ie = InferenceEngine(bn)
            inference_engines.append(ie)
        return inference_engines

    @staticmethod
    def learn_from_data(config, training_dataframe):
        service_statuses = []
        tabu_edges = []
        # for tabu_node in TABU_PARENTS:
        #     tabu_node = tabu_node.replace("-", "_")
        #     if tabu_node not in training_dataframe.columns and f"{tabu_node}_delay" not in training_dataframe.columns:
        #         continue
        # for column in training_dataframe.columns:
        #     if (column.startswith("availability") or column.startswith("memory")) and tabu_node not in column:
        #         tabu_edge = (f"availability_{tabu_node}", column)
        #         tabu_edges.append(tabu_edge)
        # for service_name_1 in SERVICES_FOR_FAULT_INJECTION:
        #     memory_metric_name_1 = f"memory_{service_name_1}".replace("-", "_")
        #     if memory_metric_name_1 in training_dataframe.columns:
        #         for service_name_2 in SERVICES_FOR_FAULT_INJECTION:
        #             memory_metric_name_2 = f"memory_{service_name_2}".replace("-", "_")
        #             if memory_metric_name_2 in training_dataframe.columns and service_name_1 != service_name_2:
        #                 tabu_edge = (memory_metric_name_1, memory_metric_name_2)
        #                 tabu_edges.append(tabu_edge)

        for service_name in config["services_for_fault_injection"]:
            service_name = service_name.replace('-', '_')
            service_statuses.extend([service_name, f"{service_name}_delay", f"{service_name}_cpu",
                                     f"{service_name}_memory", f"{service_name}_failure"])
        for service_status in service_statuses.copy():
            if service_status not in training_dataframe.columns:
                service_statuses.remove(service_status)
        all_metrics = list(set(training_dataframe.columns) - set(service_statuses))
        sm = from_pandas(training_dataframe, tabu_child_nodes=service_statuses, tabu_parent_nodes=all_metrics,
                         tabu_edges=tabu_edges, max_iter=1000)
        n_components = nx.number_weakly_connected_components(sm)
        logger.info(f"Number of independent subgraphs: {n_components}")
        return sm

    @staticmethod
    def save_cbn_graph(sm, filename=None):
        if filename is None:
            filename = time.strftime("%Y%m%d-%H%M%S")
        node_attributes = {
            node: {
                "shape": "hexagon",
                "width": 10,
                "height": 3.5,
                "fillcolor": "#000000",
                "penwidth": "7",
                "color": "#4a90e2d9",
                "fontsize": 70,
                "labelloc": "c",
            }
            for node in sm.nodes
        }
        for node in sm.nodes:
            node_attributes[node]["label"] = node.replace("_edgex_", "\n").replace("edgex_", "")
            if node.startswith("edgex"):
                node_attributes[node]["fillcolor"] = "#00ffff"
            elif node.startswith("cpu"):
                node_attributes[node]["fillcolor"] = CB_COLOR_CYCLE[0]
            elif node.startswith("latency"):
                node_attributes[node]["fillcolor"] = "#8be04e"
            elif node.startswith("memory"):
                node_attributes[node]["fillcolor"] = "#a65628"
            elif node.startswith("availability"):
                node_attributes[node]["fillcolor"] = "#bc5090"
            elif node.startswith("error"):
                node_attributes[node]["fillcolor"] = "#377eb8"
        edge_attributes = {
            (u, v): {
                "penwidth": w * 60 + 0.5,  # Setting edge thickness
                # "weight": int(5 * w),  # Higher "weight"s mean shorter edges
                "arrowsize": 2.5 + w,
                "arrowtail": "dot",
                "color": "orange"
            }
            for u, v, w in sm.edges(data="weight")
        }
        all_node_attributes = NODE_STYLE.STRONG.copy()
        all_node_attributes.update({"color": "black", "fontcolor": "black"})
        viz = plot_structure(
            sm,
            graph_attributes={"scale": "0.9", "bgcolor": "white", "dpi": "82", "fontcolor": "black", "pad": "1,0.8", },
            all_node_attributes=all_node_attributes,
            all_edge_attributes=EDGE_STYLE.WEAK,
            node_attributes=node_attributes,
            edge_attributes=edge_attributes,
            prog="circo",
        )

        viz.draw(format='svg', path=f'cbn_graph/cbn_map_{filename}.svg')
        # with open("cbn_map.svg", "wb+") as file:
        #     pass
        all_node_attributes
        pass

    @staticmethod
    def save_data_to_file(data, filename="sm_cbn.pickle"):
        logger.info(f"Saving model to {filename}")
        with open(filename, "wb+") as sm_file:
            pickle.dump(data, sm_file)

    @staticmethod
    def read_from_file(filename="sm_cbn.pickle"):
        logger.info(f"Reading model from {filename}")
        with open(filename, "rb") as sm_file:
            return pickle.load(sm_file)
