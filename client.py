from image_transfer import ImageClient
from stereo_class_ethan import StereoSystem
from performance import depth_rmse, spatial_noise, median_lr_consistency_error
import numpy as np
import cv2
import glob 
import matplotlib.pyplot as plt


class StereoClientDevice:
    def __init__(self, server_host='localhost', server_port=8080, calibrating = False, calibraton_params_file="calibration_params.npz"):
        self.client = ImageClient(server_host, server_port)
        self.stereo = StereoSystem()
        if not calibrating:
            self.stereo.load_calibration_parameters(calibraton_params_file)
        self.calibration_path = calibraton_params_file
        self.calibrating = calibrating

    
    def load_local_images(self, left_filename="left_image.jpg", right_filename="right_image.jpg"):
        #load images from local storage
        pass    
    
    def reconstruct(self, bytes, image_height=3040, image_width=4056, channels=4):
        # always 4-channel RGBA
        expected = image_height * image_width * channels
        if len(bytes) != expected:
            raise ValueError(f"Expected {expected} bytes, got {len(bytes)}")
        arr = np.frombuffer(bytes, dtype=np.uint8)
        arr = arr.reshape((image_height, image_width, channels))
        # drop alpha and convert RGB->BGR
        rgb = arr[:, :, :3]
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    
    def run_calibration_pipeline(self, imgL, imgR):
        if len(self.stereo.corners_L) < 40:
            retl, cornersL, retR, cornersR = self.stereo.find_calibration_corners(imgL, imgR, display=False)
            if not (retl and retR):
                print(f"Failed to find corners in pair")
            else:
                print(f"Found corners in pair #{len(self.stereo.corners_L)}")
        else:
            self.stereo.calibrate_stereo_system()
            self.stereo.generate_rectification_maps()
            self.stereo.save_calibration_parameters(self.calibration_path)
            # Print baseline from Q matrix
            baseline = 1.0 / self.stereo.Q[3, 2]
            actual_baseline = 0.07  # replace with actual measured baseline in meters
            baseline_error = abs(baseline - actual_baseline) / actual_baseline
            print(f"Baseline: {baseline*100:.2f} centimeters")
            print(f"Baseline error: {baseline_error*100:.2f}%")
            # Print reprojection error
            print(f"Left reprojection error: {self.stereo.retL:.2f}px")
            print(f"Right reprojection error: {self.stereo.retR:.2f}px")
            print(f"Stereo reprojection error: {self.stereo.stereo_ret:.2f}px")
            self.run_depth_map_pipeline(imgL, imgR)

        
    
    def run_depth_map_pipeline(self, imgL, imgR):
        # Process images (rectification, disparity, depth)
        print("Rectifiying Images")
        rectified_L, rectified_R = self.stereo.rectify_pair(imgL, imgR)
        print("Computing Disparity")
        dispL, dispL2, dispR = self.stereo.compute_disparity(
            rectified_L, rectified_R)
        # Pass dispL directly - disparity_to_depth handles masking internally
        # dispL_filtered = self.stereo.postprocess_disparity(dispL)
        print("Calculating Depth")
        depth = self.stereo.disparity_to_depth(dispL)
        print("Visualizing Depth Map")
        self.stereo.visualize_depth_map(depth, original_image=imgL, title="Depth Map", vmax=1.75, save_folder="C:\\repos\\images\\depth_maps\\")
        actual_depth = 1  # replace with actual depth if known for testing
        # print("Calculating Performance Metrics")
        # rmse = depth_rmse(depth, actual_depth)
        # noise = spatial_noise(depth)
        # lr = median_lr_consistency_error(dispL, dispR)
        # print(f"Depth RMSE: {rmse:.4f} m, Spatial Noise: {noise:.4f} m, Median LR Consistency Error: {lr:.2f} pixels")

    def run(self):
        self.client.connect()

        while self.client.connected:
            imgL_bytes, imgR_bytes = self.client.receive_images()
            try:
                imgR = self.reconstruct(imgL_bytes)
                imgL = self.reconstruct(imgR_bytes)
            except ValueError as e:
                print("Error: Failed to decode or reshape images.", e)
                continue
            
            if self.calibrating:
                self.stereo.save_images(imgL, imgR, folder="C:\\repos\\images\\received_calibration\\")
                self.run_calibration_pipeline(imgL, imgR)
            else:
                self.stereo.save_images(imgL, imgR, folder="C:\\repos\\images\\received_depth\\")
                self.run_depth_map_pipeline(imgL, imgR)
            

if __name__ == "__main__":
    device = StereoClientDevice(server_host='10.42.0.1', calibrating=False, calibraton_params_file="calibration_params_5cm.npz")
    device.run()