"""
Independent adjudication window.

Layout:
- Scrollable reviewer sidebar.
- Batch-folder and waveform-tool rows.
- Three selectable waveform panels.
- Four synchronized comparison timelines.
- Collapsible final-interval table.

Comparison loading, editing, persistence, and calipers are connected in
subsequent implementation steps.
"""

from __future__ import annotations

from typing import Optional

import pyqtgraph as pg

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtGui import QCloseEvent
from adjudication.config import (
    MINIMUM_VALID_INTERVAL_SEC,
    VALID_TERMINAL_EVENT_STATUSES,
)
from adjudication.config import ADJUDICATORS
from adjudication.models import AdjudicationComparisonResult
from adjudication_callbacks import AdjudicationAppCallbacks


# =============================================================================
# UI configuration
# =============================================================================

UM_MAIZE: str = "#FFCB05"
UM_BLUE: str = "#00274C"
UM_ACCENT: str = "#285680"
UM_RED: str = "#B71234"

AGREEMENT_COLOR: str = "#199E40"
DISAGREEMENT_COLOR: str = "#D50032"
MISSING_COLOR: str = "#888888"
RESOLVED_COLOR: str = "#2878B5"

VISIBLE_WAVEFORM_COUNT: int = 3
SIDEBAR_WIDTH: int = 300
TIMELINE_HEIGHT: int = 64


