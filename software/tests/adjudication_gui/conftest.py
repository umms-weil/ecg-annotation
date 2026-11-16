"""
Fixtures for testing the actual adjudication window.

Waveforms and annotation inputs are synthetic. Files are written only to
pytest temporary directories.

Unsaved-work confirmation is bypassed for these test windows so cleanup
does not require manual interaction.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np
import pytest

from adjudication.comparison import build_adjudication_comparison
from adjudication_app import AdjudicationWindow


@pytest.fixture
def adjudication_window(
    qtbot,
    waveform_record,
    write_annotation_file,
    annotators,
    adjudicator,
    monkeypatch,
) -> Iterator[AdjudicationWindow]:
    """
    Create a populated adjudication window with a known rhythm disagreement.

    Both annotators cover the same interval but assign different rhythms.
    No network discovery or source waveform loading is performed.

    The unsaved-work confirmation is patched only on this test instance.
    Production application behavior remains unchanged.
    """
    start = 1_700_000_000.0
    end = start + 10.0

    write_annotation_file(
        user=annotators[0],
        intervals=[
            {
                "start": start,
                "end": end,
                "cpr": "No",
                "rhythm_label": "Normal Heart Rhythm",
            }
        ],
    )

    write_annotation_file(
        user=annotators[1],
        intervals=[
            {
                "start": start,
                "end": end,
                "cpr": "No",
                "rhythm_label": "Bradycardia",
            }
        ],
    )

    comparison = build_adjudication_comparison(
        record=waveform_record,
        adjudicator=adjudicator,
        annotators=annotators,
        allowed_adjudicators=[adjudicator],
    )

    window = AdjudicationWindow()

    # Prevent close/reload confirmation dialogs from blocking test execution.
    # This patch affects only the synthetic test window.
    monkeypatch.setattr(
        window,
        "confirm_discard_adjudication_changes",
        lambda: True,
    )

    qtbot.addWidget(window)

    try:
        window.adjudication_comparison = comparison
        window.adjudication_loaded_record = dict(waveform_record)
        window.adjudication_loaded_reviewer = adjudicator

        window.adjudication_waveform_start = start
        window.adjudication_waveform_end = end

        # Synthetic signals support waveform and caliper interaction tests.
        sample_count = 2400
        relative_time = (
            np.arange(sample_count, dtype=float) / 240.0
        )
        time_axis = start + relative_time

        window.adjudication_time_axis = time_axis
        window.adjudication_times_by_lead = [
            time_axis,
            time_axis,
        ]
        window.adjudication_leads = [
            np.sin(2.0 * np.pi * relative_time),
            np.sin(2.0 * np.pi * relative_time + 0.2),
        ]
        window.adjudication_lead_names = ["II", "I"]
        window.adjudication_units = ["mV", "mV"]

        window._populate_adjudication_lead_selectors([0, 1])

        window.adjudication_waveform_plots[0].setXRange(
            start,
            end,
            padding=0,
        )

        window.adjudication_calipers.refresh_sources()
        window.draw_adjudication_timelines()
        window.populate_adjudication_table()
        window.select_adjudication_interval(0)
        window.update_adjudication_navigation_controls()

        window.show()
        qtbot.wait(20)

        yield window

    finally:
        # The confirmation patch also protects pytest-qt's window cleanup.
        try:
            window.adjudication_calipers.clear()
        finally:
            window.adjudication_comparison = None
            window.adjudication_dirty = False
            window.close()