import numpy as np
import cv2

def get_roi(predicted_depth, dispL=None, dispR=None):
    
    valid_mask = np.isfinite(predicted_depth) & (predicted_depth > 0)
    if np.any(valid_mask):
        # 2. Calculate the 5th and 95th percentiles of VALID depths
        vmin = np.percentile(predicted_depth[valid_mask], 5)
        vmax = np.percentile(predicted_depth[valid_mask], 85)
        print(f"Valid depth range for ROI selection: {vmin:.2f} m to {vmax:.2f} m")
    else:
        vmin, vmax = 0, 255

    #Clip the depth map to ignore the extreme edge outliers for visualization
    clipped_depth = np.clip(predicted_depth, vmin, vmax)
    visual_image = cv2.normalize(clipped_depth, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    color_map_image = cv2.applyColorMap(visual_image, cv2.COLORMAP_JET)
    color_map_image[~valid_mask] = [0, 0, 0]
    
    # Let the user select an ROI to evaluate depth metrics on
    window_title = "Select ROI"
    cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    roi = cv2.selectROI(window_title, color_map_image, showCrosshair=False)
    cv2.destroyAllWindows()
    
    x, y, w, h = roi

    if w > 0 and h > 0:
        # Slice the raw depth map and disparities using the visual coordinates
        roi_depth = predicted_depth[y:y+h, x:x+w]
        if dispL is not None:
            roi_dispL = dispL[y:y+h, x:x+w]
            roi_dispR = dispR[y:y+h, x:x+w]
            return roi_depth, roi_dispL, roi_dispR
    return roi_depth

def depth_rmse(roi_depth, ground_truth_depth_value):
    #Compute RMSE for a depth map against a flat wall of known distance

    predicted_depth = np.array(roi_depth, dtype=np.float32)
    actual_depth = np.full_like(predicted_depth, fill_value = ground_truth_depth_value)

    # Compute the squared differences
    squared_diff = (predicted_depth - actual_depth) ** 2
    
    # Compute mean squared error
    mse = np.nanmean(squared_diff)
    
    # Return the root mean squared error
    rmse = np.sqrt(mse)
    
    return rmse

def spatial_noise(roi_depth, ignore_nan=True):
    #Calculate spatial noise (standard deviation) of a depth map.
    depth_map = np.array(roi_depth, dtype=np.float32)

    if ignore_nan:
        # Mask out zero values
        valid_depths = depth_map[np.isfinite(depth_map)]
    else:
        valid_depths = depth_map

    # Compute standard deviation
    spatial_noise = np.std(valid_depths)
    
    return spatial_noise

def median_lr_consistency_error(dispL, dispR):
    # Ensure inputs are 32-bit floats
    dispL = np.array(dispL, dtype=np.float32)
    dispR = np.array(dispR, dtype=np.float32)
    
    # Define valid masks (assuming valid disparity is positive for Left)
    valid_mask_L = dispL > 0
    
    dispR_pos = -dispR
    valid_mask_R = dispR_pos > 0 
    
    h, w = dispL.shape
    shifted_dispR = np.zeros_like(dispL)
    x_indices = np.arange(w)
    
    for y in range(h):
        # Extract the valid pixels for this row in the right map
        row_mask_R = valid_mask_R[y, :]
        valid_disp = dispR_pos[y, row_mask_R]
        valid_x = x_indices[row_mask_R]
        
        if len(valid_disp) == 0:
            continue
            
        # Shift the right pixels into the left camera's coordinate space
        shifted_x = np.round(valid_x + valid_disp).astype(int)
        
        # Filter out pixels that shift outside the image bounds
        bounds_mask = (shifted_x >= 0) & (shifted_x < w)
        
        valid_x_bounded = valid_x[bounds_mask]
        shifted_x_bounded = shifted_x[bounds_mask]
        valid_disp_bounded = valid_disp[bounds_mask]
        
        # Assign shifted values
        shifted_dispR[y, shifted_x_bounded] = valid_disp_bounded

    # Compare where BOTH the left map and our shifted right map have valid data
    valid_comparison_mask = valid_mask_L & (shifted_dispR > 0)
    
    if not np.any(valid_comparison_mask):
        return np.nan
        
    error_map = np.abs(dispL[valid_comparison_mask] - shifted_dispR[valid_comparison_mask])
    
    return float(np.median(error_map))

