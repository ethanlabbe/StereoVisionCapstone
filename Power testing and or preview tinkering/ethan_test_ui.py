from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QWidget, QGridLayout, QStackedLayout
from PyQt5.QtCore import Qt
import sys

class UI():
    def __init__(self):
        self.button_toggle = True
        
    def toggle_server(self):
        if self.button_toggle:
            self.server_button.setText("Start Server")
            self.button_toggle = False
        else:
            self.server_button.setText("Stop Server")
            self.button_toggle = True

    def UI_start(self):

        self.app = QApplication(sys.argv)
        rpiUI = QMainWindow()
        rpiUI.setWindowTitle("Stereo Vision Capstone")
        # Set window to full screen
        rpiUI.showFullScreen()

        # Transparent buttons
        self.server_button = QPushButton(text="Start Server", parent=None)
        self.server_button.clicked.connect(self.toggle_server)
        self.server_button.setStyleSheet(
            "background: transparent; color: black; border: 2px solid black; border-radius: 10px;")

        capture_button = QPushButton(text="Capture", parent=None)
        capture_button.clicked.connect(lambda: print("Capture clicked"))
        capture_button.setStyleSheet(
            "background: transparent; color: black; border: 2px solid black; border-radius: 10px;")

        quit_button = QPushButton(text="Quit", parent=None)
        quit_button.clicked.connect(lambda: rpiUI.close())
        quit_button.setStyleSheet(
            "background: transparent; color: black; border: 2px solid black; border-radius: 10px;")

        # Overlay layout using QStackedLayout
        overlay_widget = QWidget()
        overlay_layout = QStackedLayout(overlay_widget)

        # Button overlay container
        button_container = QWidget()
        button_layout = QGridLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(20)
        button_layout.addWidget(capture_button, 5, 5)
        button_layout.addWidget(self.server_button, 5, 0)
        button_layout.addWidget(quit_button, 0, 5)
        button_container.setLayout(button_layout)

        # Set button sizes
        capture_button.setFixedSize(200, 80)
        self.server_button.setFixedSize(200, 80)
        quit_button.setFixedSize(100, 40)

        overlay_layout.addWidget(button_container)
        overlay_layout.setStackingMode(QStackedLayout.StackAll)

        rpiUI.setCentralWidget(overlay_widget)

        # show UI (already full screen above)
        self.app.exec()


if __name__ == "__main__":
    ui = UI()
    ui.UI_start()