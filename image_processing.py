import cv2
import numpy as np
import glob
import matplotlib.pyplot as plt
from stereo_class import CameraCalibration, StereoSystem

calib = CameraCalibration()
stereo = StereoSystem()

left_images = sorted(glob.glob("C:\\Users\\Ethan\\OneDrive\\Desktop\\Labs\\5th year\\Capstone\\288cm_new_actual\\left_image*.png"))
right_images = sorted(glob.glob("C:\\Users\\Ethan\\OneDrive\\Desktop\\Labs\\5th year\\Capstone\\288cm_new_actual\\right_image*.png"))

# Add chessboard corners
valid_pairs = 0
for l_path, r_path in zip(left_images, right_images):

    imgL = cv2.imread(l_path)
    imgR = cv2.imread(r_path)
    
    

    # h, w = imgL.shape[:2]

    # resized_imgL = cv2.resize(imgL, (int(w*0.25), int(h / 0.25)))
    # resized_imgR = cv2.resize(imgR, (int(w / 0.25), int(h / 0.25)))

    if imgL is None or imgR is None:
        continue

    # Only adds if corners are found
    calib.add_chessboard_corners(imgL, imgR, display=True)
    valid_pairs += 1

if valid_pairs == 0:
    raise RuntimeError("No valid chessboard pairs found!")

print(f"Found {valid_pairs} valid stereo pairs.")

l_path = "C:\\Users\\Ethan\\OneDrive\\Desktop\\Labs\\5th year\\Capstone\\288cm_new_actual\\depth_image\\left_image_20260202_205211.png"
r_path = "C:\\Users\\Ethan\\OneDrive\\Desktop\\Labs\\5th year\\Capstone\\288cm_new_actual\\depth_image\\right_image_20260202_205211.png"

# Use the first image to get image shape
sample_imgL = cv2.imread(l_path)
sample_imgR = cv2.imread(r_path)

# image_shape = (w, h)  #Switch since OpenCV uses width then height
# resized_sample_imgL = cv2.resize(sample_imgL, (int(w / scale), int(h / scale)))
# resized_sample_imgR = cv2.resize(sample_imgR, (int(w / scale), int(h / scale)))

# h, w = resized_sample_imgL.shape[:2]
# image_shape = (w, h)
h, w = sample_imgL.shape[:2]
image_shape = (w, h)

# Calibrate individual cameras
rmsL, rmsR, _, _, _, _ = calib.calibrate_cameras(image_shape)
print(f"Left Camera RMSE:  {rmsL:.4f} px")
print(f"Right Camera RMSE: {rmsR:.4f} px")

# Stereo calibration and rectification
stereo_rms, Q_matrix = calib.stereo_calibrate_and_rectify(
    image_shape)
print(f"Stereo Calibration RMSE: {stereo_rms:.4f} px")

print(f"{Q_matrix}")
# Get rectification maps
rect_mapL1, rect_mapL2, rect_mapR1, rect_mapR2 = calib.get_rectification_maps()

# Now using stereo class
# ADJUST chessboard_size per calibration image in stereo_class
stereo.set_rectification(
    rect_mapL1, rect_mapL2, rect_mapR1, rect_mapR2, Q_matrix)



# Rectify first pair
imgL_rect, imgR_rect = stereo.rectify_pair(
    sample_imgL, sample_imgR)

imgL_gray = cv2.cvtColor(imgL_rect, cv2.COLOR_BGR2GRAY)
imgR_gray = cv2.cvtColor(imgR_rect, cv2.COLOR_BGR2GRAY)

cv2.imshow("Left Rectified", imgL_rect)
cv2.imshow("Right Rectified", imgR_rect)
cv2.waitKey(1000)
cv2.destroyAllWindows()

dispL_filtered, dispL, dispR = stereo.compute_disparity(
    imgL_gray, imgR_gray)
print("Disparity range:", np.nanmin(
    dispL_filtered), np.nanmax(dispL_filtered))
print("raw dispL min/max:", np.min(dispL_filtered),
        np.max(dispL_filtered))
# visR = (dispR - np.min(dispR)) / (np.max(dispR) - np.min(dispR) + 1e-6)
# cv2.imshow("dispR", visR)
# cv2.imshow("dispL filtered", (dispL_filtered - stereo.min_disp) / stereo.num_disp)  # quick normalization
# cv2.waitKey(0)
# cv2.destroyAllWindows

disp = dispL_filtered.copy()
disp[disp <= 1.0] = np.nan

depth = stereo.disparity_to_depth(disp)
depth = -depth

depth[~np.isfinite(depth)] = np.nan

print(f"{dispL_filtered}")
print(f"{depth}")
plt.figure(figsize=(10, 6))
im = plt.imshow(depth, cmap='plasma', vmin=0.01, vmax=10)
plt.colorbar(im, label='Depth (meters)')
plt.title('Depth Map from Disparity')
plt.axis('off')
plt.show()
