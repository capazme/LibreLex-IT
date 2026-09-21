# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.pdftext import rebuild_lines


def test_words_on_one_baseline_become_one_line_in_x_order():
    frames = [(1, 1000, 3000, 400, "espone"), (1, 1010, 1000, 400, "Il"),
              (1, 990, 2000, 400, "ricorrente"), (1, 1005, 4000, 400, "quanto segue.")]
    assert rebuild_lines(frames) == "Il ricorrente espone quanto segue."


def test_lines_pages_and_empty_frames():
    frames = [(2, 500, 1000, 400, "Seconda pagina"), (1, 1000, 1000, 400, "Prima riga"),
              (1, 1600, 1000, 400, "Seconda riga"), (1, 1600, 3000, 400, "  "),
              (1, 2300, 1000, 400, "")]
    assert rebuild_lines(frames) == "Prima riga\nSeconda riga\n--- pagina 2 ---\nSeconda pagina"
    assert rebuild_lines([]) == "" and rebuild_lines([(1, 0, 0, 10, " ")]) == ""
