class ModifiedAggregation:
    """
    Modified Aggregation from an adjacency matrix and a list of values
    corresponding to the same ordering as the adjacency matrix.
    """
    def __init__(self, seed, agg):
        self.seed = seed
        self.agg = agg
        if seed <= agg:
            print("Seed threshold can't be smaller than aggregation threshold. Defaulting to 1 and 0.")
            self.seed = 1
            self.agg = 0

    def run(self, A, v):
        """
        Main loop that iteratively finds new clusters and calls spreading functions.
        """

        labels = np.zeros_like(v, dtype=np.int32)
        if A.shape[0] != v.shape[0]:
            print("Adjacency matrix must have same number of rows as values.")
            return labels

        count = 0
        tag_it = 1
        while(count < 1E6):
            seed_mask = v < seed
            limit_mask = labels != 0
            masked_data = ma.masked_array(v, mask = seed_mask | limit_mask)
            
            if np.all(masked_data.mask):  # Check if all elements are masked
                break
            max_index = masked_data.argmax()
            seed_mask[max_index] = True
            self.spread(A,v,max_index,labels,tag_it,agg)
            tag_it += 1
            count += 1
        return labels


    def spread(self,A,v,seed,labels,tag,agg):
        """
        Spread
        """
        spread_mask = A[seed] == 1
        spread_mask = np.zeros_like(labels).astype(bool)
        spread_mask[seed] = True
        
        # later make into while
        labels_temp = np.ones_like(labels)*-1
        count = 0
        while(count < 1E6):
            count += 1
            limit_mask = labels == 0

            if (labels_temp==labels).all():
                break        
            labels_temp = labels.copy()
            
            spread_to_idx = np.where(spread_mask)[0]
            for icell in spread_to_idx:
                self.spread_step(A,v,icell,spread_mask,labels,tag,agg)


    def spread_step(self,A,v,cell,spread_mask,labels,tag,agg):
        """
        Spread to neighbors and check value and agg threshold.
        Check A for neighbors, make a mask for already tagged.
        """

        limit_mask = labels == 0
        value_mask = v <= v[cell]
        agg_mask = v > agg
        mask = A[cell]
        final_mask = np.bitwise_and(mask, limit_mask & value_mask & agg_mask).astype(bool)

        # Tag
        labels[final_mask] = tag

        # Update spreading cells
        # This might not be efficient.
        spread_mask[final_mask] = True

