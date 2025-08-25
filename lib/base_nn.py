import ROOT # Segmentation error when imported after some of the others... Insanity.
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import KDTree
from scipy.interpolate import griddata, NearestNDInterpolator


class Data(): # or DataLoader, DataTransformer?
    """
    I need something to read the Generic ttree format.
    It needs to be able to transform the 249 heatmap to a 21-by-21 upscaled.
    Functions:
        read
        upscale (as 21x21 image)
        spline(order)
    Maybe it is a good idea to transform it into the coordinate arrays:
        (N,441,3) for x,y,val
    Need to define geometry again to know what module is which when upscaling
    But simple this time. All 7x7, center as-is and outer upscaled. Need bounded regions to classify.
    """
    def __init__(self):
        # Points from simulation
        self.x_min = -8.773864
        self.x_max = 8.773864
        self.y_min = -8.689269
        self.y_max = 8.785495
        self.xy_bounds = [self.x_min, self.x_max, self.y_min, self.y_max]


    """
    General methods
    """
    def center_of_masses(self, x, y, val, labels, fracs, threshold=0):
        """
        A function to return center of masses from original data.
        """
        Nparticles = labels.max() # Assumes 1..N particle exist and no gap
        coms = np.zeros(Nparticles*2).reshape(Nparticles,2)
        for i in range(1, Nparticles+1):
            v = self.reconstruct_single_particle(val, labels, fracs, i)
            coms[i-1][0] = self.com(x,v,threshold)
            coms[i-1][1] = self.com(y,v,threshold)
        return coms


    def get_major_labels(self, labels, fractions, particles):
        fractions_stack = fractions.reshape(particles, -1, order='F').T
        major_label_mask = np.argmax(fractions_stack, axis=1)
        nplabmaj = labels[major_label_mask]
        return nplabmaj


    def com(self, dim, val, threshold=False):
        """
        Center of mass calculation. With the option
        of "correcting" the effect of everything being
        dragged towards the origin.
        """
        if threshold > 0:
            mask = val >= val.max() * threshold
            val = val[mask]
            dim = dim[mask]
        tot = val.sum()
        if tot == 0:
            return 0
        return np.dot(dim, val)/val.sum()


    def reconstruct_single_particle(self, val, labels, fracs, particle_num):
        """
        From fractional contributions, reconstruct the Nth particle.
        """
        mask = labels == particle_num
        return val * fracs[mask]



    """
    Tensor and image transformations
    """
    def to_training_tensor(self, ttree):
        """
        Convert to images, gaussian class activation maps and other stuff
        """
        entries = ttree.GetEntries()
        print(f"Converting {entries} events...")
        image_list = []
        count_list = []
        target_list = []
        mapping_list = []
        dlabels_list = []

        for i in range(entries):
            try:
                ret, coms, dlabels, mapping = self.read_ttree_event(ttree, i)
                target = self.gaussian_class_activation_map(coms, 21, 21, 3)
                count = torch.tensor(len(coms), dtype=torch.float32).unsqueeze(0).unsqueeze(0)
            except RuntimeError:
                # TO-DO: Fix the edge cases of gaussians
                continue
            count_list.append(count)
            image_list.append(ret)
            target_list.append(target)
            mapping_list.append(torch.from_numpy(mapping).unsqueeze(0).unsqueeze(0))
            dlabels_list.append(torch.from_numpy(dlabels).unsqueeze(0).unsqueeze(0))

        image_tensor = torch.cat(image_list, dim=0)
        target_tensor = torch.cat(target_list, dim=0)
        count_tensor = torch.cat(count_list, dim=0)
        mapping_tensor = torch.cat(mapping_list, dim=0)
        dlabels_tensor = torch.cat(dlabels_list, dim=0)

        data = {
            "event": image_tensor,
            "target": target_tensor,
            "count" : count_tensor,
            "mapping": mapping_tensor,
            "dlabels": dlabels_tensor,
            "metadata": {"version": 1},
        }

        return data

    def read_ttree_event(self, ttree, event, print_heatmap=False):
        """
        Read an event of generic format and transform into image tensor.
        """

        ttree.GetEntry(event)
        npx = np.array(ttree.x, dtype=np.float32)
        npy = np.array(ttree.y, dtype=np.float32)
        npval = np.array(ttree.value, dtype=np.float32)
        npfracs = np.array(ttree.fractions, dtype=np.float32)
        nplabels = np.array(ttree.labels, dtype=np.int32)

        coms = self.center_of_masses(npx, npy, npval, nplabels, npfracs, 0.75)
        npdlabels = self.get_major_labels(nplabels, npfracs, len(coms))

        # And mapping
        event_tensor, mapping = self.generic_to_tensor(npx,npy,npval)


        #fig, ax = plt.subplots()
        #self.plot_tensor_physical(event_tensor[0][0], xy_extent=None, ax=ax)
        #ax.scatter(coms[:,0], coms[:,1], marker="x", s=200, linewidths=1)
        #fig.savefig("tensor_physical_com.png", bbox_inches="tight")

        # Use get_major_labels

        # Labels and mapping

        return event_tensor, coms, npdlabels, mapping


    def gaussian_class_activation_map(self, points, img_x_dim, img_y_dim, kernel_size=3):
        """
        Function to return a gaussian N-by-N blob centered at x,y
        that can be added to an empty image.
        Must somehow map x,y coordinates to image indices.
        Want it to work for generic image dimensions.
        From image and bounds, map to indices?
        Given some boundary, divide into dimensions pieces and pick closest?
        Just make the image here? From image dimension.
        """
        empty_tensor = torch.zeros((img_x_dim, img_y_dim))
        offset = kernel_size//2 # Integer division
        for p in points:
            col = self.coord_to_pixel(p[0], self.x_min, self.x_max, img_x_dim)
            row = self.coord_to_pixel(p[1], self.y_min, self.y_max, img_y_dim, flip=True)

            # TO-DO: Bounds checking
            # Tried bounds checking by I can't get it to work...
            # Need to look at it again with a clearer head and some pen and paper
            xlow = col if col-offset < 0 else offset
            xhigh = img_x_dim-col if col+offset > img_x_dim else offset+1
            ylow = row if row-offset < 0 else offset
            yhigh = img_y_dim-row if row+offset > img_y_dim else offset+1

            g = self.gaussian_kernel(kernel_size)
            empty_tensor[row-offset:row-offset+kernel_size, col-offset:col-offset+kernel_size] += g

        saturated = empty_tensor >= 1
        empty_tensor[saturated] = 1

        # batch shape
        empty_tensor = empty_tensor.unsqueeze(0).unsqueeze(0)
        return empty_tensor


    def gaussian_kernel(self, size, sigma=1):
        """
        Create a size-by-size gaussian kernel.
        """
        ax = torch.linspace(-(size - 1)/2., (size - 1)/2., size)
        xx, yy = torch.meshgrid(ax, ax, indexing="ij")
        kernel = torch.exp(-(xx**2 + yy**2)/(2*sigma**2))
        return kernel

    def coord_to_pixel(self, point, minimum, maximum, image_dimension, flip=False):
        """
        Map a floating point coordinate to a pixel.
        Expects the image to have origin at top-left.
        Flip for y if an image (origin is top-left commonly).
        """
        dim = np.linspace(minimum, maximum, image_dimension)
        if flip:
            dim = np.flip(dim)
        return np.argmin(np.abs(dim - point))


    def generic_to_tensor(self,x,y,val):
        """
        Transform the generic data to tensor format.
        """

        # This should be set somewhere else
        MIN = 0
        MAX = 4095 # Or 4096??
        # Cutting saturation in original data
        print(val.max())
        saturated_orig = val >= MAX
        val[saturated_orig] = MAX
        print(val.max())

        # Interpolating
        new_dim = 21
        inter = self.interpolate(x, y, val, new_dim)

        # Scaling and normalizing
        orig_sum = val.sum()
        negatives = inter[2] < 0
        inter[2][negatives] = 0
        interpolated_sum = inter[2].sum()
        scaled_interpolated_values = inter[2]*(orig_sum/interpolated_sum)
        normalized_scaled_interpolated_values = scaled_interpolated_values/scaled_interpolated_values.max()
        normalized_scaled_interpolated_values = np.flipud(normalized_scaled_interpolated_values.T).copy()
        tensor_values = torch.tensor(normalized_scaled_interpolated_values, dtype=torch.float32)
        tensor_values = tensor_values.unsqueeze(0).unsqueeze(0)

        # Could change to take ttree and entry, do interpolation and plot
        #self.print_interpolation(x,y,val,inter[0].flatten(),inter[1].flatten(),inter[2].flatten())

        # Return mapping as well
        return tensor_values, inter[5]


    def interpolate(self,x,y,val,new_size):
        """
        Interpolate as third-order spline.
        """

        width = 19.5
        dx = width/new_size
        edge = 0
        min_x = x.min()+edge# -width/2 + dx
        max_x = x.max()-edge# width/2 - dx
        min_y = y.min()+edge# -width/2 + dx
        max_y = y.max()-edge# width/2 - dx
        grid_x, grid_y = np.mgrid[min_x:max_x:new_size*1j, min_y:max_y:new_size*1j]
        interpolated_values = griddata((x, y), val, (grid_x, grid_y), method='cubic')


        # Secondary interpolation for the edges where spline fails
        nan_positions = np.isnan(interpolated_values)
        if np.any(nan_positions):
            nearest_interp = NearestNDInterpolator((x, y), val)
            nearest_values = nearest_interp(grid_x[nan_positions], grid_y[nan_positions])
            interpolated_values[nan_positions] = nearest_values

        # Do KDTree mapping to closest points and return mapping and original points
        points = np.column_stack((x,y))
        ktree = KDTree(points)
        _, mapping = ktree.query(np.column_stack((grid_x.ravel(), grid_y.ravel())))
        # ALWAYS use on old points

        #fig, ax = plt.subplots(ncols=2, figsize=(10,5))
        #ax[0].scatter(grid_x.ravel(), x.ravel()[mapping])
        #ax[0].set_xlabel("Interpolated x points")
        #ax[0].set_ylabel("Original x points")
        #ax[1].scatter(grid_y.ravel(), y.ravel()[mapping])
        #ax[1].set_xlabel("Interpolated y points")
        #ax[1].set_ylabel("Original y points")
        #fig.tight_layout()
        #fig.savefig("inverse_points.png", bbox_inches="tight")

        return grid_x, grid_y, interpolated_values, x, y, mapping


    def invert_labels(self, highd_l, mapping, values, dim):
        """
        I think I need a function to map to original labels.
        It will take new labels and mapping, and when it gets
        mapped to more than one then choose the highest intensity
        pixel.
        """
        lowd_l = np.zeros(dim)
        for i in range(dim):
            mask = (mapping == i)
            if np.any(mask):
                best_idx = np.argmax(values[mask])
                lowd_l[i] = highd_l[mask][best_idx]
        return lowd_l


    def map_highd_to_lowd(lowd_l, highd_l, mapping, value):
        for i in range(len(lowd_l)):
            mask = (mapping == i)
            if np.any(mask):
                best_idx = np.argmax(value[mask])
                lowd_l[i] = highd_l[mask][best_idx]
        return lowd_l

    """
    Other transformations
    Because they may vary in number of points, they can't all be added
    to a large higher dimensional array. They must be added to lists
    or the clustering algorithms call the transformations each time.
    """
    def transform_multiply(self, x, y, z, factor, width):
        """
        Multiply the x,y points dependent on the intensity + noise .
        """

        # Have some issues with negative (???) or zero values
        try:
            z = (factor*z/z.max()).astype(int)
        except ValueError:
            z = z.astype(int)
        mask = z <= 0
        z[mask] = 1

        x = np.repeat(x, z) + width*np.random.rand(z.sum())-0.5
        y = np.repeat(y, z) + width*np.random.rand(z.sum())-0.5

        # If I want to normalize, I have to compute the mapping before.

        return x,y

    def transform_3d(self, x, y, z, scale):
        pass

    def transform_cutoff(self, x, y, z, threshold):
        pass


    """
    Plotting functions
    """
    def print_interpolation(self, x, y, val, xi, yi, vali):
        mask = np.isnan(vali)

        fig, ax = plt.subplots()
        ax.scatter(xi[mask], yi[mask], color="red", marker="s", alpha=0.5)
        ax.scatter([], [], color="red", marker="s", label="nans")
        ax.scatter(xi[~mask], yi[~mask], alpha=vali[~mask]/vali[~mask].max(), s=(vali[~mask]/vali[~mask].max())*80, color="green")
        ax.scatter([], [], color="green", label="interpolated")
        ax.scatter(x, y, alpha=val/val.max(), s=(val/val.max())*80, color="blue")
        ax.scatter([], [], color="blue", label="original")
        ax.set_xlabel("x [cm]")
        ax.set_ylabel("y [cm]")
        ax.set_aspect("equal")
        ax.legend()
        fig.savefig("interpolation_weighted.png")

        fig, ax = plt.subplots()
        ax.scatter(xi[mask], yi[mask], color="red")
        ax.scatter([], [], color="red", label="nans")
        ax.scatter(xi[~mask], yi[~mask], color="green")
        ax.scatter([], [], color="green", label="interpolated")
        ax.scatter(x, y, color="blue")
        ax.scatter([], [], color="blue", label="original")
        ax.set_xlabel("x [cm]")
        ax.set_ylabel("y [cm]")
        ax.set_aspect("equal")
        ax.legend()
        fig.savefig("interpolation.png")


    def plot_tensor_physical(self, T, xy_extent=None, ax=None):
        if xy_extent is None:
            xy_extent = self.xy_bounds

        if ax is None:
            fig, ax = plt.subplots()

        ax.imshow(T, cmap="hot", extent=xy_extent)
        #ax.colorbar()  # Add a colorbar to show the scale
        ax.set_xlabel("x [cm]")
        ax.set_ylabel("y [cm]")
        ax.set_title("Heatmap")
        ax.set_aspect("equal")


    def plot_tensor_image(self, T, ax=None):
        """
        Plotting the raw tensor values as imshow
        """
        if ax is None:
            fig, ax = plt.subplots()
        ax.imshow(T, cmap="hot")
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])

    def remap(self):
        """
        Probably want a function to remap tensor results or something to original data for evaluation.
        """
        pass

def squawk():
    print("Base NN module.")
