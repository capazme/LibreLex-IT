# Phase 0 spike (throwaway)

Scripts that answer spec §12 by probing LibreOffice 26.8 at
`/Applications/LibreOffice.app`. Nothing here ships.

## Run method

LibreOffice's bundled `Resources/python` binary (used to connect over a UNO
socket) is SIGKILLed (exit 137) in this environment, so probes do **not**
run that way. Instead, each probe runs *inside* soffice's own embedded
Python, as a UNO script macro, in a private per-run profile:

    ./spike/run.sh spike/s0_smoke.py

`run.sh`:

1. Creates a fresh temp profile (`mktemp -d`) and a
   `<profile>/user/Scripts/python/` directory inside it.
2. Builds the macro file by concatenating `lo.py` with the probe (the
   probe's `from lo import ...` line is stripped, since after concatenation
   `lo.py`'s names are already in scope).
3. Sets `LIBRELEX_EVIDENCE_DIR` to `spike/evidence/` (created if missing).
4. Launches soffice headless in the background against the macro, e.g.:

       soffice -env:UserInstallation=file://<profile> --headless --norestore \
         --nologo "vnd.sun.star.script:<probe>.py$main?language=Python&location=user"

5. Polls every second, up to a 120 s watchdog, then kills soffice if it
   hasn't exited on its own (macOS has no `timeout` command).
6. Prints the evidence file path and its content. Exits non-zero if the
   evidence file was never created.

Headless macros have no usable stdout, so a probe writes its evidence to a
file instead of printing it (see `LIBRELEX_EVIDENCE_DIR` / `evidence_path`
in `lo.py`).

## Probe contract

A probe file (e.g. `spike/s1_markdown_insert.py`):

```python
from lo import ...  # for readability/editors; stripped by run.sh at run time


def probe(ctx, log):
    ...  # do the work, call log(...) to record evidence


def main(*args):
    run_probe(probe, "<probe name>")


g_exportedScripts = (main,)
```

`run_probe` (in `lo.py`) obtains the component context, opens the evidence
file, passes a `log(*parts)` function to `probe`, catches any exception and
writes the full traceback to the evidence file, and always terminates the
desktop afterwards so soffice exits.

## Evidence

Each run writes `spike/evidence/<probe name>.txt`. These files are checked
in as evidence of what each probe found on this LibreOffice install.

## Known environment limitation: out-of-process UNO bridges are killed

The same restriction that forces the run-as-macro convention above also
breaks `unopkg add`'s internal "enable" step for a `.oxt` bundling a Python
UNO component: `unopkg` copies the package into the profile fine, but
enabling/registering the Python component requires `unopkg` to spawn a
child `soffice` and validate the component over an out-of-process UNO pipe
bridge. In this environment that bridge is refused
(`com.sun.star.connection.NoConnectException`), and directly reproducing
the same bridge with LibreOffice's bundled
`Contents/Resources/python -c "import uno; ...resolve(...)"` against a
`soffice --accept="pipe,...;urp;"` confirms it: the python process is
SIGKILLed (exit 137), the exact same signature already seen for connecting
over a socket. `spike/build_oxt.sh` (Task 5) still runs the literal
`unopkg add`/`list` commands and prints their real output for the record,
but the extension ends up copied and *not* registered
(`is registered: no`); the headless registration check
(`spike/evidence/s4_registration.txt`) reflects that honestly. This is an
environment restriction, not a packaging bug — see task-5-report.md for the
full diagnostic chain. M1 will need a real (non-sandboxed) machine to
`unopkg add`/test extensions.
