#!/usr/bin/env bash
# Run a spike probe as a macro inside soffice's own embedded Python.
#
# LibreOffice's bundled `Resources/python` binary is SIGKILLed in this
# environment, so probes run *inside* soffice as a UNO script macro instead
# of connecting over a socket. A fresh private profile is created for each
# run; the probe (concatenated with lo.py) is dropped into that profile's
# user/Scripts/python/ directory and invoked via a vnd.sun.star.script URL.
#
# Headless macros have no usable stdout, so the probe writes its evidence to
# a file under spike/evidence/ instead of printing it.
set -euo pipefail

SOFFICE="${SOFFICE:-/Applications/LibreOffice.app/Contents/MacOS/soffice}"

if [ $# -lt 1 ]; then
  echo "Usage: $0 PROBE.py" >&2
  exit 1
fi

SPIKE_DIR="$(cd "$(dirname "$0")" && pwd)"
PROBE_BASENAME="$(basename "$1")"
PROBE_FILE="$SPIKE_DIR/$PROBE_BASENAME"
PROBE_NAME="${PROBE_BASENAME%.py}"

if [ ! -f "$PROBE_FILE" ]; then
  echo "Probe not found: $PROBE_FILE" >&2
  exit 1
fi

PROFILE="$(mktemp -d)"
mkdir -p "$PROFILE/user/Scripts/python"

# The probe imports helpers "from lo import ..." for readability/editors,
# but at run time it is concatenated with lo.py into a single macro file, so
# that import line is stripped (lo.py's names are already in scope).
MACRO_FILE="$PROFILE/user/Scripts/python/$PROBE_BASENAME"
{
  cat "$SPIKE_DIR/lo.py"
  echo
  grep -v '^from lo import' "$PROBE_FILE"
} > "$MACRO_FILE"

export LIBRELEX_EVIDENCE_DIR="$SPIKE_DIR/evidence"
mkdir -p "$LIBRELEX_EVIDENCE_DIR"

EVIDENCE_FILE="$LIBRELEX_EVIDENCE_DIR/$PROBE_NAME.txt"
rm -f "$EVIDENCE_FILE"

MACRO_URL="vnd.sun.star.script:${PROBE_BASENAME}\$main?language=Python&location=user"

"$SOFFICE" \
  "-env:UserInstallation=file://$PROFILE" \
  --headless --norestore --nologo \
  "$MACRO_URL" &
SOFFICE_PID=$!

# macOS has no `timeout` command, hence this poll loop.
TIMED_OUT=0
SECONDS_WAITED=0
while kill -0 "$SOFFICE_PID" 2>/dev/null; do
  if [ "$SECONDS_WAITED" -ge 120 ]; then
    TIMED_OUT=1
    break
  fi
  sleep 1
  SECONDS_WAITED=$((SECONDS_WAITED + 1))
done

if [ "$TIMED_OUT" -eq 1 ]; then
  echo "TIMEOUT: soffice did not exit within 120s, killing pid $SOFFICE_PID" >&2
  kill "$SOFFICE_PID" 2>/dev/null || true
  KILL_WAITED=0
  while kill -0 "$SOFFICE_PID" 2>/dev/null; do
    if [ "$KILL_WAITED" -ge 5 ]; then
      echo "soffice pid $SOFFICE_PID still alive after SIGTERM, sending SIGKILL" >&2
      kill -9 "$SOFFICE_PID" 2>/dev/null || true
      break
    fi
    sleep 1
    KILL_WAITED=$((KILL_WAITED + 1))
  done
fi

wait "$SOFFICE_PID" 2>/dev/null || true

echo "Evidence: $EVIDENCE_FILE"
if [ ! -f "$EVIDENCE_FILE" ]; then
  echo "ERROR: evidence file was not created" >&2
  exit 1
fi
cat "$EVIDENCE_FILE"
