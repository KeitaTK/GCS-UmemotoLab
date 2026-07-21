#!/bin/bash
# F9P UART2 Hardware Diagnostic Script — Test #5
# Run on Raspi: bash scripts/f9p_uart2_hw_diag.sh
set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
pass() { echo -e "${GREEN}[PASS]${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; WARN=$((WARN+1)); }
info() { echo -e "       $1"; }

echo "===== F9P UART2 HW Diagnostic — Test #5 ====="
echo "Date: $(date)"
echo ""

# Section 1: UART4 device check
echo "--- Section 1: UART4 (GPIO12/13) ---"
if [ -e /dev/ttyAMA4 ]; then
    pass "/dev/ttyAMA4 exists"
    ls -la /dev/ttyAMA4
else
    fail "/dev/ttyAMA4 NOT FOUND"
fi

echo ""
echo "  GPIO12/13 pinmux:"
pinctrl 12 13 2>/dev/null || warn "pinctrl not available"

GPIO12_FUNC=$(pinctrl 12 2>/dev/null | grep -oP 'a\d' || echo "?")
GPIO13_FUNC=$(pinctrl 13 2>/dev/null | grep -oP 'a\d' || echo "?")
if [ "$GPIO12_FUNC" = "a2" ] && [ "$GPIO13_FUNC" = "a2" ]; then
    pass "GPIO12=$GPIO12_FUNC(TXD4), GPIO13=$GPIO13_FUNC(RXD4)"
else
    [ "$GPIO12_FUNC" = "a2" ] && pass "GPIO12=$GPIO12_FUNC(TXD4)" || fail "GPIO12=$GPIO12_FUNC (expected a2)"
    [ "$GPIO13_FUNC" = "a2" ] && pass "GPIO13=$GPIO13_FUNC(RXD4)" || fail "GPIO13=$GPIO13_FUNC (expected a2)"
fi

echo ""
UART4_USERS=$(sudo fuser /dev/ttyAMA4 2>/dev/null || echo "none")
if [ "$UART4_USERS" = "none" ]; then
    pass "/dev/ttyAMA4: no other process"
else
    warn "/dev/ttyAMA4 used by PID: $UART4_USERS"
fi

echo ""
if grep -q "dtoverlay=uart4" /boot/firmware/config.txt 2>/dev/null; then
    pass "dtoverlay=uart4 in /boot/firmware/config.txt"
else
    fail "dtoverlay=uart4 NOT in /boot/firmware/config.txt"
fi

echo ""
info "stty /dev/ttyAMA4:"
stty -F /dev/ttyAMA4 -a 2>/dev/null | head -2 || warn "Cannot read stty"

# Section 2: F9P communication test
echo ""
echo "--- Section 2: F9P TX2→GPIO13 read test ---"
sudo fuser -k /dev/ttyAMA4 2>/dev/null || true
sleep 1
stty -F /dev/ttyAMA4 115200 cs8 -cstopb -parenb raw -echo 2>/dev/null
READ_DATA=$(timeout 3 cat /dev/ttyAMA4 2>/dev/null | xxd | head -10 || echo "")
if echo "$READ_DATA" | grep -q "b5 62"; then
    pass "F9P TX2→GPIO13: UBX data received (0xB5 0x62)"
    echo "$READ_DATA" | head -5
elif [ -n "$READ_DATA" ]; then
    warn "F9P TX2→GPIO13: data but no UBX preamble"
    echo "$READ_DATA" | head -3
else
    fail "F9P TX2→GPIO13: NO data"
fi

# Section 3: Multi-baudrate write test to F9P RX2
echo ""
echo "--- Section 3: GPIO12→F9P RX2 write test (multi-baud) ---"
UBX_POLL_HEX="b562068b080000000000010059403387"
for BAUDRATE in 9600 19200 38400 57600 115200 230400; do
    stty -F /dev/ttyAMA4 $BAUDRATE cs8 -cstopb -parenb raw -echo 2>/dev/null
    timeout 0.5 cat /dev/ttyAMA4 > /dev/null 2>&1 || true
    echo -n "$UBX_POLL_HEX" | xxd -r -p > /dev/ttyAMA4 2>/dev/null
    RESP=$(timeout 1.5 cat /dev/ttyAMA4 2>/dev/null | xxd | head -3 || echo "")
    if echo "$RESP" | grep -q "b5 62"; then
        pass "Baud $BAUDRATE: F9P responded!"
        echo "$RESP"
        break
    else
        fail "Baud $BAUDRATE: no response"
    fi
done

# Section 4: Power check
echo ""
echo "--- Section 4: Power check ---"
if dmesg | grep -qi "undervoltage\|under-voltage"; then
    UV_COUNT=$(dmesg | grep -ci "undervoltage\|under-voltage")
    warn "Undervoltage: $UV_COUNT occurrences"
    dmesg | grep -i "undervoltage\|under-voltage" | tail -3
else
    pass "No undervoltage"
fi

# Section 5: Physical inspection guide
echo ""
echo "--- Section 5: Physical Inspection Guide ---"
echo "  1. F9P RX2=Pin2, TX2=Pin3, GND=Pin6 — inspect pins"
echo "  2. Raspi GPIO12=Pin32, GPIO13=Pin33 — inspect pins"
echo "  3. Continuity: Pin32↔F9P-Pin2, Pin33↔F9P-Pin3, Pin34↔F9P-Pin6"
echo "  4. Swap with spare F9P if available"
echo ""

echo "===== SUMMARY: Pass=$PASS Fail=$FAIL Warn=$WARN ====="
[ $FAIL -eq 0 ] && echo "All checks passed" || echo "$FAIL check(s) failed — check F9P RX2 hardware"
