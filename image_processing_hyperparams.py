import cv2
import numpy as np
import glob
import matplotlib.pyplot as plt
from stereo_class_ethan import StereoSystem
from performance import depth_rmse, spatial_noise, median_lr_consistency_error, get_roi
#from stereo_class import StereoSystem, CameraCalibration

stereo = StereoSystem(block_size=3, num_disp=16*15)
calibrating = False
calib_file_path = "test_calib_60mm_0.5.npz"
scale_factor = 0.5


calib_right_images = sorted(glob.glob("C:\\repos\\images\\received_calibration\\5cm\\left_image*.png"))
calib_left_images = sorted(glob.glob("C:\\repos\\images\\received_calibration\\5cm\\right_image*.png"))

depth_L_path = "C:\\repos\\images\\testing\\60mm\\left_image_445935019585000.png"
depth_R_path = "C:\\repos\\images\\testing\\60mm\\right_image_445935019585000.png"

depth_img_L = cv2.imread(depth_L_path)
depth_img_R = cv2.imread(depth_R_path)

depth_img_L = cv2.resize(depth_img_L, (0, 0), fx=scale_factor, fy=scale_factor)
depth_img_R = cv2.resize(depth_img_R, (0, 0), fx=scale_factor, fy=scale_factor)

for block_size in [3, 5, 7]:
    for wls_lambda in [0, 500, 800]:
        with open(f"validation_results.csv", "a") as f:
            f.write(f"{depth_L_path},{block_size},{wls_lambda},")
        print(f"Testing block size {block_size} and wls_lambda {wls_lambda}")
        stereo = StereoSystem(block_size=block_size, num_disp=16*15, wls_lambda=wls_lambda)
        if calibrating:
            # Add chessboard corners (only valid pairs)
            valid_pairs = 0
            for l_path, r_path in zip(calib_left_images, calib_right_images):
                left_img = cv2.imread(l_path)
                right_img = cv2.imread(r_path)
                retl, cornersL, retR, cornersR = stereo.find_calibration_corners(left_img, right_img, display=True)
                if not (retl and retR):
                    print(f"Failed to find corners in pair {l_path} and {r_path}")
                else:
                    valid_pairs += 1
                    print(f"Found corners in pair {l_path} and {r_path}")
            if valid_pairs < 5:
                print(f"Warning: Only {valid_pairs} valid pairs found. Calibration may be poor.")
            # Use more robust calibration flags
            stereo.calibrate_stereo_system()
            stereo.generate_rectification_maps()
            stereo.save_calibration_parameters(calib_file_path)
            # Print baseline from Q matrix
            baseline = 1.0 / stereo.Q[3, 2]
            actual_baseline = 0.07  # replace with actual measured baseline in meters
            baseline_error = abs(baseline - actual_baseline) / actual_baseline
            
            print(f"Baseline: {baseline*100:.2f} centimeters")
            print(f"Baseline error: {baseline_error*100:.2f}%")
            # Print reprojection error
            print(f"Left reprojection error: {stereo.retL:.2f}px")
            print(f"Right reprojection error: {stereo.retR:.2f}px")
            print(f"Stereo reprojection error: {stereo.stereo_ret:.2f}px")
        else:
            stereo.load_calibration_parameters(calib_file_path)

        # depth_img_L, depth_img_R = stereo.preprocess_images(depth_img_L, depth_img_R)
        rectified_L, rectified_R = stereo.rectify_pair(depth_img_L, depth_img_R)
        dispL, dispL2, dispR = stereo.compute_disparity(rectified_L, rectified_R)
        if calibrating:
            # Add chessboard corners (only valid pairs)
            valid_pairs = 0
            for l_path, r_path in zip(calib_left_images, calib_right_images):
                left_img = cv2.imread(l_path)
                right_img = cv2.imread(r_path)
                retl, cornersL, retR, cornersR = stereo.find_calibration_corners(left_img, right_img, display=True)
                if not (retl and retR):
                    print(f"Failed to find corners in pair {l_path} and {r_path}")
                else:
                    valid_pairs += 1
                    print(f"Found corners in pair {l_path} and {r_path}")
            if valid_pairs < 5:
                print(f"Warning: Only {valid_pairs} valid pairs found. Calibration may be poor.")
            # Use more robust calibration flags
            stereo.calibrate_stereo_system()
            stereo.generate_rectification_maps()
            stereo.save_calibration_parameters(calib_file_path)
            # Print baseline from Q matrix
            baseline = 1.0 / stereo.Q[3, 2]
            actual_baseline = 0.07  # replace with actual measured baseline in meters
            baseline_error = abs(baseline - actual_baseline) / actual_baseline
            
            print(f"Baseline: {baseline*100:.2f} centimeters")
            print(f"Baseline error: {baseline_error*100:.2f}%")
            # Print reprojection error
            print(f"Left reprojection error: {stereo.retL:.2f}px")
            print(f"Right reprojection error: {stereo.retR:.2f}px")
            print(f"Stereo reprojection error: {stereo.stereo_ret:.2f}px")
        else:
            stereo.load_calibration_parameters(calib_file_path)

        # depth_img_L, depth_img_R = stereo.preprocess_images(depth_img_L, depth_img_R)
        rectified_L, rectified_R = stereo.rectify_pair(depth_img_L, depth_img_R)
        dispL, dispL2, dispR = stereo.compute_disparity(rectified_L, rectified_R)
        # Pass dispL directly - disparity_to_depth handles masking internally
        #dispL_filtered = stereo.postprocess_disparity(dispL)
        depth = stereo.disparity_to_depth(dispL)
        stereo.visualize_depth_map(depth, title="Depth Map", vmin = 0.2,vmax= 1)
        actual_depth = 0.6  # replace with actual depth if known for testing
        # roi_depth, roi_dispL, roi_dispR = get_roi(depth, dispL, dispR)
        x = 752
        y = 403
        width = 501
        height = 610
        roi_depth = depth[y:y+height, x:x+width]
        roi_dispL = dispL[y:y+height, x:x+width]
        roi_dispR = dispR[y:y+height, x:x+width]
        rmse = depth_rmse(roi_depth, actual_depth)
        noise = spatial_noise(roi_depth)
        lr = median_lr_consistency_error(roi_dispL, roi_dispR)
        print(f"Depth RMSE: {rmse:.4f} m, Spatial Noise: {noise:.4f} m, Median LR Consistency Error: {lr:.2f} pixels")
        
        with open(f"validation_results.csv", "a") as f:
            f.write(f"{rmse:.4f},{noise:.4f},{lr:.2f}\n")
