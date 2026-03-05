import numpy as np
import cv2

def depth_rmse(predicted_depth, ground_truth_depth_value):
    #Compute RMSE for a depth map against a flat wall of known distance

    predicted_depth = np.array(predicted_depth, dtype=np.float32)
    actual_depth = np.full_like(predicted_depth, fill_value = ground_truth_depth_value)

    # Compute the squared differences
    squared_diff = (predicted_depth - actual_depth) ** 2
    
    # Compute mean squared error
    mse = np.nanmean(squared_diff)
    
    # Return the root mean squared error
    rmse = np.sqrt(mse)
    
    return rmse

def spatial_noise(depth_map, ignore_nan=True):
    #Calculate spatial noise (standard deviation) of a depth map.
    depth_map = np.array(depth_map, dtype=np.float32)

    if ignore_nan:
        # Mask out zero values
        valid_depths = depth_map[np.isfinite(depth_map)]
    else:
        valid_depths = depth_map

    # Compute standard deviation
    spatial_noise = np.std(valid_depths)
    
    return spatial_noise

def median_lr_consistency_error(disp_left, disp_right, ignore_zeros=True):
    #Calculate the median left-right consistency error for stereo disparity maps.

    height, width = disp_left.shape
    errors = []

    for y in range(height):
        for x in range(width):
            d_left = disp_left[y, x]
            if ignore_zeros and d_left == 0:
                continue

            # Corresponding x in right image
            xr = int(round(x - d_left))
            if 0 <= xr < width:
                d_right = disp_right[y, xr]
                if ignore_zeros and d_right == 0:
                    continue
                errors.append(abs(d_left - d_right))

    if len(errors) == 0:
        return 0.0  # No valid pixels

    return float(np.median(errors))


