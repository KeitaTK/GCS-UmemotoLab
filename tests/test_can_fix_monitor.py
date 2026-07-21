"""can_fix_monitor.py のユニットテスト

DSDL パースと CAN トランスポート再構築のロジックを検証する。
CAN ハードウェア不要。
"""

import struct
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rtk_tools.can_fix_monitor import (
    parse_fix2, format_fix2, format_fix2_verbose,
    CanTransportReassembler,
    FIX2_HEADER_FMT, FIX2_HEADER_SIZE,
    FIX2_DOP_FMT, FIX2_DOP_SIZE,
    FIX2_MIN_SIZE, FIX2_COV_MAX,
    FIX2_SUBJECT_ID, SUBJECT_ID_SHIFT, SUBJECT_ID_MASK,
)


def _build_fix2_payload(
    ts_us=1000000, gnss_ts_us=2000000, num_leap=0,
    lon_deg=139.0, lat_deg=35.0, h_ellip_m=50.0, h_msl_m=40.0,
    vel_n=0.0, vel_e=0.0, vel_d=0.0,
    sats=28, status=3, mode=3, sub_mode=0,
    covariance=(), pdop=1.2, hdop=0.7, vdop=1.0, tdop=0.8, ndop=0.6, edop=0.5,
) -> bytes:
    """Fix2 DSDL ペイロードを構築して返す"""
    header = struct.pack(
        FIX2_HEADER_FMT,
        ts_us, gnss_ts_us, num_leap,
        int(lon_deg * 1e8), int(lat_deg * 1e8),
        int(h_ellip_m * 1000), int(h_msl_m * 1000),
        vel_n, vel_e, vel_d, sats, status, mode, sub_mode,
    )
    cov = bytes([len(covariance)]) + struct.pack(f"<{len(covariance)}e", *covariance)
    dops = struct.pack(FIX2_DOP_FMT, pdop, hdop, vdop, tdop, ndop, edop)
    return header + cov + dops


class _MockCanFrame:
    """python-can Message の簡易モック"""
    def __init__(self, arbitration_id: int, data: bytes):
        self.arbitration_id = arbitration_id
        self.data = data


def _make_can_id(source_node: int, subject_id: int) -> int:
    prio = 4
    return (prio << 25) | (subject_id << SUBJECT_ID_SHIFT) | source_node


# ------------------------------------------------------------------
# DSDL パース テスト
# ------------------------------------------------------------------

class TestParseFix2:

    def test_minimal_payload(self):
        payload = _build_fix2_payload()
        assert len(payload) == FIX2_MIN_SIZE  # 70
        r = parse_fix2(payload)
        assert r is not None
        assert r["mode"] == 3
        assert r["mode_name"] == "RTK_FIXED"
        assert r["status_name"] == "3D_FIX"
        assert r["sats_used"] == 28
        assert r["lat"] == 35.0
        assert r["lon"] == 139.0
        assert r["height_msl_m"] == 40.0
        # float16 精度を考慮し approx で比較
        assert r["hdop"] == pytest.approx(0.7, rel=1e-3)
        assert r["pdop"] == pytest.approx(1.2, rel=1e-3)

    def test_with_covariance(self):
        cov = tuple(range(1, 7))
        payload = _build_fix2_payload(covariance=cov)
        r = parse_fix2(payload)
        assert r is not None
        assert r["pdop"] == pytest.approx(1.2, rel=1e-3)
        assert r["hdop"] == pytest.approx(0.7, rel=1e-3)

    def test_full_covariance(self):
        cov = tuple(float(i) for i in range(36))
        payload = _build_fix2_payload(covariance=cov)
        r = parse_fix2(payload)
        assert r is not None
        assert r["hdop"] == pytest.approx(0.7, rel=1e-3)

    def test_mode_mapping(self):
        for v, name in [(0, "SINGLE"), (1, "DGPS"), (2, "RTK_FLOAT"), (3, "RTK_FIXED"), (4, "PPP")]:
            r = parse_fix2(_build_fix2_payload(mode=v))
            assert r["mode_name"] == name

    def test_status_mapping(self):
        for v, name in [(0, "NO_FIX"), (1, "TIME_ONLY"), (2, "2D_FIX"), (3, "3D_FIX"), (4, "DGPS")]:
            r = parse_fix2(_build_fix2_payload(status=v))
            assert r["status_name"] == name

    def test_velocity(self):
        r = parse_fix2(_build_fix2_payload(vel_n=1.5, vel_e=-0.5, vel_d=0.1))
        vn, ve, vd = r["ned_velocity_ms"]
        # float32 精度を考慮し approx で比較
        assert vn == 1.5 and ve == -0.5 and vd == pytest.approx(0.1)

    def test_unknown_mode(self):
        r = parse_fix2(_build_fix2_payload(mode=99))
        assert "UNK(99)" in r["mode_name"]

    def test_truncated_payload(self):
        assert parse_fix2(b"\x00" * 10) is None

    def test_corrupt_payload(self):
        payload = _build_fix2_payload()
        truncated = payload[:FIX2_HEADER_SIZE + 1]
        assert parse_fix2(truncated) is None


