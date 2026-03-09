class RtcmInjector:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def inject(self, gps_system, rtcm_data):
        if not self.enabled:
            return
        # GPS_RTCM_DATA送信処理
        gps_system.send_rtcm_data(rtcm_data)
        # ログへの記録（ファイルI/Oの負荷を減らすためバイナリログは標準loggingに乗せるか省略）
        pass
