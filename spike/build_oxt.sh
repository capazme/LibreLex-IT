#!/usr/bin/env bash
# Build spike/librelex-spike.oxt and (re)install it into a private, throwaway
# LibreOffice profile at spike/lo_profile — NEVER the user's real profile
# (~/Library/Application Support/LibreOffice).
#
# After installing, this script also proves headlessly (no GUI) that the
# Python UNO component is registered and importable, by running a check
# macro that calls createInstanceWithContext("org.librelex.spike.PanelFactory", ...)
# and records the outcome (or the exact exception) to
# spike/evidence/s4_registration.txt.
set -euo pipefail

SPIKE_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SPIKE_DIR/oxt"
rm -f ../librelex-spike.oxt
zip -r -q ../librelex-spike.oxt . -x '*.DS_Store'
cd "$SPIKE_DIR"

UNOPKG="${UNOPKG:-/Applications/LibreOffice.app/Contents/MacOS/unopkg}"
SOFFICE="${SOFFICE:-/Applications/LibreOffice.app/Contents/MacOS/soffice}"

PROFILE_DIR="$SPIKE_DIR/lo_profile"
PROFILE_URL="file://$PROFILE_DIR"
mkdir -p "$PROFILE_DIR"

# unopkg refuses to add/remove while a soffice instance holds a lock on the
# same profile. With a private profile this should not happen, but a
# leftover headless process from an earlier run of this script could still
# hold the lock. Kill only soffice processes bound to spike/lo_profile,
# never any other LibreOffice instance.
kill_leftover_soffice() {
  local pids
  pids="$(ps ax -o pid=,command= | grep -F "$PROFILE_DIR" | grep -F soffice | grep -v grep | awk '{print $1}' || true)"
  if [ -n "$pids" ]; then
    echo "Killing leftover soffice process(es) locked to $PROFILE_DIR: $pids" >&2
    kill $pids 2>/dev/null || true
    sleep 2
  fi
}

kill_leftover_soffice

"$UNOPKG" "-env:UserInstallation=$PROFILE_URL" remove org.librelex.spike >/dev/null 2>&1 || true

if ! "$UNOPKG" "-env:UserInstallation=$PROFILE_URL" add --force librelex-spike.oxt; then
  echo "unopkg add failed; checking for a locked leftover soffice process and retrying once..." >&2
  kill_leftover_soffice
  # Retry once. If this also fails, do not abort the script: unopkg still
  # copies the package into the profile even when the "enable" step fails,
  # so `unopkg list` and the headless registration check below remain
  # meaningful (and are what this script exists to report honestly).
  "$UNOPKG" "-env:UserInstallation=$PROFILE_URL" add --force librelex-spike.oxt || \
    echo "unopkg add still failed after retry; continuing to report actual state via 'list' and the headless check." >&2
fi

echo "--- unopkg list (spike profile) ---"
"$UNOPKG" "-env:UserInstallation=$PROFILE_URL" list

# --- Headless registration check ------------------------------------------
mkdir -p "$PROFILE_DIR/user/Scripts/python"
EVIDENCE_DIR="$SPIKE_DIR/evidence"
mkdir -p "$EVIDENCE_DIR"
EVIDENCE_FILE="$EVIDENCE_DIR/s4_registration.txt"
rm -f "$EVIDENCE_FILE"

CHECK_MACRO="$PROFILE_DIR/user/Scripts/python/s4_check.py"
cat > "$CHECK_MACRO" <<'PYEOF'
# -*- coding: utf-8 -*-
"""Headless check (no GUI): is org.librelex.spike.PanelFactory registered
and importable? Writes the outcome (or the exact exception) to
LIBRELEX_EVIDENCE_DIR/s4_registration.txt, then terminates the desktop so
soffice exits."""
import os
import traceback

import uno


def main(*args):
    ctx = uno.getComponentContext()
    smgr = ctx.ServiceManager
    lines = []
    try:
        obj = smgr.createInstanceWithContext("org.librelex.spike.PanelFactory", ctx)
        lines.append("createInstanceWithContext: not None = %r" % (obj is not None,))
        lines.append("type(obj).__name__ = %s" % type(obj).__name__)
    except Exception:
        lines.append("createInstanceWithContext raised an exception:")
        lines.append(traceback.format_exc())

    evidence_dir = os.environ["LIBRELEX_EVIDENCE_DIR"]
    os.makedirs(evidence_dir, exist_ok=True)
    with open(os.path.join(evidence_dir, "s4_registration.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    desktop.terminate()


g_exportedScripts = (main,)
PYEOF

export LIBRELEX_EVIDENCE_DIR="$EVIDENCE_DIR"

MACRO_URL="vnd.sun.star.script:s4_check.py\$main?language=Python&location=user"

"$SOFFICE" \
  "-env:UserInstallation=$PROFILE_URL" \
  --headless --norestore --nologo \
  "$MACRO_URL" &
SOFFICE_PID=$!

# macOS has no `timeout` command, hence this poll loop (same pattern as
# spike/run.sh, copied rather than imported).
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
fi

wait "$SOFFICE_PID" 2>/dev/null || true

echo "--- $EVIDENCE_FILE ---"
if [ ! -f "$EVIDENCE_FILE" ]; then
  echo "ERROR: evidence file was not created" >&2
  exit 1
fi
cat "$EVIDENCE_FILE"

echo
echo "Installed into the private spike profile. To do the manual GUI test, open LibreOffice with:"
echo "  $SOFFICE -env:UserInstallation=$PROFILE_URL"
echo "Then in Writer: View > Sidebar > \"LibreLex spike\" > \"Start stream\", and type in the document during the stream."
