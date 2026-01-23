import os
from image_transfer import ImageServerHost
from acquisition import StereoCameraAcquisition
import cv2
import datetime

#ui imports
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt
 

class RaspberryPiStereoSystem:
    def __init__(self):
        self.running = False

        # bind to a local IP address reachable on your network
        self.server = ImageServerHost(host='192.168.1.100', port=8080)
        self.stereo_system = StereoCameraAcquisition()

    def save_images_locally(self, left_image, right_image, left_filename="left_image.jpg", right_filename="right_image.jpg", folder="rpi/desktop/images"):
        time_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(folder + "/" + left_filename + "_" + time_stamp, cv2.cvtColor(left_image, cv2.COLOR_RGB2BGR))
        cv2.imwrite(folder + "/" + right_filename + "_" + time_stamp, cv2.cvtColor(right_image, cv2.COLOR_RGB2BGR))
        print(f"Images saved locally: {left_filename}, {right_filename}")


    def run(self):
        self.running = True
        self.stereo_system.initialize_cameras()
        
        # start server in background (non-blocking)
        if input("Start server? (y/n): ") == 'y':
            self.server.start_server()
        else:
            folder_path = "rpi/desktop/images/" + input('Enter folder path to save images rpi/desktop/images/[input here]:')
            if not os.path.exists(folder_path):
                try:
                    os.makedirs(folder_path)
                except Exception as e:
                    print("Failed to create folder:", e)
                    folder_path = "rpi/desktop/images/"

        self.stereo_system.display_preview()

        while self.running:
            # interface with UI to take images when button pressed
            if input("Press Enter to capture images or 'exit' to quit: ") != 'exit': #replace with actual UI event
                imgL, imgR = self.stereo_system.capture_stereo_image()

                if self.server.connected:
                    try:
                        print("Sending images to client...")
                        self.server.send_images(imgL, imgR)
                    except Exception as e:
                        print("Failed to send images:", e)
                        self.save_images_locally(imgL, imgR, folder=folder_path)
                else:
                    self.save_images_locally(imgL, imgR, folder=folder_path)
            else:
                self.running = False
                self.stereo_system.stop()
                self.server.stop_server()


if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()