import os
from image_transfer import ImageServerHost
from acquisitionui import StereoCameraAcquisition
import cv2
import datetime
import threading


#ui imports
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QGridLayout, QWidget, QLabel
from PyQt5.QtCore import Qt
from picamera2.previews.qt import QGlPicamera2

class RaspberryPiStereoSystem:
    def __init__(self):
        self.running = False

        # bind to a local IP address reachable on your network
        self.server = ImageServerHost(host='192.168.1.100', port=8080)
        self.stereo_system = StereoCameraAcquisition()
        self.folder_path=""

    def save_images_locally(self, left_image, right_image, left_filename="left_image.jpg", right_filename="right_image.jpg", folder="rpi/desktop/images"):
        time_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(folder + "/" + left_filename + "_" + time_stamp, cv2.cvtColor(left_image, cv2.COLOR_RGB2BGR))
        cv2.imwrite(folder + "/" + right_filename + "_" + time_stamp, cv2.cvtColor(right_image, cv2.COLOR_RGB2BGR))
        print(f"Images saved locally: {left_filename}, {right_filename}")


    def run(self):
        self.running = True
        self.stereo_system.initialize_cameras()
        
        # start server in background (non-blocking)

        self.folder_path = "rpi/desktop/images/" + 'temp'
        if not os.path.exists(self.folder_path):
            try:
                os.makedirs(self.folder_path)
            except Exception as e:
                print("Failed to create folder:", e)
                self.folder_path = "rpi/desktop/images/"

        #self.stereo_system.display_preview()

    def quitting(self):
        self.stereo_system.stop()
        self.server.stop_server()
        self.app.quit()


    def image_capture(self):
        capture_thread = threading.Thread(target=self._do_capture)
        capture_thread.start()

    def _do_capture(self):
        imgL, imgR = self.stereo_system.capture_stereo_image()

        if self.server.connected:
            try:
                print("Sending images to client...")
                self.server.send_images(imgL, imgR)
            except Exception as e:
                print("Failed to send images:", e)
                self.save_images_locally(imgL, imgR)
        else:
            self.save_images_locally(imgL, imgR)


    def UI_start(self):

            self.app = QApplication(sys.argv)
            rpiUI= QMainWindow()
            rpiUI.setWindowTitle("Stereo Vision Capstone")
            rpiUI.setGeometry(100, 100, 800, 600)

            #picamera2 implementation of preview to allow functionality with qtgui
            qpicamera2 = QGlPicamera2(self.stereo_system.left_camera, width=800, height=600, keep_ar=True)
            
            #needs to start after the qpicamera2 is made but before window is shown
            self.stereo_system.start()
            #buttons initalize
            button1 = QPushButton(text="Capture",parent=rpiUI)
            button1.clicked.connect(self.image_capture)

            button2 = QPushButton(text="Quit",parent=rpiUI)
            button2.clicked.connect(self.quitting)

            button3 = QPushButton(text="Start Server and Cameras",parent=rpiUI)
            button3.clicked.connect(lambda: self.server.start_server())

            button4 = QPushButton(text="4",parent=rpiUI)
            button4.clicked.connect(lambda : print(":)"))


            #creating the grid layout
            layout=QGridLayout()
            layout.addWidget(button1,0,2)
            layout.addWidget(button2,1,2)
            layout.addWidget(button3,2,2)
            layout.addWidget(button4,3,2)
            layout.addWidget(qpicamera2,0,0,3,1) 
                
            
            #setting the button size
            buttonheight=120
            buttonwidth=300

            widget = QWidget()
            widget.setLayout(layout)
            button1.setFixedSize(buttonwidth,buttonheight)
            button2.setFixedSize(buttonwidth,buttonheight)
            button3.setFixedSize(buttonwidth,buttonheight)
            button4.setFixedSize(buttonwidth,buttonheight)
            rpiUI.setCentralWidget(widget)

            #show UI        
            rpiUI.show()
            self.app.exec()


if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()
    rpi.UI_start()
