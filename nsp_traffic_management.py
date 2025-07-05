import cv2
import numpy as np
import torch
from ultralytics import YOLO
import time
import json
import logging
import socket
import threading
import ssl
import hashlib
from typing import List, Dict, Tuple
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='traffic_system.log'
)

class SecurityManager:
    def __init__(self):
        self.authorized_clients = set()
        self.session_tokens = {}
        self.failed_attempts = {}
        self.max_attempts = 3
        self.block_duration = 300  # 5 minutes
        
    def generate_token(self, client_id: str) -> str:
        """Generate a secure session token."""
        timestamp = str(time.time())
        data = f"{client_id}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def authenticate_client(self, client_id: str, password: str) -> bool:
        """Authenticate client with secure password verification."""
        if client_id in self.failed_attempts:
            if time.time() - self.failed_attempts[client_id]['timestamp'] < self.block_duration:
                if self.failed_attempts[client_id]['count'] >= self.max_attempts:
                    logging.warning(f"Client {client_id} is blocked due to multiple failed attempts")
                    return False
        
        # Simulate password verification (replace with actual authentication)
        if password == "secure_password":  # Replace with secure password verification
            self.authorized_clients.add(client_id)
            token = self.generate_token(client_id)
            self.session_tokens[client_id] = token
            logging.info(f"Client {client_id} authenticated successfully")
            return True
        else:
            if client_id not in self.failed_attempts:
                self.failed_attempts[client_id] = {'count': 1, 'timestamp': time.time()}
            else:
                self.failed_attempts[client_id]['count'] += 1
            logging.warning(f"Failed authentication attempt for client {client_id}")
            return False

class SecureTrafficSystem:
    def __init__(self, host: str = 'localhost', port: int = 5000):
        self.security_manager = SecurityManager()
        self.host = host
        self.port = port
        self.running = False
        self.clients = {}
        
        # Initialize YOLO model
        self.model = YOLO('yolov3.pt')
        
        # Vehicle classes
        self.vehicle_classes = {
            2: 'car',
            3: 'motorcycle',
            5: 'bus',
            7: 'truck',
            1: 'bicycle'
        }
        
        # Emergency vehicle classes
        self.emergency_classes = {
            'ambulance': 2,
            'fire_truck': 7,
            'police_car': 2
        }
        
        # Traffic signal states
        self.signals = {}
        self.congestion_levels = {}
        
    def start_server(self):
        """Start the secure traffic management server."""
        try:
            # Create SSL context
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain('server.crt', 'server.key')
            
            # Create server socket
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.bind((self.host, self.port))
            server_socket.listen(5)
            
            # Wrap socket with SSL
            secure_socket = context.wrap_socket(server_socket, server_side=True)
            
            self.running = True
            logging.info(f"Secure server started on {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, address = secure_socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address)
                    )
                    client_thread.start()
                except Exception as e:
                    logging.error(f"Error accepting connection: {str(e)}")
                    
        except Exception as e:
            logging.error(f"Server error: {str(e)}")
            self.running = False
    
    def handle_client(self, client_socket: socket.socket, address: Tuple[str, int]):
        """Handle client connections securely."""
        try:
            # Receive authentication data
            auth_data = client_socket.recv(1024).decode()
            client_id, password = auth_data.split(':')
            
            if self.security_manager.authenticate_client(client_id, password):
                token = self.security_manager.session_tokens[client_id]
                client_socket.send(token.encode())
                
                while self.running:
                    try:
                        # Receive encrypted traffic data
                        data = client_socket.recv(4096)
                        if not data:
                            break
                            
                        # Process traffic data
                        self.process_traffic_data(data, client_id)
                        
                        # Send response
                        response = self.generate_response(client_id)
                        client_socket.send(response.encode())
                        
                    except Exception as e:
                        logging.error(f"Error processing client data: {str(e)}")
                        break
                        
            else:
                client_socket.send(b"Authentication failed")
                
        except Exception as e:
            logging.error(f"Error handling client {address}: {str(e)}")
        finally:
            client_socket.close()
    
    def process_traffic_data(self, data: bytes, client_id: str):
        """Process incoming traffic data securely."""
        try:
            # Decrypt and parse data
            traffic_data = json.loads(data.decode())
            
            # Update traffic signals
            if 'signal_state' in traffic_data:
                self.signals[client_id] = traffic_data['signal_state']
            
            # Update congestion levels
            if 'congestion' in traffic_data:
                self.congestion_levels[client_id] = traffic_data['congestion']
            
            logging.info(f"Processed traffic data from {client_id}")
            
        except Exception as e:
            logging.error(f"Error processing traffic data: {str(e)}")
    
    def generate_response(self, client_id: str) -> str:
        """Generate secure response for client."""
        response = {
            'timestamp': datetime.now().isoformat(),
            'signal_state': self.signals.get(client_id, 'UNKNOWN'),
            'congestion_level': self.congestion_levels.get(client_id, 0.0),
            'token': self.security_manager.session_tokens.get(client_id, '')
        }
        return json.dumps(response)
    
    def detect_vehicles(self, frame: np.ndarray) -> Tuple[List[Dict], List[Dict], float]:
        """Detect vehicles in frame using YOLO."""
        try:
            results = self.model(frame)
            
            regular_vehicles = []
            emergency_vehicles = []
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    
                    if cls in self.vehicle_classes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
                        detection = {
                            'class': self.vehicle_classes[cls],
                            'confidence': conf,
                            'box': (x1, y1, x2, y2)
                        }
                        
                        if cls in self.emergency_classes.values():
                            emergency_vehicles.append(detection)
                        else:
                            regular_vehicles.append(detection)
            
            # Calculate congestion
            frame_area = frame.shape[0] * frame.shape[1]
            vehicle_area = sum((x2-x1)*(y2-y1) for _, _, (x1, y1, x2, y2) in regular_vehicles)
            congestion = min(1.0, vehicle_area / frame_area)
            
            return regular_vehicles, emergency_vehicles, congestion
            
        except Exception as e:
            logging.error(f"Error in vehicle detection: {str(e)}")
            return [], [], 0.0
    
    def stop_server(self):
        """Stop the traffic management server."""
        self.running = False
        logging.info("Server stopped")

def main():
    # Create and start the secure traffic system
    traffic_system = SecureTrafficSystem()
    
    try:
        traffic_system.start_server()
    except KeyboardInterrupt:
        logging.info("Shutting down server...")
        traffic_system.stop_server()

if __name__ == "__main__":
    main() 