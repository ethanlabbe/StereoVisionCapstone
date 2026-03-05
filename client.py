from image_transfer import ImageClient
from stereo_class_ethan import StereoSystem
from performance import depth_rmse, spatial_noise, median_lr_consistency_error
import numpy as np
import cv2
import glob 
import matplotlib.pyplot as plt


class StereoClientDevice:
    def __init__(self, server_host='localhost', server_port=8080, calibraton_params_file="calibration_params.npz"):
        self.client = ImageClient(server_host, server_port)
        self.stereo = StereoSystem()
        self.stereo.load_calibration_parameters(calibraton_params_file)

    
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
        
    def run(self):
        self.client.connect()

        while self.client.connected:
            imgL_bytes, imgR_bytes = self.client.receive_images()

            try:
                imgL = self.reconstruct(imgL_bytes)
                imgR = self.reconstruct(imgR_bytes)
            except ValueError as e:
                print("Error: Failed to decode or reshape images.", e)
                continue
            
            # Process images (rectification, disparity, depth)
            print("Rectifiying Images")
            rectified_L, rectified_R = self.stereo.rectify_pair(imgL, imgR)
            print("Computing Disparity")
            dispL, dispL2, dispR = self.stereo.compute_disparity(rectified_L, rectified_R)
            # Pass dispL directly - disparity_to_depth handles masking internally
            #dispL_filtered = self.stereo.postprocess_disparity(dispL)
            print("Calculating Depth")
            depth = self.stereo.disparity_to_depth(dispL)
            print("Visualizing Depth Map")
            self.stereo.visualize_depth_map(depth, original_image=imgL, title="Depth Map", vmax=4, file_path="C:\\repos\\images\\depth_map")
            self.stereo.save_images(imgL, imgR, folder="C:\\repos\\images\\received\\")
            actual_depth = 1  # replace with actual depth if known for testing
            print("Calculating Performance Metrics")
            rmse = depth_rmse(depth, actual_depth)
            noise = spatial_noise(depth)
            lr = median_lr_consistency_error(dispL, dispR)
            print(f"Depth RMSE: {rmse:.4f} m, Spatial Noise: {noise:.4f} m, Median LR Consistency Error: {lr:.2f} pixels")
            

if __name__ == "__main__":
    device = StereoClientDevice(server_host='10.42.0.1', calibraton_params_file="calibration_params_700mm.npz")
    device.run()