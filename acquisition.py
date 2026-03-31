from picamera2 import Picamera2, Preview
from libcamera import controls, Transform
import cv2
import time
import datetime
import json
import os

RIGHT_CAMERA_ID = '/base/axi/pcie@1000120000/rp1/i2c@88000/imx500@1a'
LEFT_CAMERA_ID = '/base/axi/pcie@1000120000/rp1/i2c@80000/imx500@1a'

class StereoCameraAcquisition:
    def __init__(self, frame_rate=30):
        self.connect_cameras()
        
        self.framerate = frame_rate
        self.ctrls = {"FrameRate": self.framerate,}

        self.left_config = self.left_camera.create_preview_configuration(main={"size": (2028, 1520)}, lores={"size":(1024, 600)}, controls={**self.ctrls, 'SyncMode': controls.rpi.SyncModeEnum.Server})
        self.right_config = self.right_camera.create_preview_configuration(main={"size": (2028, 1520)}, controls={**self.ctrls, 'SyncMode': controls.rpi.SyncModeEnum.Client})

    def connect_cameras(self, camera_id=None):
        """Connect to cameras ensuring they are in the correct left/right order"""
        available_cameras = Picamera2.global_camera_info()
        print(available_cameras)
        for idx, cam in enumerate(available_cameras):
            if 'Id' in cam:
                if cam['Id'] == LEFT_CAMERA_ID:
                    self.left_camera = Picamera2(cam['Num'])
                elif cam['Id'] == RIGHT_CAMERA_ID:
                    self.right_camera = Picamera2(cam['Num'])


    def configure_cameras(self, configL, configR):
        self.left_camera.configure(configL)
        self.right_camera.configure(configR)
        
    def start(self):
        self.left_camera.start()
        self.right_camera.start()
#        time.sleep(2)  # Allow cameras to warm up
        
    def initialize_cameras(self):
        self.stop()
        self.configure_cameras(self.left_config, self.right_config)

    def capture_stereo_image(self):
        # capture requests and attempt to record precise timestamps
        reqL = self.left_camera.capture_sync_request()
        reqR = self.right_camera.capture_sync_request()

        frameL = reqL.make_array("main")
        frameR = reqR.make_array("main")

        reqL.release()
        reqR.release()

        return frameL, frameR

    def _request_timestamp_ns(self, req):
        """Try to extract a high-resolution timestamp (ns) from a request's metadata.
        Returns integer nanoseconds or None if unavailable.
        """
        try:
            # Picamera2/libcamera may expose metadata via get_metadata()
            meta = None
            if hasattr(req, 'get_metadata'):
                meta = req.get_metadata()
            elif hasattr(req, 'metadata'):
                meta = req.metadata
            if isinstance(meta, dict):
                # Common keys that might contain timestamps
                for k in ('SensorTimestamp', 'Timestamp', 'sensor_timestamp', 'timestamp'):
                    if k in meta and meta[k] is not None:
                        try:
                            return int(meta[k])
                        except Exception:
                            pass
        except Exception:
            pass
        return None

    def _ns_to_iso(self, ts_ns):
        return datetime.datetime.fromtimestamp(ts_ns / 1e9).strftime('%H:%M:%S.%f')[:-3]

    def _overlay_timestamp(self, frame, ts_ns, position=(10, 30), color=(0, 255, 255), scale=1.0, thickness=2):
        """Overlay a timestamp (given in ns) on an RGB frame and return BGR image."""
        ts_str = self._ns_to_iso(ts_ns)
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        cv2.putText(bgr, ts_str, position, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)
        return bgr
        
    def display_preview(self, width=1024, height=600):
        self.left_camera.start_preview(Preview.QTGL, x=int(0), y=int(0), width=int(width), height=int(height), transform=Transform(vflip=0))
        self.start()
        
    def stop(self):
        self.left_camera.stop()
        self.right_camera.stop()
        
    

if __name__ == "__main__":
    stereo_system = StereoCameraAcquisition()
    input("Press Enter to initialize cameras...")
    running = True
    stereo_system.initialize_cameras()
    stereo_system.display_preview()
    while running:
        response = input("Press Enter to capture images or 'exit' to quit: ")
        if response == 'exit':
            stereo_system.stop()
            running = False
        else:
            (frameL, tsL), (frameR, tsR) = stereo_system.capture_stereo_image()

            # choose a file timestamp based on the earlier exposure to group files
            group_ts_ns = min(tsL, tsR)
            file_ts = datetime.datetime.fromtimestamp(group_ts_ns / 1e9).strftime("%H%M%S_%f")[:-3]

            left_bgr = stereo_system._overlay_timestamp(frameL, tsL)
            right_bgr = stereo_system._overlay_timestamp(frameR, tsR)

            left_filename = f"left_{file_ts}.jpg"
            right_filename = f"right_{file_ts}.jpg"

            cv2.imwrite(left_filename, left_bgr)
            cv2.imwrite(right_filename, right_bgr)

            # save a JSON sidecar with precise timestamps (ns and ISO) and delta
            meta = {
                "left": {
                    "filename": left_filename,
                    "ts_ns": int(tsL),
                    "ts_iso": stereo_system._ns_to_iso(tsL)
                },
                "right": {
                    "filename": right_filename,
                    "ts_ns": int(tsR),
                    "ts_iso": stereo_system._ns_to_iso(tsR)
                },
                "delta_ms": (int(tsR) - int(tsL)) / 1e6
            }
            meta_filename = f"metadata_{file_ts}.json"
            with open(meta_filename, 'w') as jf:
                json.dump(meta, jf, indent=2)


