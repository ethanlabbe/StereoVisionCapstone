import socket
import threading
import struct
import time
import sys
import queue

class ImageServerHost:
    """Non-blocking image server that accepts a single client and sends images
    on demand via `send_images(left_bytes, right_bytes=None)`.
    Images are sent as a 4-byte header prefix followed by image payload.
    """
    def __init__(self, host='localhost', port=8080):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_socket = None
        self.connected = False
        self._lock = threading.Lock()
        self._accept_thread = None
        self._client_threads = []
        self._running = False
        self._image_queue = queue.Queue()
        self._queue_thread = None
        self.on_send_start = None
        self.on_send_complete = None

    def start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        
        #Unblock the accept loop every 1 second
        self.server_socket.settimeout(1.0) 
        
        self._running = True
        print(f"Image server started on {self.host}:{self.port}")
        
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        
        self._queue_thread = threading.Thread(target=self._queue_loop, daemon=True)
        self._queue_thread.start()

    def _queue_loop(self):
        while self._running:
            try:
                item = self._image_queue.get(timeout=0.1)
            except queue.Empty:
                continue
                
            left_image, right_image = item
            
            with self._lock:
                if not self.connected or not self.client_socket:
                    print("No client connected, skipping image send")
                    continue
                sock = self.client_socket
                
            try:
                left_image_bytes = left_image if isinstance(left_image, bytes) else left_image.tobytes()
                right_image_bytes = right_image if isinstance(right_image, bytes) else right_image.tobytes()
                
                # TRIGGER START CALLBACK
                if self.on_send_start:
                    self.on_send_start()
                
                sock.sendall(struct.pack('>I', 0))  # left image indicator
                sock.sendall(struct.pack('>I', len(left_image_bytes)))
                sock.sendall(left_image_bytes)
                
                sock.sendall(struct.pack('>I', 1))  # right image indicator
                sock.sendall(struct.pack('>I', len(right_image_bytes)))
                sock.sendall(right_image_bytes)
                
                # TRIGGER COMPLETE CALLBACK
                if self.on_send_complete:
                    self.on_send_complete()
                    
                print(f"Image(s) sent to client (from queue)")
            except Exception as e:
                print("Error sending images from queue:", e)
                with self._lock:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    self.client_socket = None
                    self.connected = False


    def _accept_loop(self):
        while self._running:
            try:
                client_sock, addr = self.server_socket.accept()
            except socket.timeout:
                #Ignore the timeout, loop back and check self._running
                continue 
            except OSError:
                print("Server socket closed, stopping accept loop")
                break
            
            with self._lock:
                # if another client is connected, refuse new connection
                if self.client_socket:
                    try:
                        client_sock.close()
                    except Exception:
                        pass
                    continue
                self.client_socket = client_sock
                self.connected = True
            print(f"Client connected from {addr}")
            
            t = threading.Thread(target=self._client_monitor, args=(client_sock,), daemon=True)
            t.start()
            self._client_threads.append(t)

    def _client_monitor(self, client_sock):
        try:
            # Block on recv with small peek to detect disconnect
            while True:
                try:
                    data = client_sock.recv(1, socket.MSG_PEEK)
                    if not data:
                        break
                    time.sleep(0.1)
                except BlockingIOError:
                    time.sleep(0.1)
                except Exception:
                    break
        finally:
            with self._lock:
                if self.client_socket is client_sock:
                    try:
                        client_sock.close()
                    except Exception:
                        pass
                    self.client_socket = None
                    self.connected = False
            print("Client disconnected")

    def send_images(self, left_image, right_image):
        """Queue one or two images for sending to the connected client.
        Images will be sent in the background when a client is connected.
        Raises ConnectionError if no client is connected."""
        with self._lock:
            if not self.connected or not self.client_socket:
                raise ConnectionError("No client connected")
        self._image_queue.put((left_image, right_image))
        print(f"Images queued for transfer")

    def stop_server(self):
        self._running = False
        try:
            if self.server_socket:
                self.server_socket.close()
        except Exception:
            pass
        with self._lock:
            if self.client_socket:
                try:
                    self.client_socket.close()
                except Exception:
                    pass
                self.client_socket = None
            self.connected = False
        # join background threads so they don't run during interpreter shutdown
        try:
            if self._accept_thread:
                self._accept_thread.join(timeout=2)
        except Exception:
            pass
        for t in list(self._client_threads):
            try:
                t.join(timeout=1)
            except Exception:
                pass
        try:
            if self._queue_thread:
                self._queue_thread.join(timeout=2)
        except Exception:
            pass
        try:
            sys.stdout.flush()
        except Exception:
            pass


