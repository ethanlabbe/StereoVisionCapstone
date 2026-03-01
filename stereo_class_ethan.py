import cv2
import numpy as np
import matplotlib.pyplot as plt

class StereoSystem:
    def __init__(self):
        self.chessboard_size = (14, 9)  # Number of inner corners per chessboard row and column
        self.square_size = 0.0181  # Size of a square in meters
        
        self.corners_L = []
        self.corners_R = []
        self.objpoints = []
        
        self.window_size = 5
        self.min_disp = 0
        self.num_disp = 16 * 20  # Must be divisible by 16
        self.left_matcher = cv2.StereoSGBM_create(
            minDisparity=self.min_disp,
            numDisparities=self.num_disp,
            blockSize=5,
            P1=8 * 3 * self.window_size ** 2,
            P2=32 * 3 * self.window_size ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=150,
            speckleRange=1
        )
        self.right_matcher = cv2.ximgproc.createRightMatcher(self.left_matcher)
        
        
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
            return False, None, False, None
    
    
    def calibrate_stereo_system(self):
        flags = cv2.CALIB_FIX_INTRINSIC
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6)
        
        self.retL, self.mtxL, self.distL, self.rvecsL, self.tvecsL = cv2.calibrateCamera(
            self.objpoints, self.corners_L, self.calib_size, None, None)
        self.retR, self.mtxR, self.distR, self.rvecsR, self.tvecsR = cv2.calibrateCamera(
            self.objpoints, self.corners_R, self.calib_size, None, None)
        
        self.stereo_ret, _, _, _, _, self.R, self.T, self.E, self.F = cv2.stereoCalibrate(
            self.objpoints, self.corners_L, self.corners_R, 
            self.mtxL, self.distL, self.mtxR, self.distR,
            self.calib_size, flags=flags, criteria=criteria)

    def generate_rectification_maps(self):
        self.R1, self.R2, self.P1, self.P2, self.Q, _, _ = cv2.stereoRectify(
            self.mtxL, self.distL, self.mtxR, self.distR, self.calib_size, self.R, self.T)
        
        self.rect_mapL1, self.rect_mapL2 = cv2.initUndistortRectifyMap(
            self.mtxL, self.distL, self.R1, self.P1, self.calib_size, cv2.CV_16SC2)
        self.rect_mapR1, self.rect_mapR2 = cv2.initUndistortRectifyMap(
            self.mtxR, self.distR, self.R2, self.P2, self.calib_size, cv2.CV_16SC2)
        return self.rect_mapL1, self.rect_mapL2, self.rect_mapR1, self.rect_mapR2, self.Q
    
    def save_calibration_parameters(self, filename, include_rect_maps=True, compressed=True):
        data = {
            'mtxL': self.mtxL, 'distL': self.distL,
            'mtxR': self.mtxR, 'distR': self.distR,
            'R': self.R, 'T': self.T,
            'Q': self.Q,
        }
        if include_rect_maps:
            data.update({
                'rect_mapL1': self.rect_mapL1,
                'rect_mapL2': self.rect_mapL2,
                'rect_mapR1': self.rect_mapR1,
                'rect_mapR2': self.rect_mapR2,
            })
        save_fn = np.savez_compressed if compressed else np.savez
        save_fn(filename, **data)
        
    def load_calibration_parameters(self, filename):
        data = np.load(filename)
        self.mtxL = data['mtxL']
        self.distL = data['distL']
        self.mtxR = data['mtxR']
        self.distR = data['distR']
        self.R = data['R']
        self.T = data['T']
        self.Q = data['Q']
        if 'rect_mapL1' in data:
            self.rect_mapL1 = data['rect_mapL1']
            self.rect_mapL2 = data['rect_mapL2']
            self.rect_mapR1 = data['rect_mapR1']
            self.rect_mapR2 = data['rect_mapR2']
        else:
            # maps will need to be generated later
            self.rect_mapL1 = self.rect_mapL2 = None
            self.rect_mapR1 = self.rect_mapR2 = None
    
    def rectify_pair(self, img_left, img_right):
        img_left_rect = cv2.remap(img_left, self.rect_mapL1, self.rect_mapL2, cv2.INTER_LINEAR)
        img_right_rect = cv2.remap(img_right, self.rect_mapR1, self.rect_mapR2, cv2.INTER_LINEAR)
        return img_left_rect, img_right_rect

    def compute_disparity(self, imgL, imgR):
        if imgL.ndim == 3:
            imgL = cv2.cvtColor(imgL, cv2.COLOR_BGR2GRAY)
        if imgR.ndim == 3:
            imgR = cv2.cvtColor(imgR, cv2.COLOR_BGR2GRAY)

        # Keep CV_16S here (no float conversion!)
        dispL_16 = self.left_matcher.compute(
            imgL, imgR)      # CV_16S, scaled by 16
        dispR_16 = self.right_matcher.compute(
            imgR, imgL)     # CV_16S, scaled by 16

        wls = cv2.ximgproc.createDisparityWLSFilter(matcher_left=self.left_matcher)
        wls.setLambda(8000.0)
        wls.setSigmaColor(1.5)

        # Correct Python signature: filter(disparity_left, left_view, disparity_right)
        dispL_filt_16 = wls.filter(dispL_16, imgL, disparity_map_right=dispR_16)

        # Convert AFTER filtering
        dispL_filtered = dispL_filt_16.astype(np.float32) / 16.0
        dispL = dispL_16.astype(np.float32) / 16.0
        dispR = dispR_16.astype(np.float32) / 16.0

        return dispL_filtered, dispL, dispR


    def disparity_to_depth(self, disparity):
        if self.Q is None:
            raise ValueError("Reprojection matrix Q not set.")

        disp = disparity.astype(np.float32).copy()

        # Valid disparity should be > 0 for standard rectified pairs
        invalid = (~np.isfinite(disp)) | (disp <= 0)
        disp[invalid] = -1.0

        pts3d = cv2.reprojectImageTo3D(disp, self.Q, handleMissingValues=True)
        Z = pts3d[:, :, 2].astype(np.float32)

        # If your Z sign is now correct after swapping cameras, you can drop abs().
        depth = Z
        depth[invalid] = np.nan
        depth[~np.isfinite(depth)] = np.nan

        # Optional: remove absurd values that are almost always “bad disparity”
        depth[(depth < 0.05) | (depth > 1.2)] = np.nan  # tune for your scene
        return depth

    def visualize_depth_map(self, depth, title='Depth Map'):
        depth[depth <= 0] = np.nan  # Mask invalid values

        plt.figure(figsize=(10, 7))
        plt.imshow(depth, cmap='plasma')
        plt.colorbar(label='Depth (meters)')
        plt.title(title)
        plt.xlabel('Pixel X')
        plt.ylabel('Pixel Y')
        plt.show()

    def display_image(self, img, title="Image"):
        plt.figure(figsize=(10, 7))
        plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        plt.title(title)
        plt.axis('off')
        plt.show()
