#!/usr/bin/env python3
"""Generate RTCM proof summary from existing log files."""
import csv
import os
import sys
from datetime import datetime

INJECTION_LOG = os.path.join("logs", "rtcm_injection.log")
FIX_TRANSITION_LOG = os.path.join("logs", "rtcm_fix_transition.log")
PROOF_SUMMARY = os.path.join("logs", "rtcm_proof_summary.txt")


def read_injection_stats():
    total_frames = 0
    total_bytes = 0
    fpm_values = []
    try:
        with open(INJECTION_LOG, "r") as f:
            reader = csv.reader(f)
            last_row = None
            for row in reader:
                if row and not row[0].startswith("#") and row[0] != "timestamp":
                    last_row = row
                    if len(row) >= 4:
                        try:
                            fpm_values.append(float(row[3]))
                        except (ValueError, IndexError):
                            pass
            if last_row and len(last_row) >= 3:
                try:
                    total_frames = int(last_row[1])
                    total_bytes = int(last_row[2])
                except (ValueError, IndexError):
                    pass
    except (FileNotFoundError, IOError):
        pass
    avg_fpm = sum(fpm_values) / len(fpm_values) if fpm_values else 0
    return total_frames, total_bytes, avg_fpm, len(fpm_values)


def read_fix_transitions():
    entries = 0
    fixes_seen = set()
    first_ts = None
    last_ts = None
    transitions = []
    try:
        with open(FIX_TRANSITION_LOG, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0].startswith("#") or row[0] == "timestamp":
                    continue
                entries += 1
                if len(row) >= 4:
                    try:
                        fixes_seen.add(int(row[2]))
                    except ValueError:
                        pass
                if len(row) >= 10 and row[9]:
                    transitions.append(row[9])
                if len(row) >= 1 and not first_ts:
                    first_ts = row[0]
                if len(row) >= 1:
                    last_ts = row[0]
    except (FileNotFoundError, IOError):
        pass
    return entries, fixes_seen, transitions, first_ts, last_ts


def main():
    os.makedirs("logs", exist_ok=True)

    total_frames, total_bytes, avg_fpm, fpm_samples = read_injection_stats()
    fix_entries, fixes_seen, fix_transitions, first_fix_ts, last_fix_ts = read_fix_transitions()

    now = datetime.now()

    fix_names = {0: "NoFix", 1: "GPS", 2: "DGPS", 4: "RTK_FIXED", 5: "RTK_FLOAT"}
    fix_display = ", ".join(f"{v}({fix_names.get(v, '?')})" for v in sorted(fixes_seen))

    lines = []
    lines.append("=" * 60)
    lines.append("  RTCM INJECTION PROOF SUMMARY")
    lines.append("=" * 60)
    lines.append(f"  生成日時            : {now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("  --- RTCM 注入ログ (rtcm_injection.log) ---")
    lines.append(f"  総注入フレーム数    : {total_frames}")
    lines.append(f"  総注入バイト数      : {total_bytes}")
    lines.append(f"  平均注入レート      : {avg_fpm:.1f} frames/min")
    lines.append(f"  サンプル数          : {fpm_samples}")
    if total_frames > 0:
        lines.append(f"  注入状態            : ACTIVE (frames_per_min > 0)")
    else:
        lines.append(f"  注入状態            : INACTIVE")
    lines.append("")
    lines.append("  --- F9P Fix 遷移ログ (rtcm_fix_transition.log) ---")
    lines.append(f"  記録エントリ数      : {fix_entries}")
    lines.append(f"  観測Fix状態         : {fix_display}")
    if first_fix_ts:
        lines.append(f"  初回観測時刻        : {first_fix_ts}")
    if last_fix_ts:
        lines.append(f"  最終観測時刻        : {last_fix_ts}")
    transitions_found = [t for t in fix_transitions if t]
    if transitions_found:
        lines.append(f"  遷移検出            : {'; '.join(transitions_found)}")
    else:
        lines.append(f"  遷移検出            : なし（安定状態）")
    lines.append("")
    lines.append("  --- ログファイル一覧 ---")
    lines.append(f"    - RTCM注入ログ       : {INJECTION_LOG}")
    lines.append(f"    - RTK Fix遷移ログ    : {FIX_TRANSITION_LOG}")
    lines.append(f"    - 証明サマリ (本ファイル) : {PROOF_SUMMARY}")
    lines.append("")
    lines.append(f"  STATUS: {'OK - RTCM注入アクティブ' if total_frames > 0 else 'NG'}")
    lines.append("=" * 60)

    with open(PROOF_SUMMARY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    for line in lines:
        print(line)

    print(f"\nProof summary saved to: {PROOF_SUMMARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