class AdjudicationWindow(QMainWindow, AdjudicationAppCallbacks):
    """
    Provide the independent adjudication application interface.

    Source annotator timelines are read-only. Final adjudication state is
    separate from standard annotation state.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Waveform Adjudication App")

        # Independent reviewer session state.
        self.adjudication_base_folder: str = ""
        self.adjudication_comparison: Optional[
            AdjudicationComparisonResult
        ] = None
        self.adjudication_dirty: bool = False

        self.adjudication_selected_interval_index: Optional[int] = None
        self.adjudication_selected_region_id: Optional[str] = None

        # Temporary highlighting only; these items are not saved.
        self.adjudication_selection_graphics: list[
            tuple[pg.PlotWidget, pg.LinearRegionItem]
        ] = []

        # Retain explicit widget references for later callbacks.
        self.adjudication_waveform_plots: list[pg.PlotWidget] = []
        self.adjudication_lead_selectors: list[QComboBox] = []
        self.adjudication_timeline_plots: dict[str, pg.PlotWidget] = {}
        self.adjudication_y_controls: list[dict[str, QPushButton]] = []

        # Draggable internal boundaries belong only to the final timeline.
        self.adjudication_boundary_lines: list[pg.InfiniteLine] = []

        # Index of the final interval awaiting a click-to-place split.
        self.adjudication_pending_split_index: Optional[int] = None

        # True until the first successfully saved draft replaces completed status.
        self.adjudication_reopened_from_complete: bool = False

        self.adjudication_complete: bool = False

        # Temporary waveform-overlay graphics, separate from selection highlights.
        self.adjudication_waveform_overlay_graphics: list[
            tuple[pg.PlotWidget, pg.LinearRegionItem]
        ] = []

        self._apply_styles()
        self._build_interface()
        self._connect_signals()
        self._size_window()

    # =========================================================================
    # Overall interface
    # =========================================================================

    def _apply_styles(self) -> None:
        """
        Apply the annotation application's maize, blue, and white visual theme.

        Use explicit widget selectors so sidebar styling does not unintentionally
        introduce borders around every child widget.
        """
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background-color: #FFFFFF;
            }}

            QWidget {{
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 12px;
            }}

            QWidget#AdjudicationSidebar {{
                background-color: {UM_MAIZE};
                border: none;
                border-right: 2px solid {UM_BLUE};
            }}

            QLabel {{
                color: {UM_BLUE};
                background: transparent;
                border: none;
            }}

            QLineEdit {{
                background-color: #FFFFFF;
                color: {UM_BLUE};
                border: 2px solid {UM_BLUE};
                border-radius: 3px;
                min-height: 24px;
                padding: 3px 5px;
                selection-background-color: {UM_BLUE};
                selection-color: {UM_MAIZE};
            }}

            QComboBox {{
                background-color: #FFFFFF;
                color: {UM_BLUE};
                border: 1px solid {UM_ACCENT};
                border-radius: 4px;
                min-height: 24px;
                padding: 3px 5px;
            }}

            QComboBox:disabled {{
                background-color: #F2F2F2;
                color: #777777;
                border: 1px solid #999999;
            }}

            QComboBox QAbstractItemView {{
                background-color: #FFFFFF;
                color: {UM_BLUE};
                selection-background-color: {UM_BLUE};
                selection-color: {UM_MAIZE};
                border: 1px solid {UM_ACCENT};
            }}

            QTextEdit {{
                background-color: #FFFFFF;
                color: {UM_BLUE};
                border: 2px solid {UM_BLUE};
                border-radius: 3px;
                padding: 3px;
            }}

            QTextEdit:disabled {{
                background-color: #F2F2F2;
                color: #777777;
                border: 1px solid #999999;
            }}

            QPushButton {{
                background-color: {UM_BLUE};
                color: {UM_MAIZE};
                border: 1px solid {UM_BLUE};
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
                font-weight: bold;
            }}

            QPushButton:hover {{
                background-color: {UM_ACCENT};
                border: 1px solid {UM_ACCENT};
            }}

            QPushButton:pressed {{
                background-color: {UM_BLUE};
                border: 2px solid {UM_MAIZE};
            }}

            QPushButton:checked {{
                background-color: {UM_MAIZE};
                color: {UM_BLUE};
                border: 2px solid {UM_BLUE};
            }}

            QPushButton:disabled {{
                background-color: #B0B0B0;
                color: #FFFFFF;
                border: 1px solid #888888;
            }}

            QToolButton {{
                background-color: {UM_BLUE};
                color: {UM_MAIZE};
                border: 1px solid {UM_ACCENT};
                border-radius: 3px;
                padding: 5px 8px;
                font-weight: bold;
            }}

            QToolButton:hover {{
                background-color: {UM_ACCENT};
            }}

            QCheckBox {{
                color: {UM_BLUE};
                background: transparent;
                spacing: 5px;
            }}

            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                background-color: #FFFFFF;
                border: 1px solid {UM_BLUE};
                border-radius: 2px;
            }}

            QCheckBox::indicator:checked {{
                background-color: {UM_MAIZE};
                border: 2px solid {UM_BLUE};
            }}

            QScrollArea {{
                background-color: {UM_MAIZE};
                border: none;
            }}

            QSplitter::handle:horizontal {{
                background-color: {UM_ACCENT};
                width: 3px;
            }}

            QSplitter::handle:vertical {{
                background-color: {UM_ACCENT};
                height: 3px;
            }}

            QTableWidget {{
                background-color: #FFFFFF;
                alternate-background-color: #E6F0FA;
                color: {UM_BLUE};
                gridline-color: {UM_ACCENT};
                border: 1px solid {UM_ACCENT};
            }}

            QHeaderView::section {{
                background-color: {UM_MAIZE};
                color: {UM_BLUE};
                border: 1px solid {UM_ACCENT};
                padding: 5px;
                font-weight: bold;
            }}
            """
        )

    def _build_interface(self) -> None:
        """Build the sidebar beside the waveform and timeline panel."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_main_panel(), stretch=1)

        self.setCentralWidget(container)

    def _size_window(self) -> None:
        """Size the window to fit the available display."""
        screen = QApplication.primaryScreen()

        if screen is None:
            self.resize(1300, 850)
            return

        available = screen.availableGeometry()
        self.resize(
            int(available.width() * 0.95),
            int(available.height() * 0.93),
        )

    # =========================================================================
    # Sidebar
    # =========================================================================

    def _add_heading(
        self,
        layout: QVBoxLayout,
        text: str,
    ) -> None:
        """
        Add a strong blue separator and section heading on the maize sidebar.
        """
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(2)
        separator.setStyleSheet(
            f"background-color:{UM_ACCENT}; border:none;"
        )
        layout.addWidget(separator)

        heading = QLabel(text)
        heading.setStyleSheet(
            f"""
            QLabel {{
                color: {UM_BLUE};
                background: transparent;
                border: none;
                font-size: 13px;
                font-weight: bold;
                padding-top: 3px;
                padding-bottom: 2px;
            }}
            """
        )
        layout.addWidget(heading)

    def _pending_button(
        self,
        text: str,
    ) -> QPushButton:
        """Create a disabled button for a not-yet-implemented action."""
        button = QPushButton(text)
        button.setEnabled(False)
        button.setToolTip(
            "This action will be enabled when its implementation is added."
        )
        return button

    def _build_sidebar(self) -> QScrollArea:
        """Create reviewer selection, final-label, and review-action controls."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(SIDEBAR_WIDTH)
        scroll.setFrameShape(QFrame.NoFrame)

        sidebar = QWidget()
        sidebar.setObjectName("AdjudicationSidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        title = QLabel("Adjudication")
        title.setStyleSheet(
            f"font-size:25px; font-weight:bold; color:{UM_BLUE};"
        )
        layout.addWidget(title)

        self._add_heading(layout, "REVIEWER AND RECORD")

        layout.addWidget(QLabel("Adjudicator"))
        self.adjudicator_dropdown = QComboBox()
        self.adjudicator_dropdown.addItem("Select adjudicator", "")

        for username in ADJUDICATORS:
            self.adjudicator_dropdown.addItem(username, username)

        layout.addWidget(self.adjudicator_dropdown)

        layout.addWidget(QLabel("Waveform Record"))
        self.adjudication_subject_dropdown = QComboBox()
        self.adjudication_subject_dropdown.setEnabled(False)
        layout.addWidget(self.adjudication_subject_dropdown)

        self.adjudication_load_btn = self._pending_button(
            "Load Waveform / Compare"
        )
        self.adjudication_resume_btn = self._pending_button(
            "Resume Adjudication"
        )
        layout.addWidget(self.adjudication_load_btn)
        layout.addWidget(self.adjudication_resume_btn)

        self.adjudication_input_status = QLabel(
            "Annotator A: Not loaded\nAnnotator B: Not loaded"
        )
        self.adjudication_input_status.setWordWrap(True)
        layout.addWidget(self.adjudication_input_status)

        self._add_heading(layout, "SELECTED FINAL INTERVAL")

        self.adjudication_selection_label = QLabel(
            "No interval selected.\nStart: —   End: —\nDuration: —"
        )
        self.adjudication_selection_label.setWordWrap(True)
        layout.addWidget(self.adjudication_selection_label)

        self.adjudication_comparison_details = QLabel(
            "Select a region to inspect the source labels."
        )
        self.adjudication_comparison_details.setWordWrap(True)
        layout.addWidget(self.adjudication_comparison_details)

        self._add_heading(layout, "FINAL LABEL")

        layout.addWidget(QLabel("Is this CPR?"))

        self.adjudication_cpr_dropdown = QComboBox()
        self.adjudication_cpr_dropdown.addItems(
            ["", "Yes", "No", "Unable to Determine"]
        )
        self.adjudication_cpr_dropdown.setEnabled(False)
        layout.addWidget(self.adjudication_cpr_dropdown)

        layout.addWidget(QLabel("Rhythm"))

        self.adjudication_rhythm_dropdown = QComboBox()
        self.adjudication_rhythm_dropdown.addItems(
            [
                "",
                "Normal Heart Rhythm",
                "Sinus tachycardia",
                "Bradycardia",
                "Supraventricular tachycardia",
                "Atrial Flutter",
                "Atrial Fibrillation",
                "Ventricular Tachycardia",
                "Ventricular Fibrillation",
                "Atrial Pacing Rhythm",
                "Ventricular Pacing Rhythm",
                "Idioventricular Rhythm",
                "Unable to Determine",
                "Other",
            ]
        )
        self.adjudication_rhythm_dropdown.setEnabled(False)
        layout.addWidget(self.adjudication_rhythm_dropdown)

        layout.addWidget(QLabel("Explanation / Comment"))

        self.adjudication_explanation = QTextEdit()
        self.adjudication_explanation.setMaximumHeight(75)
        self.adjudication_explanation.setEnabled(False)
        layout.addWidget(self.adjudication_explanation)

        self.adjudication_apply_btn = self._pending_button(
            "Apply Final Label"
        )
        layout.addWidget(self.adjudication_apply_btn)

        self._add_heading(layout, "BOUNDARY EDITING")

        boundary_row = QHBoxLayout()
        self.adjudication_add_boundary_btn = self._pending_button(
            "Add Boundary"
        )
        self.adjudication_remove_boundary_btn = self._pending_button(
            "Remove"
        )
        boundary_row.addWidget(self.adjudication_add_boundary_btn)
        boundary_row.addWidget(self.adjudication_remove_boundary_btn)
        layout.addLayout(boundary_row)

        boundary_help = QLabel(
            "Final timeline boundaries will be draggable."
        )
        boundary_help.setWordWrap(True)
        layout.addWidget(boundary_help)

        self._add_heading(layout, "REVIEW NAVIGATION")

        navigation_row = QHBoxLayout()
        self.adjudication_previous_btn = self._pending_button(
            "Previous"
        )
        self.adjudication_next_btn = self._pending_button("Next")
        navigation_row.addWidget(self.adjudication_previous_btn)
        navigation_row.addWidget(self.adjudication_next_btn)
        layout.addLayout(navigation_row)

        self.adjudication_resolve_btn = self._pending_button(
            "Mark Resolved"
        )
        layout.addWidget(self.adjudication_resolve_btn)

        self.adjudication_progress_label = QLabel(
            "Unresolved regions: Not loaded"
        )
        layout.addWidget(self.adjudication_progress_label)

        self._add_heading(layout, "SAVE AND COMPLETE")

        self.adjudication_save_btn = self._pending_button("Save Draft")
        self.adjudication_finalize_btn = self._pending_button(
            "Finalize Adjudication"
        )
        self.adjudication_reopen_btn = self._pending_button(
            "Reopen for Editing"
        )

        layout.addWidget(self.adjudication_save_btn)
        layout.addWidget(self.adjudication_finalize_btn)
        layout.addWidget(self.adjudication_reopen_btn)

        self.adjudication_save_status = QLabel("")
        self.adjudication_save_status.setWordWrap(True)

        # Long messages must wrap without increasing the sidebar's width.
        self.adjudication_save_status.setMinimumWidth(0)
        self.adjudication_save_status.setMaximumWidth(
            SIDEBAR_WIDTH - 40
        )
        self.adjudication_save_status.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )

        layout.addWidget(self.adjudication_save_status)

        layout.addStretch(1)
        scroll.setWidget(sidebar)
        return scroll

    # =========================================================================
    # Main visual panel
    # =========================================================================

    def _build_main_panel(self) -> QWidget:
        """Build folder controls, waveform panels, timelines, and final table."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Annotation Batch Folder:"))

        self.adjudication_folder_input = QLineEdit()
        self.adjudication_folder_input.setPlaceholderText(
            "Paste an annotation batch folder path"
        )
        folder_row.addWidget(
            self.adjudication_folder_input,
            stretch=1,
        )

        self.adjudication_browse_btn = QPushButton("Browse")
        folder_row.addWidget(self.adjudication_browse_btn)

        self.adjudication_set_folder_btn = QPushButton("Set Folder")
        folder_row.addWidget(self.adjudication_set_folder_btn)

        layout.addLayout(folder_row)

        self.adjudication_status_label = QLabel(
            "Select a batch folder. Loading and editing will be added next."
        )
        self.adjudication_status_label.setWordWrap(True)
        layout.addWidget(self.adjudication_status_label)

        tools_row = QHBoxLayout()

        self.adjudication_caliper_btn = self._pending_button("Calipers")
        tools_row.addWidget(self.adjudication_caliper_btn)

        self.adjudication_caliper_result = QLabel("Calipers: Off")
        tools_row.addWidget(self.adjudication_caliper_result)

        tools_row.addStretch(1)

        self.adjudication_overlay_checks: dict[str, QCheckBox] = {}

        for name in ("Annotator A", "Annotator B", "Final"):
            checkbox = QCheckBox(name)

            # Display the separated source overlays initially.
            # The reviewer can enable the full-height final overlay when needed.
            checkbox.setChecked(name != "Final")
            checkbox.setEnabled(False)

            checkbox.setToolTip(
                {
                    "Annotator A": "Show source annotations in the upper half.",
                    "Annotator B": "Show source annotations in the lower half.",
                    "Final": "Show final adjudication across the full plot height.",
                }[name]
            )

            self.adjudication_overlay_checks[name] = checkbox
            tools_row.addWidget(checkbox)

        layout.addLayout(tools_row)

        self.adjudication_visual_splitter = QSplitter(Qt.Vertical)

        waveform_panel = QWidget()
        waveform_layout = QVBoxLayout(waveform_panel)
        waveform_layout.setContentsMargins(0, 0, 0, 0)
        waveform_layout.setSpacing(3)

        for index in range(VISIBLE_WAVEFORM_COUNT):
            waveform_layout.addWidget(
                self._build_waveform_row(index),
                stretch=1,
            )

        timeline_panel = QWidget()
        timeline_layout = QVBoxLayout(timeline_panel)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.setSpacing(3)

        for name in (
            "Annotator A",
            "Annotator B",
            "Agreement / Review",
            "Final Adjudication",
        ):
            timeline_layout.addWidget(
                self._build_timeline_row(name)
            )

        timeline_layout.addWidget(self._build_status_legend())

        self.adjudication_visual_splitter.addWidget(waveform_panel)
        self.adjudication_visual_splitter.addWidget(timeline_panel)
        self.adjudication_visual_splitter.setChildrenCollapsible(False)
        self.adjudication_visual_splitter.setStretchFactor(0, 3)
        self.adjudication_visual_splitter.setStretchFactor(1, 1)
        self.adjudication_visual_splitter.setSizes([600, 280])

        layout.addWidget(
            self.adjudication_visual_splitter,
            stretch=1,
        )

        self._link_plot_axes()

        # A small collapsible table preserves waveform space.
        self.adjudication_table_toggle = QToolButton()
        self.adjudication_table_toggle.setText("Final Interval Table")
        self.adjudication_table_toggle.setCheckable(True)
        self.adjudication_table_toggle.setChecked(False)
        self.adjudication_table_toggle.setArrowType(Qt.RightArrow)
        self.adjudication_table_toggle.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
        )
        layout.addWidget(self.adjudication_table_toggle)

        self.adjudication_table = QTableWidget(0, 5)
        self.adjudication_table.setHorizontalHeaderLabels(
            ["CPR", "Rhythm", "Explanation", "Start", "End"]
        )
        self.adjudication_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.adjudication_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.adjudication_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.adjudication_table.setAlternatingRowColors(True)
        self.adjudication_table.setFixedHeight(140)
        self.adjudication_table.setVisible(False)
        layout.addWidget(self.adjudication_table)

        return panel

    def _build_waveform_row(self, index: int) -> QWidget:
        """Create one waveform plot with a lead selector and Y controls."""
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        control_widget = QWidget()
        controls = QVBoxLayout(control_widget)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(2)
        control_widget.setFixedWidth(115)

        selector = QComboBox()
        selector.addItem(f"Waveform {index + 1}")
        selector.setEnabled(False)
        self.adjudication_lead_selectors.append(selector)
        controls.addWidget(selector)

        button_map: dict[str, QPushButton] = {}

        for labels in (("Y-IN", "Y-OUT"), ("Y+", "Y-")):
            button_row = QHBoxLayout()
            button_row.setSpacing(2)

            for label in labels:
                button = self._pending_button(label)
                button_map[label] = button
                button_row.addWidget(button)

            controls.addLayout(button_row)

        auto_button = self._pending_button("AUTO-Y")
        button_map["AUTO-Y"] = auto_button
        controls.addWidget(auto_button)
        controls.addStretch(1)

        self.adjudication_y_controls.append(button_map)
        row.addWidget(control_widget)

        plot = self._make_plot()
        plot.setMinimumHeight(100)
        plot.setLabel("left", f"Waveform {index + 1}")
        self.adjudication_waveform_plots.append(plot)
        row.addWidget(plot, stretch=1)

        return row_widget

    def _build_timeline_row(self, name: str) -> QWidget:
        """Create a compact, read-only timeline placeholder."""
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        label = QLabel(name)
        label.setFixedWidth(115)
        label.setWordWrap(True)
        label.setStyleSheet("font-weight:bold;")
        row.addWidget(label)

        plot = self._make_plot()
        plot.setFixedHeight(TIMELINE_HEIGHT)
        plot.hideAxis("left")
        plot.setYRange(0, 1, padding=0)

        self.adjudication_timeline_plots[name] = plot
        row.addWidget(plot, stretch=1)

        return row_widget

    def _build_status_legend(self) -> QWidget:
        """Explain comparison colors without implying clinical correctness."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(119, 0, 0, 0)

        statuses = (
            ("Agreement", AGREEMENT_COLOR),
            ("Unresolved", DISAGREEMENT_COLOR),
            ("Missing coverage", MISSING_COLOR),
            ("Resolved", RESOLVED_COLOR),
        )

        for text, color in statuses:
            label = QLabel(f"■ {text}")
            label.setStyleSheet(f"color:{color}; font-weight:bold;")
            row.addWidget(label)

        row.addStretch(1)
        widget.setToolTip(
            "Green indicates annotator agreement, not clinical correctness. "
            "Every final interval remains under adjudicator oversight."
        )
        return widget

    def _make_plot(self) -> pg.PlotWidget:
        """Create a white-background, horizontally navigable plot."""
        plot = pg.PlotWidget()
        plot.setBackground("w")
        plot.showGrid(x=True, y=False, alpha=0.2)
        plot.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        plot.getViewBox().setMouseEnabled(x=True, y=False)
        plot.hideAxis("bottom")
        return plot

    def _link_plot_axes(self) -> None:
        """Link waveform and timeline plots to one shared X-range."""
        anchor = self.adjudication_waveform_plots[0]

        for plot in self.adjudication_waveform_plots[1:]:
            plot.setXLink(anchor)

        for plot in self.adjudication_timeline_plots.values():
            plot.setXLink(anchor)

        final_plot = self.adjudication_timeline_plots[
            "Final Adjudication"
        ]
        final_plot.showAxis("bottom")
        final_plot.setLabel("bottom", "Time — no waveform loaded")

    # =========================================================================
    # Implemented UI connections
    # =========================================================================

    def _connect_signals(self) -> None:
        """
        Connect implemented discovery, loading, lead-selection, and Y controls.

        Editing, saving, finalization, overlays, and calipers remain disabled.
        """
        self.adjudication_browse_btn.clicked.connect(
            self.browse_adjudication_base_folder
        )

        self.adjudication_set_folder_btn.clicked.connect(
            self.set_adjudication_base_folder
        )

        self.adjudication_folder_input.returnPressed.connect(
            self.set_adjudication_base_folder
        )

        self.adjudication_table_toggle.toggled.connect(
            self._toggle_final_table
        )

        self.adjudicator_dropdown.currentIndexChanged.connect(
            self.update_adjudication_load_availability
        )

        self.adjudication_subject_dropdown.currentIndexChanged.connect(
            self.update_adjudication_load_availability
        )

        self.adjudication_load_btn.clicked.connect(
            self.load_adjudication_record
        )

        self.adjudication_table.itemSelectionChanged.connect(
            self.handle_adjudication_table_selection
        )

        self.adjudication_previous_btn.clicked.connect(
            lambda _checked=False:
                self.navigate_adjudication_unresolved(-1)
        )

        self.adjudication_next_btn.clicked.connect(
            lambda _checked=False:
                self.navigate_adjudication_unresolved(1)
        )

        self.adjudication_cpr_dropdown.currentTextChanged.connect(
            self.update_adjudication_label_controls
        )

        self.adjudication_rhythm_dropdown.currentTextChanged.connect(
            self.update_adjudication_label_controls
        )

        self.adjudication_explanation.textChanged.connect(
            self.update_adjudication_label_controls
        )

        self.adjudication_apply_btn.clicked.connect(
            self.apply_adjudication_final_label
        )

        self.adjudication_resolve_btn.clicked.connect(
            self.mark_adjudication_region_resolved
        )

        self.adjudication_save_btn.clicked.connect(
            self.save_current_adjudication_draft
        )

        self.adjudication_resume_btn.clicked.connect(
            self.resume_current_adjudication
        )

        self.adjudication_add_boundary_btn.clicked.connect(
            self.add_adjudication_boundary
        )

        self.adjudication_remove_boundary_btn.clicked.connect(
            self.remove_adjudication_boundary
        )

        self.adjudication_finalize_btn.clicked.connect(
            self.finalize_current_adjudication
        )

        self.adjudication_reopen_btn.clicked.connect(
            self.reopen_current_adjudication
        )

        for checkbox in self.adjudication_overlay_checks.values():
            checkbox.toggled.connect(
                self.handle_adjudication_overlay_toggle
            )

        # Connect once during window construction.
        for row_index, plot in enumerate(self.adjudication_waveform_plots):
            plot.scene().sigMouseClicked.connect(
                lambda event, row=row_index:
                    self.handle_adjudication_waveform_click(row, event)
            )

        # Connect once during construction—not each time a comparison is loaded.
        for track_name, plot in self.adjudication_timeline_plots.items():
            plot.scene().sigMouseClicked.connect(
                lambda event, name=track_name:
                    self.handle_adjudication_timeline_click(name, event)
            )

        for row_index, selector in enumerate(
            self.adjudication_lead_selectors
        ):
            selector.currentIndexChanged.connect(
                lambda _index, row=row_index:
                    self.draw_adjudication_waveform(row)
            )

        actions = {
            "Y-IN": "in",
            "Y-OUT": "out",
            "Y+": "up",
            "Y-": "down",
            "AUTO-Y": "auto",
        }

        for row_index, controls in enumerate(
            self.adjudication_y_controls
        ):
            for button_name, action in actions.items():
                controls[button_name].clicked.connect(
                    lambda _checked=False, row=row_index, operation=action:
                        self.adjust_adjudication_y(row, operation)
                )

    def _toggle_final_table(self, expanded: bool) -> None:
        """Show or hide the final interval table."""
        self.adjudication_table.setVisible(expanded)
        self.adjudication_table_toggle.setArrowType(
            Qt.DownArrow if expanded else Qt.RightArrow
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Prevent accidental loss of in-memory adjudication edits.
        """
        if self.confirm_discard_adjudication_changes():
            event.accept()
        else:
            event.ignore()