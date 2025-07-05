import socket
import ssl
import json
import cv2
import numpy as np
import time
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='traffic_client.log'
)

class SecureTrafficClient:
    def __init__(self, host: str = 'localhost', port: int = 5000):
        self.host = host
        self.port = port
        self.client_id = f"client_{int(time.time())}"
        self.session_token = None
        self.connected = False
        
    def connect(self, password: str) -> bool:
        """Establish secure connection with the server."""
        try:
            # Create SSL context
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            # Create socket and wrap with SSL
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.secure_socket = context.wrap_socket(sock, server_hostname=self.host)
            self.secure_socket.connect((self.host, self.port))
            
            # Send authentication data
            auth_data = f"{self.client_id}:{password}"
            self.secure_socket.send(auth_data.encode())
            
            # Receive authentication response
            response = self.secure_socket.recv(1024).decode()
            
            if response != "Authentication failed":
                self.session_token = response
                self.connected = True
                logging.info(f"Successfully connected to server as {self.client_id}")
                return True
            else:
                logging.error("Authentication failed")
                return False
                
        except Exception as e:
            logging.error(f"Connection error: {str(e)}")
            return False
    
    def send_traffic_data(self, frame: np.ndarray) -> Dict[str, Any]:
        """Send traffic data to server and receive response."""
        if not self.connected:
            logging.error("Not connected to server")
            return {}
            
        try:
            # Process frame and prepare data
            traffic_data = {
                'timestamp': time.time(),
                'client_id': self.client_id,
                'token': self.session_token,
                'frame_data': self._process_frame(frame)
            }
            
            # Send data
            self.secure_socket.send(json.dumps(traffic_data).encode())
            
            # Receive response
            response = self.secure_socket.recv(4096).decode()
            return json.loads(response)
            
        except Exception as e:
            logging.error(f"Error sending traffic data: {str(e)}")
            return {}
    
    def _process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """Process video frame and extract relevant information."""
        try:
            # Convert frame to grayscale for basic processing
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate basic metrics
            brightness = np.mean(gray)
            contrast = np.std(gray)
            
            # Detect motion (simple implementation)
            if hasattr(self, 'prev_frame'):
                motion = np.mean(np.abs(gray - self.prev_frame))
            else:
                motion = 0
            self.prev_frame = gray.copy()
            
            return {
                'brightness': float(brightness),
                'contrast': float(contrast),
                'motion': float(motion),
                'timestamp': time.time()
            }
            
        except Exception as e:
            logging.error(f"Error processing frame: {str(e)}")
            return {}
    
    def disconnect(self):
        """Disconnect from the server."""
        if self.connected:
            try:
                self.secure_socket.close()
                self.connected = False
                logging.info("Disconnected from server")
            except Exception as e:
                logging.error(f"Error disconnecting: {str(e)}")

def main():
    # Create client
    client = SecureTrafficClient()
    
    # Connect to server
    if client.connect("secure_password"):
        try:
            # Open video capture
            cap = cv2.VideoCapture(0)
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Send traffic data
                response = client.send_traffic_data(frame)
                
                # Display response
                if response:
                    print(f"Signal State: {response.get('signal_state', 'UNKNOWN')}")
                    print(f"Congestion Level: {response.get('congestion_level', 0.0):.2f}")
                
                # Break on 'q' press
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        except KeyboardInterrupt:
            print("\nStopping client...")
        finally:
            cap.release()
            client.disconnect()
    else:
        print("Failed to connect to server")

if __name__ == "__main__":
    main() 