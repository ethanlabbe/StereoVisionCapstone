import cv2
import numpy as np
import glob
import matplotlib.pyplot as plt
from stereo_class_ethan import StereoSystem
from performance import depth_rmse, spatial_noise, median_lr_consistency_error, get_roi
#from stereo_class import StereoSystem, CameraCalibration

stereo = StereoSystem(block_size=5, num_disp=16*20)
calibrating = False
calib_file_path = "calib_60mm_0.5.npz"

calib_left_images = sorted(glob.glob("C:\\repos\\images\\received_calibration\\60mm\\left_image*.png"))
calib_right_images = sorted(glob.glob("C:\\repos\\images\\received_calibration\\60mm\\right_image*.png"))

depth_folder = "C:\\repos\\images\\received_depth\\60mm_depth"

if calibrating:
    # Add chessboard corners (only valid pairs)
    valid_pairs = 0
    for l_path, r_path in zip(calib_left_images, calib_right_images):
        left_img = cv2.imread(l_path)
        right_img = cv2.imread(r_path)
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
    stereo.save_calibration_parameters(calib_file_path)
    # Print baseline from Q matrix
    baseline = 1.0 / stereo.Q[3, 2]
    actual_baseline = 0.06  # replace with actual measured baseline in meters
    baseline_error = abs(baseline - actual_baseline) / actual_baseline
    
    print(f"Baseline: {baseline*100:.2f} centimeters")
    print(f"Baseline error: {baseline_error*100:.2f}%")
    # Print reprojection error
    print(f"Left reprojection error: {stereo.retL:.2f}px")
    print(f"Right reprojection error: {stereo.retR:.2f}px")
    print(f"Stereo reprojection error: {stereo.stereo_ret:.2f}px")
else:
    stereo.load_calibration_parameters(calib_file_path)

with open(f"validation_results.csv", "w") as f:
    f.write("Baseline_mm,Actual_Depth_m,Depth_RMSE_mm,Spatial_Noise_mm,Median_LR_Consistency_Error_px\n")
for depth_L_path in sorted(glob.glob(f"{depth_folder}\\left_image_*.png")):
    depth_R_path = depth_L_path.replace("left_image", "right_image")
    depth_img_L = cv2.imread(depth_L_path)
    depth_img_R = cv2.imread(depth_R_path)
    # depth_img_L, depth_img_R = stereo.preprocess_images(depth_img_L, depth_img_R)
    rectified_L, rectified_R = stereo.rectify_pair(depth_img_L, depth_img_R)
    dispL, dispL2, dispR = stereo.compute_disparity(rectified_L, rectified_R)
    # Pass dispL directly - disparity_to_depth handles masking internally
    #dispL_filtered = stereo.postprocess_disparity(dispL)
    depth = stereo.disparity_to_depth(dispL)
    image_title = depth_L_path.split("\\")[-1].replace(".png", "")
    stereo.visualize_depth_map(depth, original_image=depth_img_L,title=f"Depth Image {image_title}", vmin = 0.3,vmax= 1.5)
    actual_depth = input("Enter actual depth for performance metrics (or press Enter to skip): ")
    if actual_depth:
        roi_depth, roi_dispL, roi_dispR = get_roi(depth, dispL, dispR)
        rmse = depth_rmse(roi_depth, actual_depth)
        noise = spatial_noise(roi_depth)
        lr = median_lr_consistency_error(roi_dispL, roi_dispR)
        print(f"Depth RMSE: {rmse*1000:.4f} mm, Spatial Noise: {noise*1000:.4f} mm, Median LR Consistency Error: {lr:.2f} pixels")
        with open(f"validation_results.csv", "a") as f:
            f.write(f"70,{rmse*1000:.4f},{noise*1000:.4f},{lr:.2f}\n")
