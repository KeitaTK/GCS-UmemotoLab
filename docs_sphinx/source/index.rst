.. GCS-UmemotoLab documentation master file, created by
   sphinx-quickstart on Sat Mar 14 02:11:06 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

GCS-UmemotoLab documentation
============================

ArduPilot用カスタムGCS（地上管制局）の完全なAPIドキュメントです。

概要
----

- **通信方式**: MAVLink v2 over UDP/Wi-Fi
- **ハードウェア**: Windows PC + Raspberry Pi 5（通信ブリッジ）
- **言語**: Python 3.10+
- **UI**: PySide6（Qt）
- **特徴**: カスタムMAVLinkメッセージ、RTKインジェクション、マルチドローン対応


.. toctree::
   :maxdepth: 2
   :caption: API Reference:

   modules
