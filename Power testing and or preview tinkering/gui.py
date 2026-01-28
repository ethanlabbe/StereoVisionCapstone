import sys
from picamera2 import Picamera2, Preview
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        buttonheight=120
        buttonwidth=480

        self.setWindowTitle("Stereo Vision Capstone")
        self.setGeometry(100, 100, 600, 400)

       
        
        #widgets initalize
        button1 = QPushButton(text="1",parent=self)
        button1.clicked.connect(self.button1click)

        button2 = QPushButton(text="2",parent=self)
        button2.clicked.connect(self.button2click)

        button3 = QPushButton(text="3",parent=self)
        button3.clicked.connect(self.button3click)

        button4 = QPushButton(text="4",parent=self)
        button4.clicked.connect(self.button4click)

        layout=QVBoxLayout()
        layout.addWidget(button1)
        layout.addWidget(button2)
        layout.addWidget(button3)
        layout.addWidget(button4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        widget = QWidget()
        widget.setLayout(layout)
        button1.setFixedSize(buttonwidth,buttonheight)
        button2.setFixedSize(buttonwidth,buttonheight)
        button3.setFixedSize(buttonwidth,buttonheight)
        button4.setFixedSize(buttonwidth,buttonheight)
        self.setCentralWidget(widget)
        

    def button1click(self):
        picam2 = Picamera2()
        picam2.start_preview(Preview.QTGL)

    def button2click(self):
        #second button code
        print("hi2")

    def button3click(self):
        #first button code
        print("hi3")

    def button4click(self):
        #first button code
        print("hi4")


    

app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()