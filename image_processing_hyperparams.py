import cv2
import numpy as np
import glob
import matplotlib.pyplot as plt
from stereo_class import StereoSystem
from performance import depth_rmse, spatial_noise, median_lr_consistency_error
#from stereo_class import StereoSystem, CameraCalibration

stereo = StereoSystem(block_size=3, num_disp=16*15)
calibrating = False
calib_file_path = "calibration_params_60mm.npz"


calib_right_images = sorted(glob.glob("C:\\repos\\images\\received_calibration\\5cm\\left_image*.png"))
calib_left_images = sorted(glob.glob("C:\\repos\\images\\received_calibration\\5cm\\right_image*.png"))

depth_L_path = "C:\\repos\\images\\received_depth\\60mm_depth\\left_image_1051128656329600_705mm.png"
depth_R_path = "C:\\repos\\images\\received_depth\\60mm_depth\\right_image_1051128656329600_705mm.png"

depth_img_L = cv2.imread(depth_L_path)
depth_img_R = cv2.imread(depth_R_path)

with open(f"validation_results.csv", "w") as f:
    f.write("Depth_Image,Block_Size,WLS_Lambda,Depth_RMSE_mm,Spatial_Noise_mm,Median_LR_Consistency_Error_px\n")

for block_size in [3,5,7]:
    for num_disp in [16*10, 16*15, 16*20]:
        for wls_lambda in [500, 2000, 8000]:
            with open(f"validation_results.csv", "a") as f:
                f.write(f"{depth_L_path},{block_size},{wls_lambda},")
            print(f"Testing block size {block_size}, num_disp {num_disp} and wls_lambda {wls_lambda}")
            stereo = StereoSystem(block_size=block_size, num_disp=num_disp, wls_lambda=wls_lambda)
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
            stereo.visualize_depth_map(depth, title="Depth Map")
            actual_depth = 0.705  # replace with actual depth if known for testing
            #roi_depth, roi_dispL, roi_dispR = get_roi(depth, dispL, dispR)
            x = 1017
            y = 422
            width = 313
            height = 446
            roi_depth = depth[y:y+height, x:x+width]
            roi_dispL = dispL[y:y+height, x:x+width]
            roi_dispR = dispR[y:y+height, x:x+width]
            rmse = depth_rmse(roi_depth, actual_depth)
            noise = spatial_noise(roi_depth)
            lr = median_lr_consistency_error(roi_dispL, roi_dispR)
            print(f"Depth RMSE: {rmse*1000:.4f} mm, Spatial Noise: {noise*1000:.4f} mm, Median LR Consistency Error: {lr:.2f} pixels")
            
            with open(f"validation_results.csv", "a") as f:
                f.write(f"{rmse*1000:.4f},{noise*1000:.4f},{lr:.2f}\n")
