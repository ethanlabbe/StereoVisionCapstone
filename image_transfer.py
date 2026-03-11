import socket
import threading
import struct
import time
import sys
import datetime
import queue

class ImageServerHost:
    """Non-blocking image server that accepts a single client and sends images
    on demand via `send_images(left_bytes, right_bytes=None)`.
    Images are sent as a 4-byte big-endian length prefix followed by payload.
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

    def start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        self._running = True
        print(f"Image server started on {self.host}:{self.port}")
        self._accept_thread = threading.Thread(target=self._accept_loop)
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
                sock.sendall(struct.pack('>I', 0))  # left image indicator
                sock.sendall(struct.pack('>I', len(left_image_bytes)))
                sock.sendall(left_image_bytes)
                sock.sendall(struct.pack('>I', 1))  # right image indicator
                sock.sendall(struct.pack('>I', len(right_image_bytes)))
                sock.sendall(right_image_bytes)
                print("Image(s) sent to client (from queue)")
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
            # start monitor to detect disconnects
            t = threading.Thread(target=self._client_monitor, args=(client_sock,))
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
        print("Images queued for transfer")

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
    It will save each image it receives as received_image_<n>.jpg.
    """
    def __init__(self, server_host='localhost', server_port=8080, save_images = True):
        self.sock = None
        self.server_host = server_host
        self.server_port = server_port
        self.save_images = save_images
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
        
if __name__ == "__main__":
    user_input = input("Start as server (s) or client (c)? ")
    if user_input.lower() == 'c':
        client = ImageClient(server_host='localhost', server_port=8080, save_images=True)
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
                        left_image = None
                        right_image = None
                        with open("C:\\Users\\Ethan\\OneDrive\\Desktop\\Labs\\5th year\\Capstone\\left_20260228_214325.jpg", 'rb') as fL:
                            left_image = fL.read()
                        with open("C:\\Users\\Ethan\\OneDrive\\Desktop\\Labs\\5th year\\Capstone\\right_20260228_214325.jpg", 'rb') as fR:
                            right_image = fR.read()
                        try:
                            for i in range(5):
                                print(f"Queueing image set {i+1} for transfer...")
                                server.send_images(left_image, right_image)
                        except ConnectionError:
                            print("No client connected to send images")
                    elif control_input.lower() == 'n':
                        continue
        except KeyboardInterrupt:
            print("\nShutting down server")
            server.stop_server()
