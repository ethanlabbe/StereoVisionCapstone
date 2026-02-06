import cv2
import numpy as np


class StereoSystem:
    def __init__(self):
        self.chessboard_size = (9, 6)  # Number of inner corners per chessboard row and column
        self.square_size = 0.025  # Size of a square in meters
        
        self.corners_L = []
        self.corners_R = []
        self.objpoints = []
        
        self.window_size = 5
        self.min_disp = 0
        self.num_disp = 16 * 12  # Must be divisible by 16
        self.stereo = cv2.StereoSGBM_create(
            minDisparity=self.min_disp,
            numDisparities=self.num_disp,
            blockSize=5,
            P1=8 * 3 * self.window_size ** 2,
            P2=32 * 3 * self.window_size ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32
        )
        
        
    def find_calibration_corners(self, img_left, img_right):
        gray_left = cv2.cvtColor(img_left, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(img_right, cv2.COLOR_BGR2GRAY)
        
        self.calib_size = gray_left.shape[::-1]
        
        flags = cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
        
        ret_left, corners_left = cv2.findChessboardCornersSB(gray_left, self.chessboard_size, flags)
        ret_right, corners_right = cv2.findChessboardCornersSB(gray_right, self.chessboard_size, flags)
        
        if ret_left and ret_right:
            self.corners_L.append(corners_left)
            self.corners_R.append(corners_right)
            objp = np.zeros((self.chessboard_size[0] * self.chessboard_size[1], 3), np.float32)
            objp[:, :2] = np.mgrid[0:self.chessboard_size[0], 0:self.chessboard_size[1]].T.reshape(-1, 2) * self.square_size
            self.objpoints.append(objp)
            return ret_left, corners_left, ret_right, corners_right
        else:
            print("Chessboard corners not found in one or both images.")
            return False, None, False, None
    
        
    
    
    def calibrate_stereo_system(self):
        flags = cv2.CALIB_FIX_INTRINSIC
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6)
        
        self.retL, self.mtxL, self.distL, self.rvecsL, self.tvecsL = cv2.calibrateCamera(
            self.objpoints, self.corners_L, self.calib_size, None, None)
        self.retR, self.mtxR, self.distR, self.rvecsR, self.tvecsR = cv2.calibrateCamera(
            self.objpoints, self.corners_R, self.calib_size, None, None)
        
        self.stereo_ret, self.R, self.T, self.E, self.F = cv2.stereoCalibrate(
            self.objpoints, self.corners_L, self.corners_R, self.calib_size, None, None, None, None, criteria)

    def generate_rectification_maps(self):
        self.R1, self.R2, self.P1, self.P2, self.Q, _, _ = cv2.stereoRectify(
            self.mtxL, self.distL, self.mtxR, self.distR, self.calib_size, self.R, self.T)
        
        self.rect_mapL1, self.rect_mapL2 = cv2.initUndistortRectifyMap(
            self.mtxL, self.distL, self.R1, self.P1, self.calib_size, cv2.CV_16SC2)
        self.rect_mapR1, self.rect_mapR2 = cv2.initUndistortRectifyMap(
            self.mtxR, self.distR, self.R2, self.P2, self.calib_size, cv2.CV_16SC2)
        return self.rect_mapL1, self.rect_mapL2, self.rect_mapR1, self.rect_mapR2, self.Q
    
    def save_calibration_parameters(self, filename):
        np.savez(filename,
                 mtxL=self.mtxL, distL=self.distL,
                 mtxR=self.mtxR, distR=self.distR,
                 R=self.R, T=self.T,
                 rect_mapL1=self.rect_mapL1, rect_mapL2=self.rect_mapL2,
                 rect_mapR1=self.rect_mapR1, rect_mapR2=self.rect_mapR2,
                 Q=self.Q)
    
    def rectify_pair(self, img_left, img_right):
        img_left_rect = cv2.remap(img_left, self.rect_mapL1, self.rect_mapL2, cv2.INTER_LINEAR)
        img_right_rect = cv2.remap(img_right, self.rect_mapR1, self.rect_mapR2, cv2.INTER_LINEAR)
        return img_left_rect, img_right_rect
        
        
    def compute_disparity(self, img_left, img_right):
        img_left_gray = cv2.cvtColor(img_left, cv2.COLOR_BGR2GRAY)
        img_right_gray = cv2.cvtColor(img_right, cv2.COLOR_BGR2GRAY)
        disp_left = self.stereo.compute(img_left, img_right).astype(np.float32) / 16.0
        disp_right = self.stereo.compute(img_right, img_left).astype(np.float32) / 16.0
        
        # WLS filtering
        wls_filter = cv2.ximgproc.createDisparityWLSFilter(matcher_left=self.stereo)
        wls_filter.setLambda(8000.0)
        wls_filter.setSigmaColor(1.5)
        
        disp_left_filtered = wls_filter.filter(disp_left, img_left_gray, None, disp_right)
        
        return disp_left_filtered, disp_left, disp_right
    
    def generate_depth_map(self, disparity):
        with np.errstate(divide='ignore'):
            depth_map = cv2.reprojectImageTo3D(disparity, self.Q)
        return depth_map