class ImageClient:
    """Client that connects and receives length-prefixed images.
    """
    def __init__(self, server_host='localhost', server_port=8080):
        self.sock = None
        self.server_host = server_host
        self.server_port = server_port
        self.connected = False
        
    def _recv_all(self, n):
        data = bytearray()
        while len(data) < n:
            packet = self.sock.recv(n - len(data))
            if not packet:
                raise ConnectionError('Socket closed while receiving')
            data.extend(packet)
        return bytes(data)

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.server_host, self.server_port))
        self.connected = True
        print(f"Connected to server {self.server_host}:{self.server_port}")
    
    #receive 2 images
    def receive_images(self):
        # Receive left image indicator
        indicator_data = self._recv_all(4)
        indicator = struct.unpack('>I', indicator_data)[0]
        if indicator != 0:
            print("Expected left image indicator, got:", indicator)
        # Receive left image
        length_data = self._recv_all(4)
        length = struct.unpack('>I', length_data)[0]
        left_image_bytes = self._recv_all(length)
        print(f"Received left image of length {length} bytes")

        # Receive right image indicator
        indicator_data = self._recv_all(4)
        indicator = struct.unpack('>I', indicator_data)[0]
        if indicator != 1:
            print("Expected right image indicator, got:", indicator)
        # Receive right image
        length_data = self._recv_all(4)
        length = struct.unpack('>I', length_data)[0]
        right_image_bytes = self._recv_all(length)
        print(f"Received right image of length {length} bytes")
            
        return left_image_bytes, right_image_bytes
        
    def disconnect(self):
        try:
            if self.sock:
                self.sock.close()
                self.connected = False
        except Exception:
            self.connected = False
            pass


#CODE FOR DEBUG        
if __name__ == "__main__":
    user_input = input("Start as server (s) or client (c)? ")
    if user_input.lower() == 'c':
        client = ImageClient(server_host='localhost', server_port=8080)
        client.connect()
        try:
            while True:
                imgL, imgR = client.receive_images()
                print("Images received from server")
        except Exception as e:
            print(f"\nDisconnecting client {e}")
            client.disconnect()
    else:
        server = ImageServerHost()
        server.start_server()
        try:
            # keep main thread alive while accept thread runs
            while True:
                if server.connected:
                    control_input = input("sendimages to client? (y/n): ")
                    if control_input.lower() == 'y':
                        #load files from popup dialog to send
                        import cv2
                        import numpy as np
                        #open file dialog to select left and right images
                        from tkinter import Tk
                        from tkinter import filedialog
                        # root = Tk()
                        # root.withdraw()  # Hide the root window
                        # left_path = filedialog.askopenfilename(title="Select left image")
                        # right_path = left_path.replace("left", "right")  # Assume right image has same name with "right" instead of "left"
                        # # Read with OpenCV (BGR)
                        left_path = "C:\\repos\\images\\faces\\received_depth\\left_image_1775605130818.png"
                        right_path = "C:\\repos\\images\\faces\\received_depth\\right_image_1775605130818.png"

                        left_img = cv2.imread(left_path, cv2.IMREAD_UNCHANGED)
                        right_img = cv2.imread(right_path, cv2.IMREAD_UNCHANGED)
                        # Ensure both are 4 channels (BGRA)
                        if left_img is not None and left_img.shape[2] == 3:
                            left_img = cv2.cvtColor(left_img, cv2.COLOR_BGR2BGRA)
                        if right_img is not None and right_img.shape[2] == 3:
                            right_img = cv2.cvtColor(right_img, cv2.COLOR_BGR2BGRA)
                        # Convert BGRA to RGBA
                        left_img = cv2.cvtColor(left_img, cv2.COLOR_BGRA2RGBA)
                        right_img = cv2.cvtColor(right_img, cv2.COLOR_BGRA2RGBA)
                        # Send as raw bytes
                        try:
                            server.send_images(left_img.tobytes(), right_img.tobytes())
                        except ConnectionError:
                            print("No client connected to send images")
                    elif control_input.lower() == 'n':
                        continue
                else:
                    # FIX: Sleep to yield CPU time when no client is connected
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nShutting down server")
            server.stop_server()