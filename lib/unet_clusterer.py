import ROOT
from lib.modified_aggregation import ModifiedAggregation
import lib.base_nn as BNN
import lib.unet_nn as UNet
import torch
import numpy as np


class UNetClusterer:
    def __init__(self):
        # Reference 
        pass

    def data(self, config):

        files = config["files"]
        Nfiles = len(files)
        event_list = []
        target_list = []
        count_list = []
        mapping_list = []
        dlabel_list = []
        values_list = []
        energy_list = []
        dataloader = BNN.Data()
        for file in files:
            tfile = ROOT.TFile(file["path"], "READ")
            ttree = tfile.Get("EventsTree")
            data = dataloader.to_training_tensor(ttree)
            event_list.append(data["event"])
            target_list.append(data["target"])
            count_list.append(data["count"])
            mapping_list.append(data["mapping"])
            dlabel_list.append(data["dlabels"])
            values_list.append(data["values"])
            for e in data["energy"]:
                energy_list.append(e)

        events = torch.cat(event_list)
        targets = torch.cat(target_list)
        counts = torch.cat(count_list)
        mapping = torch.cat(mapping_list)
        dlabels = torch.cat(dlabel_list)
        values = torch.cat(values_list)

        adj = np.load("p2_image_adj_21x21.npy")

        return events, targets, counts, mapping, dlabels, values, energy_list, adj


    def event_data(self, ttree, event):
        """
        Prepare data for single event.
        """
        pass


    def cluster(self, events, unet_model, ma_seed, ma_agg, adj, labels, mapping):
        x = unet_model(events)
        ma = ModifiedAggregation(seed=ma_seed, agg=ma_agg)
        dataloader = BNN.Data()
        Ncells = labels.shape[2]
        Nentries = len(x)
        tags = np.zeros(Nentries*Ncells, dtype=np.int32).reshape(Nentries,Ncells)
        for i in range(Nentries):
            vals = x[i][0].flatten().detach().numpy()
            clusters,_ = ma.run(adj, vals)
            lab = dataloader.invert_labels(clusters, mapping[i][0].detach().numpy(), vals, Ncells)
            tags[i] = lab
        return tags
