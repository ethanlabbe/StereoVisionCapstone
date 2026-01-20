from image_transfer import ImageServerHost
from acquisition import StereoCameraAcquisition

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

    def save_images_locally(self, left_bytes, right_bytes, left_filename="left_image.jpg", right_filename="right_image.jpg"):
        with open(left_filename, 'wb') as fL:
            fL.write(left_bytes)
        with open(right_filename, 'wb') as fR:
            fR.write(right_bytes)
        print(f"Images saved locally: {left_filename}, {right_filename}")

    def rpi_UI_start():
        
        app = QApplication(sys.argv)
        rpiUI= QMainWindow()
        rpiUI.setWindowTitle("Stereo Vision Capstone")
        rpiUI.setGeometry(100, 100, 600, 400)



        #buttons initalize
        button1 = QPushButton(text="1",parent=rpiUI)
        button1.clicked.connect("Fuction 1")

        button2 = QPushButton(text="2",parent=rpiUI)
        button2.clicked.connect("Fuction 2")

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


    def run(self):
        self.running = True
        self.stereo_system.initialize_cameras()
        # start server in background (non-blocking)
        self.server.start_server()

        self.stereo_system.display_preview()

        while self.running:
            # interface with UI to take images when button pressed
            if ui_button_pressed():
                self.stereo_system.stop_preview()
                imgL, imgR = self.stereo_system.capture_stereo_image()

                # extract raw bytes from your image objects; adjust as needed
                left_bytes = imgL.get_array("main")
                right_bytes = imgR.get_array("main")

                if self.server.connected:
                    try:
                        print("Sending images to client...")
                        self.server.send_images(left_bytes, right_bytes)
                    except Exception as e:
                        print("Failed to send images:", e)
                        self.save_images_locally(left_bytes, right_bytes)
                else:
                    self.save_images_locally(left_bytes, right_bytes)

                self.stereo_system.display_preview()


if __name__ == "__main__":
    rpi = RaspberryPiStereoSystem()
    rpi.run()