import socket
import threading

class RtcmReader:
    def __init__(self, host='127.0.0.1', port=15000, enabled=True):
        self.host = host
        self.port = port
        self.enabled = enabled
        self.sock = None
        self.thread = None
        self.running = False
        self.callbacks = []

    def start(self):
        if not self.enabled:
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()
        if self.thread:
            self.thread.join()

    def register_callback(self, callback):
        self.callbacks.append(callback)

    def _read_loop(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            while self.running:
                data = self.sock.recv(4096)
                if not data:
                    break
                for cb in self.callbacks:
                    cb(data)
        except Exception as e:
            print(f"RTCM Reader error: {e}")
        finally:
            if self.sock:
                self.sock.close()
