from image_transfer import ImageClient
from stereo_class import CameraCalibration, StereoSystem
import performance
import numpy as np
import cv2

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
                fL = open("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\LeftCBoard.png", 'rb')
                imgL = fL.read()
                fR = open("C:\\Users\\15877\\OneDrive\\Documents\\GitHub\\StereoVisionCapstone\\RightCBoard.png", 'rb')
                imgR = fR.read()
            imgL_array = np.frombuffer(imgL,np.uint8)
            imgR_array = np.frombuffer(imgR,np.uint8)

            imgL_cv, imgR_cv = self.calib.decode_img(imgL_array, imgR_array)
            im_shape = imgL_cv.shape[:2]
            #ADJUST chessboard_size per calibration image in stereo_class
            self.calib.add_chessboard_corners(imgL_cv, imgR_cv)
            rmseL, rmseR, _, _, _, _ = self.calib.calibrate_cameras(im_shape)
            print(f"{rmseL},{rmseR}")
            stereorms, _ = self.calib.stereo_calibrate_and_rectify(im_shape)
            print(f"STEREO = {stereorms}")


            #TODO process received images
        else:
            print("Client not connected to server, loading local images...")
            self.load_local_images()
            #process received images for depth mapping

if __name__ == "__main__":
    device = StereoClientDevice(testing_flag=True)
    device.run()