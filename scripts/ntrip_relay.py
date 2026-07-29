import socket, base64, threading, time
from datetime import datetime

HOST, PORT = "ntrip.ales-corp.co.jp", 2101
MOUNT = "32M7NHS"
USER, PASS = "6y8swddj", "xxu2w5"
FWD = ("100.69.75.96", 2102)
GGA_LAT, GGA_LON, GGA_ALT = 36.075716, 136.213434, 51.0

def make_gga():
    t = datetime.utcnow().strftime("%H%M%S.00")
    la = abs(GGA_LAT); lat_d, lat_m = int(la), (la-int(la))*60
    lo = abs(GGA_LON); lon_d, lon_m = int(lo), (lo-int(lo))*60
    ns = "N" if GGA_LAT >= 0 else "S"
    ew = "E" if GGA_LON >= 0 else "W"
    body = f"GPGGA,{t},{lat_d:02d}{lat_m:07.4f},{ns},{lon_d:03d}{lon_m:07.4f},{ew},1,12,1.0,{GGA_ALT:.1f},M,0.0,M,,"
    ck = 0
    for c in body: ck ^= ord(c)
    return f"${body}*{ck:02X}\r\n".encode()

fwd = socket.socket()
fwd.connect(FWD)
print(f"FWD: connected to {FWD}")

s = socket.socket()
s.settimeout(15)
s.connect((HOST, PORT))
token = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
req = f"GET /{MOUNT} HTTP/1.0\r\nUser-Agent: NTRIP\r\nAuthorization: Basic {token}\r\n\r\n"
s.sendall(req.encode())

resp = b""
while b"\r\n\r\n" not in resp:
    resp += s.recv(1)
for line in resp.split(b"\r\n"):
    if line.startswith(b"ICY") or line.startswith(b"HTTP"):
        print(f"NTRIP: {line.decode()}")
        break

run = True
def gga_loop():
    while run:
        try: s.sendall(make_gga())
        except: break
        time.sleep(10)
threading.Thread(target=gga_loop, daemon=True).start()

total = 0
s.settimeout(30)
try:
    while True:
        data = s.recv(4096)
        if not data: break
        fwd.sendall(data)
        total += len(data)
        if total % 50000 < 4096:
            print(f"RTCM: {total:,} bytes")
except KeyboardInterrupt:
    pass
except Exception as e:
    print(f"Done: {e}")
finally:
    run = False; s.close(); fwd.close()
    print(f"Total: {total:,} bytes")
