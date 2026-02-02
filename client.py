from image_transfer import ImageClient
from stereo_class import CameraCalibration, StereoSystem
import performance
import numpy as np
import cv2
import glob 
import matplotlib.pyplot as plt


class StereoClientDevice:
    def __init__(self, server_host='localhost', server_port=8080, testing_flag=False):
        self.client = ImageClient(server_host, server_port)
        self.calib = CameraCalibration()
        self.stereo = StereoSystem()
        self.testing = testing_flag

    
    def load_local_images(self, left_filename="left_image.jpg", right_filename="right_image.jpg"):
        #load images from local storage
        pass    
        
    def run(self):
        if not self.testing:
            self.client.connect()
        else:
            self.client.connected = True

        while self.client.connected:
            if not self.testing:
                imgL, imgR = self.client.receive_images()
            else:
                """fL = open("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\Im_L_1.png", 'rb')
                imgL = fL.read()
                fR = open("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\Im_R_1.png", 'rb')
                imgR = fR.read()"""

            """imgL_array = np.frombuffer(imgL,np.uint8)
            imgR_array = np.frombuffer(imgR,np.uint8)

            imgL_cv, imgR_cv = self.calib.decode_img(imgL_array, imgR_array)"""


            right_images  = sorted(glob.glob("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\data\\imgs\\288cm_new_actual\\left_image*.png"))
            left_images = sorted(glob.glob("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\data\\imgs\\288cm_new_actual\\right_image*.png"))

            #Add chessboard corners
            valid_pairs = 0
            scale = 4.75
            for l_path, r_path in zip(left_images, right_images):
                imgL = cv2.imread(l_path)
                imgR = cv2.imread(r_path)

                h, w = imgL.shape[:2]

                resized_imgL = cv2.resize(imgL, (int(w / scale), int(h / scale)))
                resized_imgR = cv2.resize(imgR, (int(w / scale), int(h / scale)))

                if imgL is None or imgR is None:
                    continue

                # Only adds if corners are found
                self.calib.add_chessboard_corners(resized_imgL, resized_imgR, 1)
                valid_pairs += 1

            if valid_pairs == 0:
                raise RuntimeError("No valid chessboard pairs found!")

            print(f"Found {valid_pairs} valid stereo pairs.")

            #Use the first image to get image shape
            sample_imgR = cv2.imread("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\data\\depth_img\\288cm_new_actual\\left_image_20260202_205211.png")
            sample_imgL = cv2.imread("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\data\\depth_img\\288cm_new_actual\\right_image_20260202_205211.png")


            image_shape = (w, h)  #Switch since OpenCV uses width then height
            resized_sample_imgL = cv2.resize(sample_imgL, (int(w / scale), int(h / scale)))
            resized_sample_imgR = cv2.resize(sample_imgR, (int(w / scale), int(h / scale)))

            h, w = resized_sample_imgL.shape[:2]
            image_shape = (w, h)

            #Calibrate individual cameras
            rmsL, rmsR, _, _, _, _ = self.calib.calibrate_cameras(image_shape)
            print(f"Left Camera RMSE:  {rmsL:.4f} px")
            print(f"Right Camera RMSE: {rmsR:.4f} px")

            #Stereo calibration and rectification
            stereo_rms, Q_matrix = self.calib.stereo_calibrate_and_rectify(image_shape)
            print(f"Stereo Calibration RMSE: {stereo_rms:.4f} px")

            print(f"{Q_matrix}")
            #Get rectification maps
            rect_mapL1, rect_mapL2, rect_mapR1, rect_mapR2 = self.calib.get_rectification_maps()
            
            #Now using stereo class
            #ADJUST chessboard_size per calibration image in stereo_class
            self.stereo.set_rectification(rect_mapL1, rect_mapL2, rect_mapR1, rect_mapR2, Q_matrix)

            #Rectify first pair
            imgL_rect, imgR_rect = self.stereo.rectify_pair(resized_sample_imgL, resized_sample_imgR)

            imgL_gray = cv2.cvtColor(imgL_rect, cv2.COLOR_BGR2GRAY) 
            imgR_gray = cv2.cvtColor(imgR_rect, cv2.COLOR_BGR2GRAY)

            """cv2.imshow("Left Rectified", imgL_rect)
            cv2.imshow("Right Rectified", imgR_rect)
            cv2.waitKey(1000)
            cv2.destroyAllWindows()"""

            dispL_filtered, dispL, dispR = self.stereo.compute_disparity(imgL_gray, imgR_gray)
            print("Disparity range:", np.nanmin(dispL_filtered), np.nanmax(dispL_filtered))
            print("raw dispL min/max:", np.min(dispL_filtered), np.max(dispL_filtered))
            visR = (dispR - np.min(dispR)) / (np.max(dispR) - np.min(dispR) + 1e-6)
            #cv2.imshow("dispR", visR)
            cv2.imshow("dispL filtered", (dispL_filtered - self.stereo.min_disp) / self.stereo.num_disp)  # quick normalization            cv2.waitKey(0)
            #cv2.destroyAllWindows

            disp = dispL_filtered.copy()
            disp[disp <= 0.000000001] = np.nan

            depth = self.stereo.disparity_to_depth(disp)
            #depth = -depth

            depth[~np.isfinite(depth)] = np.nan

            print(f"{dispL_filtered}")
            print(f"{depth}")
            plt.figure(figsize=(10, 6))
            im = plt.imshow(depth, cmap='YlOrRd', vmin=0.01, vmax=1.2)
            plt.colorbar(im, label='Depth (meters)')
            plt.title('Depth Map from Disparity')
            plt.axis('off')
            plt.show()

            #TODO process received images
        else:
            print("Client not connected to server, loading local images...")
            self.load_local_images()
            #process received images for depth mapping

if __name__ == "__main__":
    device = StereoClientDevice(testing_flag=True)
    device.run()