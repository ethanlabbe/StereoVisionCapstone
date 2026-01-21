from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
from libcamera import controls, Transform
import cv2
import time

class StereoCameraAcquisition:
    def __init__(self, left_camera_id=0, right_camera_id=1, frame_rate=30):
        self.left_camera = Picamera2(camera_num=left_camera_id)
        self.right_camera = Picamera2(camera_num=right_camera_id)
        
        self.framerate = frame_rate
        self.ctrls = {"FrameRate": self.framerate,}

        self.left_config_still = self.left_camera.create_still_configuration(main={"size": (4056, 3040)}, controls={**self.ctrls, 'SyncMode': controls.rpi.SyncModeEnum.Server})
        self.right_config_still = self.right_camera.create_still_configuration(main={"size": (4056, 3040)}, controls={**self.ctrls, 'SyncMode': controls.rpi.SyncModeEnum.Client})
        
        self.left_config_preview = self.left_camera.create_preview_configuration(lores={"size": (4056, 3040), "format": "YUV420",}, controls={**self.ctrls, 'SyncMode': controls.rpi.SyncModeEnum.Server})
        self.right_config_preview = self.right_camera.create_preview_configuration(lores={"size": (4056, 3040), "format": "YUV420"}, controls={**self.ctrls, 'SyncMode': controls.rpi.SyncModeEnum.Client})

    def configure_cameras(self, configL, configR):
        self.left_camera.configure(configL)
        self.right_camera.configure(configR)
        
    def start(self):
        self.left_camera.start()
        self.right_camera.start()
        time.sleep(2)  # Allow cameras to warm up
        
    def initialize_cameras(self):
        self.stop()
        self.configure_cameras(self.left_config_preview, self.right_config_preview)

    def capture_stereo_image(self):
        reqL = self.left_camera.capture_sync_request()
        reqR = self.right_camera.capture_sync_request()
        
        frameL = reqL.make_array("main")
        frameR = reqR.make_array("main")
        
        reqL.release()
        reqR.release()
        
        return frameL, frameR
        
    def display_preview(self):
        self.left_camera.start_preview(Preview.QTGL, x=int(1024*2/3), y=int(1024*1/3), width=int(1024*2/3), height=int(1024*1/3),transform=Transform(vflip=1))
        self.right_camera.start_preview(Preview.QTGL, x=int(1024*2/3), y=int(1024*1/3), width=int(1024*2/3), height=int(1024*1/3),transform=Transform(vflip=1))
        self.start()
        
    def stop_preview(self):
        self.left_camera.stop_preview()
        self.right_camera.stop_preview()
        self.left_camera.stop()
        self.right_camera.stop()
        
    def stop(self):
        self.left_camera.stop()
        self.right_camera.stop()
        time.sleep(2)
        
    


if __name__ == "__main__":
    stereo_system = StereoCameraAcquisition()
    running = True
    stereo_system.initialize_cameras()
    stereo_system.display_preview()
    while running:
        response = input("Press Enter to capture images or 'exit' to quit: ")
        if response == 'exit':
            stereo_system.stop_preview()
            running = False
        else:
            frameL, frameR = stereo_system.capture_stereo_image()
            cv2.imwrite("left.jpg", cv2.cvtColor(frameL, cv2.COLOR_RGB2BGR))
            cv2.imwrite("right.jpg", cv2.cvtColor(frameR, cv2.COLOR_RGB2BGR))


