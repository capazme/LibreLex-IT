#!/usr/bin/env bash
# Build the .oxt and install it into a LibreOffice profile (spec §9.2).
#
# The registration is done by LibreOffice itself, headless, through scripts/lo_install.py
# (the same in-process path as Tools > Extension Manager). `unopkg add` is not used: on
# macOS it registers Python components through a helper soffice reached over a named pipe,
# and on some installs that helper never answers (NoConnectException).
#
# Usage: scripts/dev_install.sh [--profile DIR] [--remove]
#   default: your real LibreOffice profile (LibreOffice must be closed)
#   --profile DIR: a private profile, e.g. --profile "$PWD/spike/lo_profile"
#   --remove: uninstall instead of installing
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SOFFICE="${SOFFICE:-/Applications/LibreOffice.app/Contents/MacOS/soffice}"
if [ ! -x "$SOFFICE" ]; then
  SOFFICE="$(command -v soffice || true)"
fi
if [ -z "$SOFFICE" ]; then
  echo "soffice not found: set SOFFICE=/path/to/soffice" >&2
  exit 1
fi

PROFILE=""
ENV_ARGS=()   # empty for the real profile: soffice then uses its default (no URL to escape)
REMOVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --profile)
      [ -n "${2:-}" ] || { echo "--profile needs a directory" >&2; exit 1; }
      mkdir -p "$2"
      PROFILE="$(cd "$2" && pwd)"
      # file URI with spaces and other characters escaped (the real profile path has a space)
      ENV_ARGS=("-env:UserInstallation=$(python3 -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).as_uri())' "$PROFILE")")
      shift 2 ;;
    --remove) REMOVE=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [ -z "$PROFILE" ]; then
  case "$(uname -s)" in
    Darwin) PROFILE="$HOME/Library/Application Support/LibreOffice/4" ;;
    *) PROFILE="$HOME/.config/libreoffice/4" ;;
  esac
  if pgrep -x soffice >/dev/null 2>&1 || [ -e "$PROFILE/.lock" ]; then
    echo "LibreOffice is running (or its profile is locked): quit it completely (Cmd+Q) and run this script again." >&2
    exit 1
  fi
fi

if [ "$REMOVE" -eq 1 ]; then
  OXT=""
else
  OXT="$(python3 "$REPO/scripts/build_oxt.py" | tail -n 1)"
  echo "built $OXT"
fi

# The macro must live in the profile's Scripts/python directory; it is removed afterwards.
SCRIPTS="$PROFILE/user/Scripts/python"
mkdir -p "$SCRIPTS"
cp "$REPO/scripts/lo_install.py" "$SCRIPTS/librelex_install.py"
RESULT="$(mktemp)"
cleanup() { rm -f "$SCRIPTS/librelex_install.py" "$RESULT"; }
trap cleanup EXIT

export LIBRELEX_OXT="$OXT" LIBRELEX_INSTALL_RESULT="$RESULT"
# ${arr[@]+"${arr[@]}"} keeps bash 3.2 (macOS) happy under set -u when the array is empty.
"$SOFFICE" ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} --headless --norestore --nologo \
  'vnd.sun.star.script:librelex_install.py$main?language=Python&location=user' >/dev/null 2>&1 &
PID=$!
WAITED=0
while kill -0 "$PID" 2>/dev/null; do
  if [ "$WAITED" -ge 180 ]; then
    echo "soffice did not finish within 180 s, killing it" >&2
    kill "$PID" 2>/dev/null || true
    sleep 2
    kill -9 "$PID" 2>/dev/null || true
    break
  fi
  sleep 1
  WAITED=$((WAITED + 1))
done
wait "$PID" 2>/dev/null || true

if [ ! -s "$RESULT" ]; then
  echo "no result from LibreOffice (see the profile at $PROFILE)" >&2
  exit 1
fi
cat "$RESULT"
if [ "$(head -n 1 "$RESULT")" != "OK" ]; then
  echo "installation failed" >&2
  exit 1
fi

echo
if [ "$REMOVE" -eq 1 ]; then
  echo "Removed. Restart LibreOffice."
else
  echo "Installed into $PROFILE. Start LibreOffice, then in Writer: View > Sidebar > LibreLex > Copilota legale."
  echo "First use runs 'uv run' on the bundled core: it needs network access once to build its environment."
fi
