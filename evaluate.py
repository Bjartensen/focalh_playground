import ROOT
import pickle
from datetime import datetime
import sys
import copy
import yaml
import argparse
from typing import Any
import numpy as np
import optuna
from lib.modified_aggregation_clusterer import ModifiedAggregationClusterer
from lib.unet_clusterer import UNetClusterer
from lib.focal import FocalH
from lib import efficiency, coverage, vmeas, compute_score, average_energy,              count_clusters,count_labels
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from pathlib import Path

DATA = "analysis/data.yaml"
METHODS = "analysis/methods.yaml"
TRANSFORMATIONS = "analysis/transformations.yaml"
EVALUATION_DIRECTORY = "evaluation/"

def load_data(type):
    with open(DATA, "r") as file:
        config = yaml.safe_load(file)
    return config[type]

def open_bundle(filename):
    with open(filename, "rb") as f:
        loaded_bundle = pickle.load(f)
    loaded_bundle["load_path"] = filename
    return loaded_bundle

def run(data: Any, study: Any):
    print("Running evaluation")
    tags, labels, values, energy = handle_method(data, study)

    result = dict()

    print("Computing metrics...")

    # Compute different things
    # Efficiency
    eff = compute_score(tags, labels, values, "efficiency")
    vmeas = compute_score(tags, labels, values, "vmeasure")
    #vmeas_weighted = compute_score(tags, labels, values, "vmeasure_weighted")
    coverage = compute_score(tags, labels, values, "coverage")
    particles = compute_score(tags, labels, values, "count_labels")
    avg_energy = average_energy(energy)

    result["data"] = data
    result["study"] = study
    result["tags"] = tags
    result["labels"] = labels
    result["values"] = values
    result["efficiency"] = eff
    result["vmeasure"] = vmeas
    #result["vmeasure_weighted"] = vmeas_weighted
    result["coverage"] = coverage
    result["particles"] = particles
    result["avg_energy"] = avg_energy

    print("Done.")
    print("Saving...")

    now = datetime.now()
    timestamp = now.strftime("%d%m%Y_%H%M%S")
    filename = "eval_"+study["method"]["name"]+"_"+timestamp+".pkl"
    dir = EVALUATION_DIRECTORY

    with open(dir+filename, "wb") as f:
        pickle.dump(result, f)

    print("Saved.")


def handle_method(data: Any, study: Any):
    name = study["method"]["name"]
    print(f"Clustering with {name}")
    if name == "ma":
        pars = study["study"].best_params
        cluster = ModifiedAggregationClusterer()
        adj, values, labels, energy = cluster.data(data) # Should also return energy I think
        tags = cluster.cluster(pars["seed"], pars["agg"], adj, values)
        return tags, labels, values, energy
    elif name == "cnn":
        pars = study["study"].best_params
        cluster = UNetClusterer()
        events, targets, counts, mapping, labels, values, energy, adj = cluster.data(data)
        p = Path(study["load_path"])
        u = torch.load(str(p.parent)+"/"+study["model_file"], weights_only=False)
        tags = cluster.cluster(events, u, pars["seed"], pars["agg"], adj, labels, mapping)
        return tags, labels.squeeze().detach().numpy(), values.squeeze().detach().numpy(), energy
    elif name in ["hdbscan"]:
        pars = study["study"].best_params
        cluster = SklearClusterer()
        d = cluster.data(data)
        tags = cluster.cluster(data, trans[transformation_choice], method, **pars)
        pass
    else:
        return


def main():
    parser = argparse.ArgumentParser(description="Evaluate clustering method")
    parser.add_argument("--data", type=str, required=True, help="Dataset")
    parser.add_argument("--study", type=str, required=True, help="Clustering method")

    args = parser.parse_args()
    data = load_data(args.data)
    study = open_bundle(args.study)

    run(data, study)


if __name__ == "__main__":
    main()
