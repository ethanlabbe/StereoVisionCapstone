import cv2
import numpy as np
import matplotlib.pyplot as plt

class CameraCalibration:
    def __init__(self, chessboard_size=(14,9), square_size=0.0181):
        """
        Initialize calibration parameters.
        """
        self.chessboard_size = chessboard_size
        self.square_size = square_size

        # Prepare object points
        self.objp = np.zeros((chessboard_size[1]*chessboard_size[0],3), np.float32)
        self.objp[:,:2] = np.mgrid[0:chessboard_size[0],0:chessboard_size[1]].T.reshape(-1,2)
        self.objp *= square_size #Gets matrix in terms of square size

        # Lists of points
        self.objpoints = []  # 3D points
        self.imgpoints_left = []
        self.imgpoints_right = []

        # Camera matrices and distortion
        self.ML = None
        self.DL = None
        self.MR = None
        self.DR = None
        self.ML_opt = None
        self.MR_opt = None

        # Stereo calibration outputs
        self.R = None
        self.T = None
        self.E = None
        self.F = None
        self.RL = None
        self.RR = None
        self.PL = None
        self.PR = None
        self.Q = None

        # Rectification maps
        self.left_map1 = None
        self.left_map2 = None
        self.right_map1 = None
        self.right_map2 = None

    def decode_img(self, img_left, img_right):
        #Deal with no image read error
        if img_left is None:
            raise FileNotFoundError("Left image not loaded")
        if img_right is None:
            raise FileNotFoundError("Right image not loaded")
        img_left_cv = cv2.imdecode(img_left, cv2.IMREAD_COLOR)
        img_right_cv = cv2.imdecode(img_right, cv2.IMREAD_COLOR)
        return img_left_cv, img_right_cv

    def add_chessboard_corners(self, img_left, img_right, scale, display=False):

        h, w = img_left.shape[:2]

        gray_left = cv2.cvtColor(img_left, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(img_right, cv2.COLOR_BGR2GRAY)

        resized_gray_left = cv2.resize(gray_left, (int(w / scale), int(h / scale)))
        resized_gray_right = cv2.resize(gray_right, (int(w / scale), int(h / scale)))

        ret_left, corners_left = cv2.findChessboardCornersSB(resized_gray_left, self.chessboard_size, None)
        ret_right, corners_right = cv2.findChessboardCornersSB(resized_gray_right, self.chessboard_size, None)

        if ret_left and ret_right:
            corners_left *= scale
            corners_right *=  scale

            self.objpoints.append(self.objp)

            # Subpixel refinement
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners_left = cv2.cornerSubPix(gray_left, corners_left, (11,11), (-1,-1), criteria)
            corners_right = cv2.cornerSubPix(gray_right, corners_right, (11,11), (-1,-1), criteria)

            self.imgpoints_left.append(corners_left)
            self.imgpoints_right.append(corners_right)

            if display:
                cv2.drawChessboardCorners(img_left, self.chessboard_size, corners_left, ret_left)
                cv2.drawChessboardCorners(img_right, self.chessboard_size, corners_right, ret_right)
                cv2.imshow("Left Corners", img_left)
                cv2.imshow("Right Corners", img_right)
                cv2.waitKey(0)
                cv2.destroyAllWindows
        else:
            print("Chessboard not found in one or both images.")
            cv2.imshow("Left Error", img_left)
            cv2.imshow("Right Error", img_right)
            cv2.waitKey(2000)
            cv2.destroyAllWindows

    def calibrate_cameras(self, image_shape, alpha=0.0):
        """
        Calibrate individual cameras and compute optimal new camera matrices.
        alpha: free scaling parameter (0 = crop, 1 = keep all pixels)
        """
        # Left camera
        rmsE1cam, self.ML, self.DL, rvecsL, tvecsL = cv2.calibrateCamera(
            self.objpoints, self.imgpoints_left, image_shape, None, None
        )
        self.ML_opt, _ = cv2.getOptimalNewCameraMatrix(self.ML, self.DL, image_shape, alpha, image_shape)

        # Right camera
        rmsE2cam, self.MR, self.DR, rvecsR, tvecsR = cv2.calibrateCamera(
            self.objpoints, self.imgpoints_right, image_shape, None, None
        )
        self.MR_opt, _ = cv2.getOptimalNewCameraMatrix(self.MR, self.DR, image_shape, alpha, image_shape)

        #RMS reprojection error returned in px
        return rmsE1cam, rmsE2cam, rvecsR, rvecsL, tvecsR, tvecsL



    def stereo_calibrate_and_rectify(self, image_shape):
        """
        Stereo calibration: get R, T, E, F and rectification maps.
        """
        flags = cv2.CALIB_FIX_INTRINSIC #Fixes intrinsics determined from camera calibration 
        criteria = (cv2.TERM_CRITERIA_MAX_ITER + cv2.TERM_CRITERIA_EPS, 100, 1e-5)

        rmsReprojEstereo, _, _, _, _, self.R, self.T, self.E, self.F = cv2.stereoCalibrate(
            self.objpoints,
            self.imgpoints_left,
            self.imgpoints_right,
            self.ML_opt,
            self.DL,
            self.MR_opt,
            self.DR,
            image_shape,
            criteria=criteria,
            flags=flags
        )

        # Rectification
        self.RL, self.RR, self.PL, self.PR, self.Q, _, _ = cv2.stereoRectify(
            self.ML_opt, self.DL, self.MR_opt, self.DR, image_shape, self.R, self.T
        )

        # Precompute rectification maps
        self.left_map1, self.left_map2 = cv2.initUndistortRectifyMap(
            self.ML_opt, self.DL, self.RL, self.PL, image_shape, cv2.CV_32FC1
        )
        self.right_map1, self.right_map2 = cv2.initUndistortRectifyMap(
            self.MR_opt, self.DR, self.RR, self.PR, image_shape, cv2.CV_32FC1
        )
        
        return rmsReprojEstereo, self.Q

    def get_rectification_maps(self):
        """
        Return rectification maps for stereo rectification.
        """
        return self.left_map1, self.left_map2, self.right_map1, self.right_map2
    
#STEREO COMPUTATION CLASS
class StereoSystem:
    #Blocksize 7 (must be odd number between 3 and 11)
    def __init__(self, min_disp=0, num_disp=16 * 8, block_size=15, lambda_val=8000, sigma_color=1.4):
        self.min_disp = min_disp
        self.num_disp = num_disp
        self.block_size = block_size

        self.matcher_left = cv2.StereoSGBM_create(
            minDisparity=self.min_disp,
            numDisparities=self.num_disp,
            blockSize=self.block_size,
            #Calculation per documentation in SGBM class
            P1=8*3*self.block_size**2,
            P2=32*3*self.block_size**2,
            uniquenessRatio = 7,
            speckleWindowSize = 50, #Was 50
            speckleRange = 1, #Was 1
            #Consider MODE_SGBM for less memory consumption
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
        )

        self.matcher_right = cv2.ximgproc.createRightMatcher(self.matcher_left)


        #LRCThresh default is 24 (1.5 px)
        #Can use .getConfidenceMap() 
        #Lambda and SigmaColor values per documentation recommendation
        self.wls_filter = cv2.ximgproc.createDisparityWLSFilter(matcher_left=self.matcher_left)
        self.wls_filter.setLambda(lambda_val)
        self.wls_filter.setSigmaColor(sigma_color)

        self.left_map1 = None
        self.left_map2 = None
        self.right_map1 = None
        self.right_map2 = None
        self.Q = None


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
                self.left_map1 = data['rect_mapL1']
                self.left_map2 = data['rect_mapL2']
                self.right_map1 = data['rect_mapR1']
                self.right_map2 = data['rect_mapR2']
        else:
            # maps will need to be generated later
            self.rect_mapL1 = self.rect_mapL2 = None
            self.rect_mapR1 = self.rect_mapR2 = None

    def set_rectification(self, left_map1, left_map2, right_map1, right_map2, Q):
        self.left_map1 = left_map1
        self.left_map2 = left_map2
        self.right_map1 = right_map1
        self.right_map2 = right_map2
        self.Q = Q

    def rectify_pair(self, imgL, imgR):
        imgL_rect = cv2.remap(imgL, self.left_map1, self.left_map2, cv2.INTER_LINEAR)
        imgR_rect = cv2.remap(imgR, self.right_map1, self.right_map2, cv2.INTER_LINEAR)
        return imgL_rect, imgR_rect

    def compute_disparity(self, imgL, imgR):
        dispL = self.matcher_left.compute(imgL, imgR).astype(np.float32) 
        dispR = self.matcher_right.compute(imgR, imgL).astype(np.float32) 

        dispL_filtered = self.wls_filter.filter(dispL, imgL, None, dispR) / 16.0
        dispR = dispR / 16.0
        dispL = dispL / 16.0
        return dispL_filtered, dispL, dispR

    def disparity_to_depth(self, disparity):
        if self.Q is None:
            raise ValueError("Reprojection matrix Q not set.")
        points_3D = cv2.reprojectImageTo3D(disparity, self.Q)
        depth = points_3D[:,:,2]


        return depth
    
    def visualize_depth_map(self, depth, title='Depth Map'):
        depth[depth <= 0] = np.nan  # Mask invalid values
        plt.figure(figsize=(10, 7))
        plt.imshow(depth, cmap='plasma', vmax=10, vmin=0)
        plt.colorbar(label='Depth (meters)')
        plt.title(title)
        plt.xlabel('Pixel X')
        plt.ylabel('Pixel Y')
        plt.show()
    
    def image_display(self, array):
        #Use PLT not CV2
        cv2.imshow("Image", array)            
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def save_stereo_rectification(Q, left_map1, left_map2, right_map1, right_map2, filename):
        np.savez(
            filename,
            Q=Q,
            left_map1=left_map1,
            left_map2=left_map2,
            right_map1=right_map1,
            right_map2=right_map2
        )

    def load_stereo_rectification(filename):
        data = np.load(filename)
        return data["Q"], data["left_map1"], data["left_map2"],data["right_map1"], data["right_map2"]




