import os
import cv2
import datetime
import threading


# ui imports
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QGridLayout, QWidget, QLabel, QStackedLayout, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import Qt


class RaspberryPiStereoSystem:
    def __init__(self):
        self.running = False
        self.toggle = True

        # bind to a local IP address reachable on your network
        self.folder_path = ""

    def save_images_locally(self, left_image, right_image, left_filename="left_image.jpg", right_filename="right_image.jpg", folder="simonspi/Desktop/images"):
        time_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(folder + "/" + left_filename + "_" + time_stamp,
                    cv2.cvtColor(left_image, cv2.COLOR_RGB2BGR))
        cv2.imwrite(folder + "/" + right_filename + "_" + time_stamp,
                    cv2.cvtColor(right_image, cv2.COLOR_RGB2BGR))
        print(f"Images saved locally")

    def toggle_server(self):
        if self.toggle:
            self.server_button.setText("Start Server")
            self.toggle = False
        else:
            self.server_button.setText("Stop Server")
            self.toggle = True

    def run(self):
        self.running = True

        # start server in background (non-blocking)

        self.folder_path = "rpi/desktop/images/" + 'temp'
        if not os.path.exists(self.folder_path):
            try:
                os.makedirs(self.folder_path)
            except Exception as e:
                print("Failed to create folder:", e)
                self.folder_path = "rpi/desktop/images/"

        # self.stereo_system.display_preview()

    def quitting(self):
        self.app.quit()


    def UI_start(self):

        self.app = QApplication(sys.argv)
        rpiUI = QMainWindow()
        rpiUI.setWindowTitle("Stereo Vision Capstone")
        # Set window to full screen
        rpiUI.showFullScreen()

        # Picamera2 preview widget
        #qpicamera2 = QGlPicamera2(self.stereo_system.left_camera, width=1024, height=600, keep_ar=True)

        # Transparent buttons
        self.server_button = QPushButton(text="Start Server", parent=None)
        self.server_button.clicked.connect(self.toggle_server)
        self.server_button.setStyleSheet(
            "background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px;")

        capture_button = QPushButton(text="Capture", parent=None)
        capture_button.clicked.connect(lambda: print("Capture button clicked"))
        capture_button.setStyleSheet(
            "background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px;")

        quit_button = QPushButton(text="Quit", parent=None)
        quit_button.clicked.connect(self.quitting)
        quit_button.setStyleSheet(
            "background: rgba(0,0,0,0.3); color: white; border: 2px solid white; border-radius: 10px;")

        # Use QWidget as central widget for absolute positioning
        central_widget = QWidget()
        central_widget.setStyleSheet("background: transparent;")
        rpiUI.setCentralWidget(central_widget)

        # Picamera display as background
        #qpicamera2.setParent(central_widget)
        #qpicamera2.setGeometry(0, 0, 1024, 600)

        # Button sizes
        self.server_button.setFixedSize(200, 80)
        capture_button.setFixedSize(200, 80)
        quit_button.setFixedSize(100, 40)

        # Absolute positioning for buttons
        self.server_button.setParent(central_widget)
        self.server_button.move(20, 600 - 80 - 20)  # Bottom-left

        capture_button.setParent(central_widget)
        capture_button.move(1024 - 200 - 20, 600 - 80 - 20)  # Bottom-right

        quit_button.setParent(central_widget)
        quit_button.move(1024 - 100 - 20, 20)  # Top-right

        # Show UI
        self.app.exec()


if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()
    rpi.UI_start()