# ------------------------------------------------------------------
# 表示フォーマット テスト
# ------------------------------------------------------------------

class TestFormat:

    def test_format_summary(self):
        r = parse_fix2(_build_fix2_payload())
        line = format_fix2(r, elapsed=1.5)
        assert "RTK_FIXED" in line
        assert "3D_FIX" in line
        assert "28" in line
        assert "1.5s" in line

    def test_format_verbose(self):
        r = parse_fix2(_build_fix2_payload())
        text = format_fix2_verbose(r)
        assert "RTK_FIXED" in text
        assert "sats_used=28" in text
        assert "lat=35.0" in text


# ------------------------------------------------------------------
# CAN トランスポート再構築 テスト
# ------------------------------------------------------------------

class TestCanTransportReassembler:

    def test_single_frame(self):
        reasm = CanTransportReassembler()
        can_id = _make_can_id(10, FIX2_SUBJECT_ID)
        frame = _MockCanFrame(can_id, b"ABCDEFG" + bytes([0x00]))
        completed = reasm.feed(frame)
        assert len(completed) == 1
        assert completed[0] == b"ABCDEFG"

    def test_multi_frame_last_dlc_short(self):
        reasm = CanTransportReassembler()
        can_id = _make_can_id(10, FIX2_SUBJECT_ID)
        tid = 3
        tail_start = 0x80 | (0 << 6) | (0 << 5) | tid  # 0x83
        reasm.feed(_MockCanFrame(can_id, b"1234567" + bytes([tail_start])))

        tail_last = 0x80 | (1 << 6) | (1 << 5) | tid  # 0xA3
        completed = reasm.feed(_MockCanFrame(can_id, b"890" + bytes([tail_last])))
        assert len(completed) == 1
        assert completed[0] == b"1234567890"

    def test_orphan_frame(self):
        reasm = CanTransportReassembler()
        can_id = _make_can_id(10, FIX2_SUBJECT_ID)
        tail = 0x80 | (1 << 6) | (0 << 5) | 7  # continuation without start
        completed = reasm.feed(_MockCanFrame(can_id, b"XXXX" + bytes([tail])))
        assert len(completed) == 0

    def test_different_source_nodes(self):
        reasm = CanTransportReassembler()
        tid = 1
        tail_start = 0x80 | (0 << 6) | (0 << 5) | tid
        reasm.feed(_MockCanFrame(_make_can_id(10, FIX2_SUBJECT_ID), b"AAAAAAA" + bytes([tail_start])))
        reasm.feed(_MockCanFrame(_make_can_id(11, FIX2_SUBJECT_ID), b"BBBBBBB" + bytes([tail_start])))
        tail_last = 0x80 | (1 << 6) | (1 << 5) | tid
        completed = reasm.feed(_MockCanFrame(_make_can_id(10, FIX2_SUBJECT_ID), b"CCCC" + bytes([tail_last])))
        assert len(completed) == 1
        assert completed[0] == b"AAAAAAACCCC"

    def test_reset(self):
        reasm = CanTransportReassembler()
        can_id = _make_can_id(10, FIX2_SUBJECT_ID)
        tail_start = 0x80 | (0 << 6) | (0 << 5) | 9
        reasm.feed(_MockCanFrame(can_id, b"DATA123" + bytes([tail_start])))
        assert len(reasm._buffers) == 1
        reasm.reset()
        assert len(reasm._buffers) == 0


# ------------------------------------------------------------------
# CAN ID 定数テスト
# ------------------------------------------------------------------

class TestCanIdFilter:

    def test_filter_id_value(self):
        expected = (FIX2_SUBJECT_ID << SUBJECT_ID_SHIFT) & 0x1FFFFFFF
        assert expected == 0x042700

    def test_subject_id_extraction(self):
        can_id = (4 << 25) | (FIX2_SUBJECT_ID << SUBJECT_ID_SHIFT) | 10
        extracted = (can_id >> SUBJECT_ID_SHIFT) & SUBJECT_ID_MASK
        assert extracted == FIX2_SUBJECT_ID

    def test_source_node_extraction(self):
        can_id = (4 << 25) | (FIX2_SUBJECT_ID << SUBJECT_ID_SHIFT) | 42
        src = can_id & 0x7F
        assert src == 42
