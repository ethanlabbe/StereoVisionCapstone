import cv2
import numpy as np
import glob
import matplotlib.pyplot as plt
from stereo_class_ethan import StereoSystem

stereo = StereoSystem()

calibrating = True
calib_right_images = sorted(glob.glob("C:\\repos\\images\\b700cm_d805\\left_image*.png"))
calib_left_images = sorted(glob.glob("C:\\repos\\images\\b700cm_d805\\right_image*.png"))

depth_img_R = cv2.imread(
    "C:\\repos\\images\\b700cm_d805\\depth_images\\left_image_20260204_231629.png")
depth_img_L = cv2.imread(
    "C:\\repos\\images\\b700cm_d805\\depth_images\\right_image_20260204_231629.png")

if calibrating:
    # Add chessboard corners
    valid_pairs = 0
    for l_path, r_path in zip(calib_left_images, calib_right_images):
        # Load images
        left_img = cv2.imread(l_path)
        right_img = cv2.imread(r_path)

        # Find chessboard corners
        retl, _, retR, _ = stereo.find_calibration_corners(left_img, right_img)
        if not (retl and retR):
            print(f"Failed to find corners in pair {l_path} and {r_path}")
        else:
            valid_pairs += 1
            print(f"Found corners in pair {l_path} and {r_path}")
    stereo.calibrate_stereo_system()
    stereo.generate_rectification_maps()
    stereo.save_calibration_parameters("calibration_params.npz")
    # print baseline from Q matrix
    baseline = -1.0 / stereo.Q[3, 2]
    print(f"Baseline: {baseline*100} centimeters")
else:
    stereo.load_calibration_parameters("calibration_params.npz")  
    
rectified_L, rectified_R = stereo.rectify_pair(depth_img_L, depth_img_R)
dispL, dispL2, dispR = stereo.compute_disparity(rectified_L, rectified_R)
# Pass dispL directly - disparity_to_depth handles masking internally
depth = stereo.disparity_to_depth(dispL)
stereo.visualize_depth_map(depth, title="Depth Map")
