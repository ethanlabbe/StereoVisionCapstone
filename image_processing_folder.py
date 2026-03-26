import cv2
import numpy as np
import glob
import matplotlib.pyplot as plt
from stereo_class_ethan import StereoSystem
from performance import depth_rmse, spatial_noise, median_lr_consistency_error
#from stereo_class import StereoSystem, CameraCalibration

stereo = StereoSystem()
calibrating = True
images_folder = "C:\\repos\\images\\testing"
depth_folder = "depth"

scales = [0.5]



for scale in scales:
    print(f"Processing images at scale: {scale}")
    with open(f"calibration_results_{scale}.csv", "w") as f:
        f.write("Folder,Pairs_Found,Baseline_cm,Baseline_Error_Percent,Left_Reprojection_Error_px,Right_Reprojection_Error_px,Stereo_Reprojection_Error_px,Depth_RMSE_m,Spatial_Noise_m,Median_LR_Consistency_Error_px\n")

    for folder in glob.glob(images_folder + "/*/"):
        stereo = StereoSystem(num_disp=80, block_size=9, wls_lambda=4000)
        folder_name = folder.split("\\")[-2]
        folder_depth = folder + depth_folder + "\\"
        
        if folder_name in  ["700mm", "450mm"]:
            calib_left_images = sorted(glob.glob(folder + "left_image*.png"))
            calib_right_images = sorted(glob.glob(folder + "right_image*.png"))
            depth_img_R = cv2.imread(glob.glob(folder_depth + "left_image*.png")[0])
            depth_img_L = cv2.imread(glob.glob(folder_depth + "right_image*.png")[0])
            
        else:
            calib_right_images = sorted(glob.glob(folder + "left_image*.png"))
            calib_left_images = sorted(glob.glob(folder + "right_image*.png"))
            depth_img_R = cv2.imread(glob.glob(folder_depth + "left_image*.png")[0])
            depth_img_L = cv2.imread(glob.glob(folder_depth + "right_image*.png")[0])
        print(f"Processing folder: {folder_name}")

        depth_img_L = cv2.resize(depth_img_L, (0, 0), fx=scale, fy=scale)
        depth_img_R = cv2.resize(depth_img_R, (0, 0), fx=scale, fy=scale)

        if calibrating:
            # Add chessboard corners (only valid pairs)
            valid_pairs = 0
            for l_path, r_path in zip(calib_left_images, calib_right_images):
                left_img = cv2.resize(cv2.imread(l_path), (0, 0), fx=scale, fy=scale)
                right_img = cv2.resize(cv2.imread(r_path), (0, 0), fx=scale, fy=scale)
                retl, cornersL, retR, cornersR = stereo.find_calibration_corners(left_img, right_img, display=False)
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
            stereo.save_calibration_parameters(f"test_calib_{folder_name}_{scale}.npz")
            # Print baseline from Q matrix
            baseline = 1.0 / stereo.Q[3, 2]
            actual_baseline = folder_name.split("mm")[0]
            actual_baseline = float(actual_baseline) / 10000.0  # convert to meters
            baseline_error = abs(baseline - actual_baseline) / actual_baseline
            
            print(f"Baseline: {baseline*100:.2f} centimeters")
            print(f"Actual Baseline: {actual_baseline*100:.2f} centimeters")
            print(f"Baseline error: {baseline_error*100:.2f}%")
            # Print reprojection error
            print(f"Left reprojection error: {stereo.retL:.2f}px")
            print(f"Right reprojection error: {stereo.retR:.2f}px")
            print(f"Stereo reprojection error: {stereo.stereo_ret:.2f}px")
        else:
            stereo.load_calibration_parameters(f"test_calib_{folder_name}_{scale}.npz")

        # depth_img_L, depth_img_R = stereo.preprocess_images(depth_img_L, depth_img_R)
        rectified_L, rectified_R = stereo.rectify_pair(depth_img_L, depth_img_R)
        dispL, dispL2, dispR = stereo.compute_disparity(rectified_L, rectified_R)
        # Pass dispL directly - disparity_to_depth handles masking internally
        #dispL_filtered = stereo.postprocess_disparity(dispL)
        depth = stereo.disparity_to_depth(dispL)
        stereo.visualize_depth_map(depth, title=f"Depth Map with scale {scale}",original_image=depth_img_L, vmax=1.5,save_folder=f"C:\\repos\\images\\testing\\{folder_name}\\depth_maps\\")
        actual_depth = 0.6  # replace with actual depth if known for testing
        rmse = depth_rmse(depth, actual_depth)
        noise = spatial_noise(depth)
        lr = median_lr_consistency_error(dispL, dispR)
        print(f"Depth RMSE: {rmse:.4f} m, Spatial Noise: {noise:.4f} m, Median LR Consistency Error: {lr:.2f} pixels")
        
        with open(f"calibration_results_{scale}.csv", "a") as f:
            f.write(f"{folder_name},{valid_pairs},{baseline*100:.2f},{baseline_error*100:.2f},{stereo.retL:.2f},{stereo.retR:.2f},{stereo.stereo_ret:.2f},{rmse:.4f},{noise:.4f},{lr:.2f}\n")
