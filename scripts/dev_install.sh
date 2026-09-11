#!/usr/bin/env bash
# Build the .oxt and install it with unopkg (spec §9.2).
#
# Run this from a Terminal, not from the automation harness: unopkg's helper process is
# killed there. Default target is your real LibreOffice profile; pass --profile DIR to use
# a private one (e.g. --profile "$PWD/spike/lo_profile"). Restart LibreOffice afterwards.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNOPKG="${UNOPKG:-/Applications/LibreOffice.app/Contents/MacOS/unopkg}"
if [ ! -x "$UNOPKG" ]; then
  UNOPKG="$(command -v unopkg || true)"
fi
if [ -z "$UNOPKG" ]; then
  echo "unopkg not found: set UNOPKG=/path/to/unopkg" >&2
  exit 1
fi

PROFILE_ARGS=()
if [ "${1:-}" = "--profile" ]; then
  [ -n "${2:-}" ] || { echo "--profile needs a directory" >&2; exit 1; }
  mkdir -p "$2"
  PROFILE_ARGS=("-env:UserInstallation=file://$(cd "$2" && pwd)")
fi

OXT="$(python3 "$REPO/scripts/build_oxt.py" | tail -n 1)"
echo "built $OXT"

# ${arr[@]+"${arr[@]}"} keeps bash 3.2 (macOS) happy under set -u when the array is empty.
"$UNOPKG" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} remove org.librelex.extension >/dev/null 2>&1 || true
"$UNOPKG" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} add --force "$OXT"
"$UNOPKG" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} list | grep -A 4 "org.librelex.extension" || true

echo
echo "Installed. Quit LibreOffice completely and start it again, then in Writer:"
echo "  View > Sidebar > LibreLex (deck) > Copilota legale."
echo "First use runs 'uv run' on the bundled core: it needs network access once to build its environment."
