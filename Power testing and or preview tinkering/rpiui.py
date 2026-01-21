from image_transfer import ImageServerHost
from acquisition import StereoCameraAcquisition
import cv2
import threading

#ui imports
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

class RaspberryPiStereoSystem:
    def __init__(self):
        self.running = False

        # bind to a local IP address reachable on your network
        self.server = ImageServerHost(host='localhost', port=8080)
        self.stereo_system = StereoCameraAcquisition()

    def save_images_locally(self, left_image, right_image, left_filename="left_image.jpg", right_filename="right_image.jpg"):
        cv2.imwrite(left_filename, cv2.cvtColor(left_image, cv2.COLOR_RGB2BGR))
        cv2.imwrite(right_filename, cv2.cvtColor(right_image, cv2.COLOR_RGB2))
        print(f"Images saved locally: {left_filename}, {right_filename}")
    def UI_start(self):
        
        app = QApplication(sys.argv)
        rpiUI= QMainWindow()
        rpiUI.setWindowTitle("Stereo Vision Capstone")
        rpiUI.setGeometry(100, 100, 600, 400)


        #buttons initalize
        button1 = QPushButton(text="Capture",parent=rpiUI)
        button1.clicked.connect(self.image_capture)

        button2 = QPushButton(text="Quit",parent=rpiUI)
        button2.clicked.connect(self.quiting)

        button3 = QPushButton(text="3",parent=rpiUI)
        button3.clicked.connect("Fuction 3")

        button4 = QPushButton(text="4",parent=rpiUI)
        button4.clicked.connect("Fuction 4")


        #creating the stacked layout
        layout=QVBoxLayout()
        layout.addWidget(button1)
        layout.addWidget(button2)
        layout.addWidget(button3)
        layout.addWidget(button4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        #setting the button size
        buttonheight=120
        buttonwidth=480

        widget = QWidget()
        widget.setLayout(layout)
        button1.setFixedSize(buttonwidth,buttonheight)
        button2.setFixedSize(buttonwidth,buttonheight)
        button3.setFixedSize(buttonwidth,buttonheight)
        button4.setFixedSize(buttonwidth,buttonheight)
        rpiUI.setCentralWidget(widget)

        #show UI        
        rpiUI.show()
        app.exec()


    def image_capture(self):
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

    def quiting(self):
        self.running = False
        self.stereo_system.stop_preview()
        self.server.stop_server()
        quit()

    def run(self):
        
        self.running = True
        self.stereo_system.initialize_cameras()
        # start server in background (non-blocking)
        self.server.start_server()
        preview_thread = threading.Thread(target=self.stereo_system.display_preview)
        preview_thread.daemon = True
        preview_thread.start()

            

    
    
if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()
    rpi.UI_start()
