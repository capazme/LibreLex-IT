#!/usr/bin/env bash
# Throwaway probe (spec §12, spec §2 row 7): does Writer's native Markdown
# *import* filter map Markdown constructs to named paragraph/character
# styles when converting headlessly (no GUI, no UNO macro)?
#
# Converts a small Markdown probe file to .odt with `soffice --convert-to`
# against a fresh private profile, then inspects content.xml of the
# resulting .odt (a zip) with the system python3's stdlib zipfile+re to
# list the paragraph/heading/list/span styles actually used, and the
# automatic styles' parent-style-name and bold/italic properties.
#
# Nothing here ships; see spike/README.md for conventions.
set -euo pipefail

SPIKE_DIR="$(cd "$(dirname "$0")" && pwd)"
SOFFICE="${SOFFICE:-/Applications/LibreOffice.app/Contents/MacOS/soffice}"

EVIDENCE_DIR="$SPIKE_DIR/evidence"
mkdir -p "$EVIDENCE_DIR"
EVIDENCE_FILE="$EVIDENCE_DIR/s5_markdown_styles.txt"
rm -f "$EVIDENCE_FILE"

WORK_DIR="$(mktemp -d)"
PROFILE_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR" "$PROFILE_DIR"' EXIT

MD_FILE="$WORK_DIR/md_probe.md"
cat > "$MD_FILE" <<'MDEOF'
# Titolo primo livello

## Titolo secondo livello

Paragrafo con **grassetto**, *corsivo* e testo normale. Art. 2043 c.c.

> Citazione: "Qualunque fatto doloso o colposo, che cagiona ad altri un danno ingiusto, obbliga colui che ha commesso il fatto a risarcire il danno."

- primo punto
- secondo punto

1. primo numerato
2. secondo numerato

Ultimo paragrafo.
MDEOF

"$SOFFICE" \
  "-env:UserInstallation=file://$PROFILE_DIR" \
  --headless --norestore --nologo \
  --convert-to odt --outdir "$WORK_DIR" "$MD_FILE"

ODT_FILE="$WORK_DIR/md_probe.odt"

if [ ! -f "$ODT_FILE" ]; then
  echo "ERROR: $ODT_FILE was not produced" >&2
  exit 1
fi

python3 - "$ODT_FILE" "$EVIDENCE_FILE" <<'PYEOF'
import re
import sys
import zipfile

odt_path, evidence_path = sys.argv[1], sys.argv[2]

with zipfile.ZipFile(odt_path) as z:
    content_xml = z.read("content.xml").decode("utf-8")

lines = []

para_styles = re.findall(r'<text:p[^>]*\stext:style-name="([^"]+)"', content_xml)
heading_styles = re.findall(r'<text:h[^>]*\stext:style-name="([^"]+)"', content_xml)
lines.append("paragraph/heading styles used: %s" % sorted(set(para_styles) | set(heading_styles)))

list_styles = re.findall(r'<text:list\s[^>]*?text:style-name="([^"]+)"', content_xml)
lines.append("list styles: %s" % sorted(set(list_styles)))

span_styles = re.findall(r'<text:span[^>]*\stext:style-name="([^"]+)"', content_xml)
lines.append("span styles: %s" % sorted(set(span_styles)))

# <style:style ...> elements are either self-closing ("... />") or carry a
# body up to "</style:style>". A single combined regex with a non-greedy
# body group wrongly merges a self-closing element's "attrs" with the body
# of the *next* style:style element, so self-closing and body-bearing
# elements are located and parsed as two separate, unambiguous passes.
pos = 0
while True:
    open_m = re.compile(r'<style:style\s+([^>]*?)>').search(content_xml, pos)
    if not open_m:
        break
    attrs_raw = open_m.group(1)
    self_closing = attrs_raw.rstrip().endswith('/')
    attrs = attrs_raw.rstrip().rstrip('/')
    name_m = re.search(r'style:name="([^"]+)"', attrs)
    family_m = re.search(r'style:family="(paragraph|text)"', attrs)
    if not name_m or not family_m:
        pos = open_m.end()
        continue
    name, family = name_m.group(1), family_m.group(1)
    parent_m = re.search(r'style:parent-style-name="([^"]+)"', attrs)
    parent = parent_m.group(1) if parent_m else None

    if self_closing:
        body = ""
        pos = open_m.end()
    else:
        close_m = re.compile(r'</style:style>').search(content_xml, open_m.end())
        body = content_xml[open_m.end():close_m.start()] if close_m else ""
        pos = close_m.end() if close_m else open_m.end()

    weight_m = re.search(r'fo:font-weight="([^"]+)"', body)
    style_m = re.search(r'fo:font-style="([^"]+)"', body)
    weight = weight_m.group(1) if weight_m else None
    fstyle = style_m.group(1) if style_m else None
    lines.append(
        "automatic style %s (family=%s): parent-style-name=%s, fo:font-weight=%s, fo:font-style=%s"
        % (name, family, parent, weight, fstyle)
    )

outline_levels = re.findall(r'<text:h[^>]*\stext:outline-level="(\d+)"', content_xml)
lines.append("heading outline levels: %s" % sorted(set(int(x) for x in outline_levels)))

with open(evidence_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
PYEOF

echo "--- $EVIDENCE_FILE ---"
if [ ! -f "$EVIDENCE_FILE" ]; then
  echo "ERROR: evidence file was not created" >&2
  exit 1
fi
cat "$EVIDENCE_FILE"
