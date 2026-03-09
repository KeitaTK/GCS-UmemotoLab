class RtcmInjector:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def inject(self, gps_system, rtcm_data):
        if not self.enabled:
            return
        # GPS_RTCM_DATA送信処理
        gps_system.send_rtcm_data(rtcm_data)
        print(f"Injected RTCM data to {gps_system.__class__.__name__}: {len(rtcm_data)} bytes")
        # ログ記録
        with open("gcs.log", "a") as log_file:
            log_file.write(f"RTCM injected to {gps_system}: {len(rtcm_data)} bytes\n")
