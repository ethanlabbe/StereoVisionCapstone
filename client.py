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


            left_images  = sorted(glob.glob("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\data\\imgs\\leftcamera\\*.png"))
            right_images = sorted(glob.glob("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\data\\imgs\\rightcamera\\*.png"))

            if len(left_images) == 0 or len(right_images) == 0:
                raise RuntimeError("No images found in calibration folders")

            #Add chessboard corners
            valid_pairs = 0
            for l_path, r_path in zip(left_images, right_images):
                imgL = cv2.imread(l_path)
                imgR = cv2.imread(r_path)

                if imgL is None or imgR is None:
                    continue

                # Only adds if corners are found
                self.calib.add_chessboard_corners(imgL, imgR)
                valid_pairs += 1

            if valid_pairs == 0:
                raise RuntimeError("No valid chessboard pairs found!")

            #print(f"Found {valid_pairs} valid stereo pairs.")

            #Use the first image to get image shape
            sample_img = cv2.imread(left_images[0])
            h, w = sample_img.shape[:2]
            image_shape = (w, h)  #Switch since OpenCV uses width then height

            #Calibrate individual cameras
            rmsL, rmsR, _, _, _, _ = self.calib.calibrate_cameras(image_shape)
            #print(f"Left Camera RMSE:  {rmsL:.4f} px")
            #print(f"Right Camera RMSE: {rmsR:.4f} px")

            #Stereo calibration and rectification
            stereo_rms, Q_matrix = self.calib.stereo_calibrate_and_rectify(image_shape)
            #print(f"Stereo Calibration RMSE: {stereo_rms:.4f} px")

            #Get rectification maps
            rect_mapL1, rect_mapL2, rect_mapR1, rect_mapR2 = self.calib.get_rectification_maps()
            
            #Now using stereo class
            #ADJUST chessboard_size per calibration image in stereo_class
            self.stereo.set_rectification(rect_mapL1, rect_mapL2, rect_mapR1, rect_mapR2, Q_matrix)

            #Rectify first pair
            imgL_rect, imgR_rect = self.stereo.rectify_pair(sample_img, cv2.imread(right_images[0]))

            """cv2.imshow("Left Rectified", imgL_rect)
            cv2.imshow("Right Rectified", imgR_rect)
            cv2.waitKey(0)
            cv2.destroyAllWindows()"""

            dispL_filtered, dispL, dispR = self.stereo.compute_disparity(imgL_rect, imgR_rect)
            print("Disparity range:", np.nanmin(dispL_filtered), np.nanmax(dispL_filtered))
            dispL_filtered[dispL_filtered < 0] = 0
            depth = self.stereo.disparity_to_depth(dispL_filtered)
            depth[depth < 0] = np.nan
            print(f"{dispL_filtered}")
            print(f"{depth}")
            plt.figure(figsize=(10, 6))
            im = plt.imshow(depth, cmap='plasma')
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