#!/bin/bash
# 仮想環境のPythonを使って自作のPythonテストプログラムを実行します。
# ※Raspberry Pi上で MAVProxy が "udp:192.168.11.6:14551" に向けて転送している必要があります。

cd "$(dirname "$0")/../.."
./venv/bin/python tests/test_raspi_connection/test_mavlink_receive_14551.py
