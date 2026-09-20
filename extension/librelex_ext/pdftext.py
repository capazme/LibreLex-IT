# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Rebuilds reading-order text from a PDF's Draw-imported text frames (design §4.2).

LibreOffice's ``draw_pdf_import`` filter gives one shape per text run, each with its own
position, not the paragraphs of the original document: this module puts the words back on
lines and the lines back in reading order from their geometry alone. Pure: no UNO here.
"""
from __future__ import annotations

Frame = tuple[int, int, int, int, str]  # (page, y, x, height, text)


class _Line:
    """One reconstructed line: the frames that joined it, and the centre/height of the
    first frame that started it (later frames are compared against this fixed baseline).
    """

    def __init__(self, frame: Frame) -> None:
        self.frames: list[Frame] = [frame]
        self.centre = frame[1] + frame[3] / 2
        self.height = frame[3]

    def joins(self, frame: Frame) -> bool:
        centre = frame[1] + frame[3] / 2
        return abs(centre - self.centre) < 0.5 * max(frame[3], self.height)

    def text(self) -> str:
        ordered = sorted(self.frames, key=lambda f: f[2])
        parts = [f[4].strip() for f in ordered if f[4].strip()]
        return " ".join(parts)


def _group_lines(page_frames: list[Frame]) -> list[_Line]:
    lines: list[_Line] = []
    current: _Line | None = None
    for frame in page_frames:
        if current is not None and current.joins(frame):
            current.frames.append(frame)
        else:
            current = _Line(frame)
            lines.append(current)
    return lines


def rebuild_lines(frames: list[Frame]) -> str:
    pages: dict[int, list[Frame]] = {}
    for frame in frames:
        pages.setdefault(frame[0], []).append(frame)

    out_lines: list[str] = []
    any_page_emitted = False
    for page in sorted(pages):
        page_frames = sorted(pages[page], key=lambda f: (f[1], f[2]))
        texts = [t for line in _group_lines(page_frames) if (t := line.text())]
        if not texts:
            continue
        if any_page_emitted:
            out_lines.append(f"--- pagina {page} ---")
        out_lines.extend(texts)
        any_page_emitted = True
    return "\n".join(out_lines)
