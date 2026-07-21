"""compare_uart_can_fix.py のユニットテスト

Fix 正規化 / TransitionEvent マッチング / レポート生成のロジックを検証する。
CAN/UART ハードウェア不要。
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rtk_tools.compare_uart_can_fix import (  # noqa: E402
    FixRecord,
    TransitionEvent,
    ComparisonResult,
    normalize_uart_fix,
    normalize_can_fix,
    UartCanFixComparator,
    generate_report,
    NORMALIZED_NAMES,
    UART_EXPECTED_HZ,
    CAN_EXPECTED_HZ,
)


# ------------------------------------------------------------------
# Fix 正規化テスト
# ------------------------------------------------------------------

class TestNormalize:
    def test_uart_none(self):
        assert normalize_uart_fix(0) == 0

    def test_uart_float(self):
        assert normalize_uart_fix(1) == 1

    def test_uart_fixed(self):
        assert normalize_uart_fix(2) == 2

    def test_uart_unknown(self):
        assert normalize_uart_fix(99) == 0

    def test_can_single(self):
        assert normalize_can_fix(0) == 0

    def test_can_dgps(self):
        assert normalize_can_fix(1) == 0

    def test_can_rtk_float(self):
        assert normalize_can_fix(2) == 1

    def test_can_rtk_fixed(self):
        assert normalize_can_fix(3) == 2

    def test_can_unknown(self):
        assert normalize_can_fix(255) == 0



# ------------------------------------------------------------------
# TransitionEvent マッチングテスト
# ------------------------------------------------------------------

class TestTransitionMatching:

    @staticmethod
    def _rec(source: str, norm: int, ts: float) -> FixRecord:
        return FixRecord(
            source=source, timestamp_mono=ts, timestamp_iso="",
            normalized_fix=norm, raw_fix_value=norm, raw_fix_name="?",
            num_sv=10, lat=35.0, lon=139.0, h_msl=40.0)

    def test_both_transition_near_simultaneous(self):
        comp = UartCanFixComparator(poll_interval=0.5)
        comp._prev_uart_norm = 0
        comp._prev_can_norm = 0
        t0 = 100.0
        comp._process_uart_record(self._rec("UART2", 1, t0))
        assert comp._pending_uart is not None
        comp._process_can_record(self._rec("CAN", 1, t0 + 0.01))
        assert comp._pending_uart is None
        assert len(comp._transitions) == 1
        ev = comp._transitions[0]
        assert ev.normalized_fix_from == 0
        assert ev.normalized_fix_to == 1
        assert abs(ev.delay_sec) < 0.02

    def test_uart_first_can_follows(self):
        comp = UartCanFixComparator(poll_interval=0.5)
        comp._prev_uart_norm = 1
        comp._prev_can_norm = 1
        comp._process_uart_record(self._rec("UART2", 2, 200.0))
        assert comp._pending_uart is not None
        comp._process_can_record(self._rec("CAN", 2, 200.5))
        assert comp._pending_uart is None
        assert len(comp._transitions) == 1
        ev = comp._transitions[0]
        assert ev.source == "UART2"
        assert ev.delay_sec == pytest.approx(0.5, rel=0.01)

    def test_can_first_uart_follows(self):
        comp = UartCanFixComparator(poll_interval=0.5)
        comp._prev_uart_norm = 0
        comp._prev_can_norm = 0
        comp._process_can_record(self._rec("CAN", 1, 300.0))
        assert comp._pending_can is not None
        comp._process_uart_record(self._rec("UART2", 1, 300.3))
        assert comp._pending_can is None
        assert len(comp._transitions) == 1
        ev = comp._transitions[0]
        assert ev.source == "CAN"
        assert ev.delay_sec == pytest.approx(-0.3, rel=0.01)

    def test_mismatched_direction_not_matched(self):
        comp = UartCanFixComparator(poll_interval=0.5)
        comp._prev_uart_norm = 0
        comp._prev_can_norm = 1
        comp._process_uart_record(self._rec("UART2", 1, 100.0))
        comp._process_can_record(self._rec("CAN", 2, 100.1))
        assert comp._pending_uart is not None
        assert comp._pending_can is not None
        assert len(comp._transitions) == 0

    def test_no_transition_no_event(self):
        comp = UartCanFixComparator(poll_interval=0.5)
        comp._prev_uart_norm = 2
        comp._prev_can_norm = 2
        comp._process_uart_record(self._rec("UART2", 2, 100.0))
        comp._process_can_record(self._rec("CAN", 2, 100.1))


# ------------------------------------------------------------------
# Analysis テスト
# ------------------------------------------------------------------

class TestAnalyze:
    def test_basic_analysis(self):
        comp = UartCanFixComparator(poll_interval=0.5)
        for i in range(25):
            comp._uart_records.append(FixRecord(
                source="UART2", timestamp_mono=float(i)*0.2,
                timestamp_iso="", normalized_fix=2,
                raw_fix_value=2, raw_fix_name="FIXED",
                num_sv=20, lat=35.0, lon=139.0, h_msl=40.0))
        for i in range(50):
            comp._can_records.append(FixRecord(
                source="CAN", timestamp_mono=float(i)*0.1,
                timestamp_iso="", normalized_fix=2,
                raw_fix_value=3, raw_fix_name="RTK_FIXED",
                num_sv=20, lat=35.0, lon=139.0, h_msl=40.0))
        result = comp.analyze(duration_sec=5.0)
        assert result.uart_records == 25
        assert result.can_records == 50
        assert result.uart_rate_hz == pytest.approx(5.0, rel=0.1)
        assert result.can_rate_hz == pytest.approx(10.0, rel=0.1)
        assert result.uart_loss_pct == pytest.approx(0.0, abs=1.0)
        assert result.can_loss_pct == pytest.approx(0.0, abs=1.0)

    def test_zero_duration(self):
        comp = UartCanFixComparator(poll_interval=0.5)
        result = comp.analyze(duration_sec=0.0)
        assert result.uart_rate_hz == 0.0
        assert result.can_rate_hz == 0.0

    def test_high_loss(self):
        comp = UartCanFixComparator(poll_interval=0.5)
        comp._uart_records.append(FixRecord(
            source="UART2", timestamp_mono=0.0, timestamp_iso="",
            normalized_fix=0, raw_fix_value=0, raw_fix_name="NONE",
            num_sv=0, lat=0.0, lon=0.0, h_msl=0.0))
        comp._uart_records.append(FixRecord(
            source="UART2", timestamp_mono=4.0, timestamp_iso="",
            normalized_fix=0, raw_fix_value=0, raw_fix_name="NONE",
            num_sv=0, lat=0.0, lon=0.0, h_msl=0.0))
        result = comp.analyze(duration_sec=5.0)
        assert result.uart_loss_pct > 90.0



# ------------------------------------------------------------------
# Report 生成テスト
# ------------------------------------------------------------------

class TestGenerateReport:
    def test_report_no_transitions_clean(self):
        result = ComparisonResult(
            duration_sec=60.0, uart_records=300, can_records=600,
            uart_rate_hz=5.0, can_rate_hz=10.0,
            uart_loss_pct=0.0, can_loss_pct=0.0,
            transitions=[], final_uart_fix=2, final_can_fix=2)
        report = generate_report(result)
        assert "UART2(UBX-NAV-PVT) vs CAN(DroneCAN Fix2)" in report
        assert "60.0 秒" in report
        assert "300 件" in report
        assert "600 件" in report
        assert "FIXED" in report
        assert "問題なし" in report

    def test_report_with_transition(self):
        ev = TransitionEvent(
            source="UART2", normalized_fix_from=0, normalized_fix_to=1,
            time_uart2=10.0, time_can=10.15, delay_sec=0.15)
        result = ComparisonResult(
            duration_sec=30.0, uart_records=150, can_records=300,
            uart_rate_hz=5.0, can_rate_hz=10.0,
            uart_loss_pct=0.0, can_loss_pct=0.0,
            transitions=[ev], final_uart_fix=1, final_can_fix=1)
        report = generate_report(result)
        assert "Fix 遷移イベント一覧" in report
        assert "NO_RTK→FLOAT" in report
        assert "同期 (良好)" in report

    def test_report_with_issues(self):
        result = ComparisonResult(
            duration_sec=10.0, uart_records=10, can_records=20,
            uart_rate_hz=1.0, can_rate_hz=2.0,
            uart_loss_pct=80.0, can_loss_pct=80.0,
            transitions=[], final_uart_fix=2, final_can_fix=0)
        report = generate_report(result)
        assert "問題検出" in report
        assert "欠落率高" in report
        assert "最終 fix 不一致" in report

    def test_report_large_delay(self):
        ev = TransitionEvent(
            source="UART2", normalized_fix_from=1, normalized_fix_to=2,
            time_uart2=5.0, time_can=8.0, delay_sec=3.0)
        result = ComparisonResult(
            duration_sec=20.0, uart_records=100, can_records=200,
            uart_rate_hz=5.0, can_rate_hz=10.0,
            uart_loss_pct=0.0, can_loss_pct=0.0,
            transitions=[ev], final_uart_fix=2, final_can_fix=2)
        report = generate_report(result)
        assert "遅延大 (要確認)" in report
        assert "遷移遅延 >2.0s" in report


# ------------------------------------------------------------------
# 定数テスト
# ------------------------------------------------------------------

class TestConstants:
    def test_normalized_names(self):
        assert NORMALIZED_NAMES[0] == "NO_RTK"
        assert NORMALIZED_NAMES[1] == "FLOAT"
        assert NORMALIZED_NAMES[2] == "FIXED"

    def test_expected_rates(self):
        assert UART_EXPECTED_HZ == 5.0
        assert CAN_EXPECTED_HZ == 10.0
