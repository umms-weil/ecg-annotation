import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QComboBox, QTextEdit, QSlider, QSpinBox, QTableWidget,
    QAbstractItemView, QButtonGroup, QHeaderView, QFrame,
    QToolButton, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
import pyqtgraph as pg
from new_callbacks import AnnotationAppCallbacks
import pyqtgraph as pg

UM_MAIZE = "#FFCB05"
UM_BLUE = "#00274C"
UM_ACCENT = "#285680"
UM_WHITE = "#FFFFFF"
UM_RED = "#D50032"
COMPLETION_GREEN = "#199E40"

# Dropdown wrapper for signals
class CollapsibleWaveformSection(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, title, content_widget, parent=None):
        super().__init__(parent)

        self.content_widget = content_widget

        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setToolTip(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Narrower button.
        # Adjust 72/80/90 depending on how much label you want visible.
        self.toggle_button.setFixedWidth(78)
        self.toggle_button.setFixedHeight(28)

        self.toggle_button.setStyleSheet(f"""
            QToolButton {{
                background-color: {UM_BLUE};
                color: {UM_MAIZE};
                font-size: 10px;
                font-weight: bold;
                border: 1px solid {UM_ACCENT};
                border-radius: 3px;
                padding-left: 2px;
                text-align: left;
            }}
            QToolButton:hover {{
                background-color: {UM_ACCENT};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Key part:
        # Align the caret button to the top-left so it does not float in the center
        # when the row gets taller.
        layout.addWidget(self.toggle_button, 0, Qt.AlignLeft | Qt.AlignTop)

        # Plot/content gets all remaining horizontal space.
        layout.addWidget(self.content_widget, 1)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.toggle_button.toggled.connect(self.set_expanded)

        self.set_expanded(True)

    def set_title(self, title):
        if title is None:
            return

        title = str(title).strip()
        if not title:
            return

        self.toggle_button.setText(title)
        self.toggle_button.setToolTip(title)

    def set_expanded(self, expanded):
        self.content_widget.setVisible(expanded)

        if expanded:
            self.toggle_button.setArrowType(Qt.DownArrow)

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
        else:
            self.toggle_button.setArrowType(Qt.RightArrow)

            collapsed_h = self.toggle_button.height() + 2
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.setMinimumHeight(collapsed_h)
            self.setMaximumHeight(collapsed_h)

        self.updateGeometry()
        self.toggled.emit(expanded)

    def is_expanded(self):
        return self.content_widget.isVisible()

class MainApp(QMainWindow, AnnotationAppCallbacks):
    def __init__(self):
        super().__init__()
        # ---- Window setup ---
        self.setWindowTitle("Waveform Annotation App (U-M Theme)")
        screen = QApplication.primaryScreen().availableGeometry()
        # self.resize(screen.width(), screen.height())
        # For a margin:
        self.resize(int(screen.width() * 0.95), int(screen.height() * 0.95))
        self.move(screen.left() + int(screen.width()*0.025), screen.top() + int(screen.height()*0.025))
        self.setMaximumSize(screen.width(), screen.height())

        # ---- State variables ----
        self.username_list = ["", "pwalczyk", "sardara", "ghamid"]
        self.base_folder = ""
        self.data_store = {}
        self.annotations = []
        self.current_marker = None
        self.last_mark = 0.0
        self.n_mark_clicks = 0
        self.triggered_by_mark_btn = False
        self.waveform_complete = False
        self.waveform_complete = False
        self.terminal_event_status = ""
        self.terminal_event_comment = ""

        font_css = f"font-size:13px; color:{UM_BLUE}; background:white; border:2px solid black;"

        # --- SIDEBAR Layout ---
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar.setMaximumWidth(355)
        sidebar.setStyleSheet(f"background-color: {UM_MAIZE}; border-right:2px solid {UM_BLUE};")

        header = QLabel("Annotations")
        header.setStyleSheet(f"""
            font-size:32px;
            font-weight:bold;
            color:{UM_BLUE};
            border-bottom: 3px solid {UM_MAIZE};
            margin-bottom: 8px;
        """)
        header.setFixedHeight(40)
        header.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(header)

        # ---- User/subject input ----
        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: {UM_ACCENT}; min-height: 2px; border:none;")
        sidebar_layout.addWidget(sep)

        lab = QLabel("User Name:"); 
        lab.setStyleSheet(f"""
            font-size:18px;
            font-weight:bold;
            color:{UM_BLUE};
            border-bottom: 3px solid {UM_MAIZE};
        """)
        lab.setFixedHeight(25)
        lab.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(lab)

        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: {UM_ACCENT}; min-height: 2px; border:none;")
        sidebar_layout.addWidget(sep)

        # --- Username input ---
        self.username_input = QComboBox()
        self.username_input.setStyleSheet(font_css)
        # Static User List
        usernames = self.username_list
        self.username_input.addItems(usernames)
        # Prevent free-form text input
        self.username_input.setEditable(False)
        self.username_input.view().setMinimumWidth(500)
        sidebar_layout.addWidget(self.username_input)
        # Default to the first item (empty)
        self.username_input.setCurrentIndex(0)

        # --- Subject selection ---
        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: {UM_ACCENT}; min-height: 2px; border:none;")
        sidebar_layout.addWidget(sep)

        lab = QLabel("Subject:"); 
        lab.setStyleSheet(f"""
            font-size:18px;
            font-weight:bold;
            color:{UM_BLUE};
            border-bottom: 3px solid {UM_MAIZE};
        """)
        lab.setFixedHeight(25)
        lab.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(lab)

        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: {UM_ACCENT}; min-height: 2px; border:none;")
        sidebar_layout.addWidget(sep)

        # --- Subject dropdown ---
        self.subject_dropdown = QComboBox(); 
        self.subject_dropdown.setStyleSheet(font_css)
        self.subject_dropdown.view().setMinimumWidth(500)
        sidebar_layout.addWidget(self.subject_dropdown)

        # --- Load / Plot buttons ---
        row = QHBoxLayout()
        self.load_subject_btn = QPushButton("Load Subject")
        self.load_subject_btn.setStyleSheet(f"background:{UM_BLUE}; color:{UM_MAIZE}; font-size:13px; font-weight:bold; border-radius:4px;")
        # self.plot_btn = QPushButton("Plot")
        row.addWidget(self.load_subject_btn); 
        # row.addWidget(self.plot_btn)
        

        # --- Load Annotations Button ---
        self.load_annotation_btn = QPushButton("Load Annotations")
        self.load_annotation_btn.setStyleSheet(f"background:{UM_BLUE}; color:{UM_MAIZE}; font-size:13px; font-weight:bold; border-radius:4px;")
        row.addWidget(self.load_annotation_btn)

        sidebar_layout.addLayout(row)

        # --- Block styling for Question buttons ---
        block_css = """
        QPushButton {
            background-color: #FFCB05;
            color: #00274C;
            border: 2px solid #00274C;
            border-radius: 8px;
            font-size: 16px;
            min-width: 80px;
            min-height: 15px;
            max-height: 20px;
            padding: 0px;
            font-weight: bold;
        }
        QPushButton:checked {
            background-color: #00274C;
            color: #FFCB05;
        }
        """

        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: {UM_ACCENT}; min-height: 2px; border:none;")
        sidebar_layout.addWidget(sep)

        # --- CPR Question ---
        # Container widget for highlight area
        lab = QLabel("Is this CPR?")
        lab.setStyleSheet(f"""
            font-size:18px;
            font-weight:bold;
            color:{UM_BLUE};
            border-bottom: 3px solid {UM_MAIZE};
        """)
        lab.setFixedHeight(25)
        lab.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(lab)

        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: {UM_ACCENT}; min-height: 2px; border:none;")
        sidebar_layout.addWidget(sep)

        self.cpr_yes = QPushButton('YES')
        self.cpr_no = QPushButton('NO')
        self.cpr_U2D = QPushButton('Unable to Determine')
        self.cpr_yes.setCheckable(True)
        self.cpr_no.setCheckable(True)
        self.cpr_U2D.setCheckable(True)
        self.cpr_group = QButtonGroup()
        self.cpr_group.addButton(self.cpr_yes)
        self.cpr_group.addButton(self.cpr_no)
        self.cpr_group.addButton(self.cpr_U2D)
        self.cpr_group.setExclusive(True)
        self.cpr_yes.setStyleSheet(block_css)
        self.cpr_no.setStyleSheet(block_css)
        self.cpr_U2D.setStyleSheet(block_css)

        # cpr_row = QHBoxLayout()
        # cpr_row.addWidget(self.cpr_yes)
        # cpr_row.addWidget(self.cpr_no)

        cpr_vert = QVBoxLayout()
        cpr_vert.addWidget(self.cpr_yes)
        cpr_vert.addWidget(self.cpr_no)
        cpr_vert.addWidget(self.cpr_U2D)
        sidebar_layout.addLayout(cpr_vert)

        # --- Rhythm type Question ---
        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: {UM_ACCENT}; min-height: 2px; border:none;")
        sidebar_layout.addWidget(sep)

        lab = QLabel("Rhythm Type"); 
        lab.setStyleSheet(f"""
            font-size:18px;
            font-weight:bold;
            color:{UM_BLUE};
            border-bottom: 3px solid {UM_MAIZE};
        """)
        lab.setFixedHeight(25)
        lab.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(lab)

        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"background-color: {UM_ACCENT}; min-height: 2px; border:2px;")
        sidebar_layout.addWidget(sep)

        # --- Rhythm type dropdown ---
        self.rhythm_dropdown = QComboBox(); 
        self.rhythm_dropdown.setStyleSheet("""
            QComboBox {
                font-size: 13px;
                color: #00274C;          /* Normal - UM Blue */
                background: #FFFFFF;
                border: 1px solid #285680;
                border-radius: 4px;
            }
            QComboBox:disabled {
                color: #888888;          /* Gray text */
                background: #f2f2f2;     /* Light gray background */
                border: 1px solid #CCCCCC;
            }
        """)
        self.rhythm_dropdown.addItems([
            "Normal Heart Rhythm", "Sinus tachycardia", "Bradycardia",
            "Supraventricular tachycardia", "Atrial Flutter", "Atrial Fibrillation",
            "Ventricular Tachycardia", "Ventricular Fibrillation",
            "Atrial Pacing Rhythm", "Ventricular Pacing Rhythm", "Idioventricular Rhythm",
            "Unable to Determine", "Other"
        ])
        sidebar_layout.addWidget(self.rhythm_dropdown)

        # --- Rhythm explanation (If "Unable to Determine" or "Other")---
        lab = QLabel("Signal Explanation"); 
        lab.setStyleSheet(f"""
            font-size:18px;
            font-weight:bold;
            color:{UM_BLUE};
            border-bottom: 3px solid {UM_MAIZE};
        """)
        lab.setFixedHeight(25)
        lab.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(lab)

        # --- Rhythm Explanation Box ---
        self.rhythm_explanation = QTextEdit()
        self.rhythm_explanation.setMaximumHeight(40)  
        self.rhythm_explanation.setStyleSheet(font_css)
        sidebar_layout.addWidget(self.rhythm_explanation)

        # --- Marking button ---
        self.mark_btn = QPushButton("Mark"); 
        self.mark_btn.setMinimumHeight(48)
        self.mark_btn.setMinimumWidth(160)
        self.mark_btn.setStyleSheet(f"""
            background: {UM_BLUE};
            color: {UM_MAIZE};
            font-size: 20px;
            font-weight: bold;
            border-radius: 8px;
            padding: 8px 32px;
        """)
        sidebar_layout.addWidget(self.mark_btn)

        self.finalize_waveform_btn = QPushButton("Finalize Waveform")
        self.finalize_waveform_btn.setDisabled(True)
        self.finalize_waveform_btn.setStyleSheet(
            f"""
            QPushButton {{
                background:{UM_BLUE};
                color:{UM_MAIZE};
                font-size:13px;
                font-weight:bold;
                border-radius:4px;
                padding:6px;
            }}
            QPushButton:disabled {{
                background:#B0B0B0;
                color:#FFFFFF;
            }}
            """
        )
        sidebar_layout.addWidget(self.finalize_waveform_btn)

        # self.waveform_complete is True after annotation ends and should disable further marking
        self.mark_btn.setDisabled(self.waveform_complete)

        # --- Marking warning label ---
        self.mark_warning = QLabel("")
        self.mark_warning.setWordWrap(True)
        self.mark_warning.setStyleSheet(f"font-size:24px; font-weight:bold; color:{UM_RED};")
        self.mark_warning.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        sidebar_layout.addWidget(self.mark_warning)

        # --- Undo Marking Button ---
        self.remove_last_btn = QPushButton("Remove Last Mark")
        self.remove_last_btn.setStyleSheet("""
            background: #B71234;     /* U-M Red */
            color: #FFFFFF;
            font-size: 14px;
            font-weight: bold;
            border-radius: 4px;
            padding: 8px 16px;
        """)

        # If no marks have been made, disable the button
        self.remove_last_btn.setDisabled(True)
        sidebar_layout.addWidget(self.remove_last_btn)

        # Connect the button to a handler that removes the last mark from the annotations list and updates the UI
        self.remove_last_btn.clicked.connect(self.handle_remove_last_mark)

        # saved_ann = sidebar_layout.addWidget(QLabel("Saved Annotations:")); saved_ann.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")

        # --- Save All Annotation button ---
        self.save_all_btn = QPushButton("Save All Annotations"); 
        self.save_all_btn.setMinimumHeight(24)
        self.save_all_btn.setMinimumWidth(160)
        self.save_all_btn.setStyleSheet(f"""
            background: {UM_BLUE};
            color: {UM_MAIZE};
            font-size: 20px;
            font-weight: bold;
            border-radius: 8px;
            padding: 8px 32px;
        """)
        sidebar_layout.addWidget(self.save_all_btn)
        self.save_message = QLabel(""); sidebar_layout.addWidget(self.save_message)


        sidebar_layout.setSpacing(4)
        sidebar_layout.setContentsMargins(4, 2, 4, 2)

        # --- MAIN PANEL Layout (For Plots)---
        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_panel.setStyleSheet(f"background-color: {UM_WHITE}; border:none;")

        # -- Base folder selection row ---
        folderrow = QHBoxLayout()
        folderlab = QLabel("Select Base Data Folder:"); folderlab.setStyleSheet(f"font-size:13px; color:{UM_ACCENT}; font-weight: bold;")
        folderrow.addWidget(folderlab)
        self.folder_input = QLineEdit(); self.folder_input.setStyleSheet(font_css)
        folderrow.addWidget(self.folder_input)
        self.set_folder_btn = QPushButton("Set Folder"); self.set_folder_btn.setStyleSheet(f"background:{UM_BLUE}; color:{UM_MAIZE}; font-size:13px; font-weight:bold; border-radius:1px;")
        folderrow.addWidget(self.set_folder_btn)
        main_layout.addLayout(folderrow)

        # -- Folder status label --
        self.folder_status = QLabel("")
        self.folder_status.setStyleSheet(f"font-size:12px; color:{UM_BLUE}; margin-top:0px; margin-bottom:0px; font-weight:bold;")
        main_layout.addWidget(self.folder_status)

        # ---- Waveform plots State Variable ----
        self.waveform_plots = []
        self.waveform_sections = []
        self.y_shift_buttons = []  # To store Y+ / Y– buttons for each plot
        self.y_zoom_buttons = [] # To store Y-IN / Y–Out buttons for each plot
        self.auto_y_buttons = [] # To store Y autoscale button for each plot

        # ---- Auto-Y behavior settings ----
        self.auto_y_enabled_by_user = []   # One bool per plot. True = user wants Auto-Y ON.
        self.auto_y_buffer_sec = 10.0      # Extra time around visible window for smoother scaling.
        self.max_auto_y_window_sec = 300.0 # Adjustable max visible time window for Auto-Y.
        self.auto_y_debounce_ms = 200      # Delay after X zoom/scroll before autoscaling.
        self.auto_y_margin_fraction = 0.1 # 5% y-padding above/below signal.
        self.auto_y_min_span = 0.25        # Minimum y-span if signal is flat/nearly flat.

        # Container for all waveform sections.
        # This lets collapsed plots shrink while expanded plots share the newly available space.
        plots_container = QWidget()
        self.plots_layout = QVBoxLayout(plots_container)
        self.plots_layout.setContentsMargins(0, 0, 0, 0)
        self.plots_layout.setSpacing(1)
        plots_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


        # ---- Create up to 7 collapsible waveform plots with existing controls ----
        for lead_idx in range(7):
            default_waveform_label = f"Waveform {lead_idx + 1}"

            plt = pg.PlotWidget()
            plt.setBackground(UM_WHITE)
            plt.showGrid(x=True, y=True, alpha=0.3)

            # Slightly lower than 75 because each waveform now also has a 24px header.
            # You can increase this if your window has enough vertical room.
            plt.setMinimumHeight(50)
            plt.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            plt.setStyleSheet(f"border: 1.5px solid {UM_ACCENT}; margin-bottom:2px;")
            plt.setLabel('left', "", color=UM_BLUE, size="10pt")

            # Bottom axis visibility will be managed dynamically so that the last
            # currently expanded plot shows the x-axis.
            plt.hideAxis('bottom')

            # Create small Y+ / Y– buttons
            y_in_btn = QPushButton("Y-IN")
            y_out_btn = QPushButton("Y-OUT")
            self.y_zoom_buttons.append((y_out_btn, y_in_btn))

            y_in_btn.setStyleSheet(
                f"font-size: 11pt; color:{UM_BLUE}; background: #FFCB05; "
                "min-width: 20px; min-height: 26px;"
            )
            y_out_btn.setStyleSheet(
                f"font-size: 11pt; color:{UM_BLUE}; background: #FFCB05; "
                "min-width: 20px; min-height: 20px;"
            )

            # Create small YU / YD buttons
            y_up_btn = QPushButton("Y+")
            y_down_btn = QPushButton("Y-")
            self.y_shift_buttons.append((y_down_btn, y_up_btn))

            y_up_btn.setStyleSheet(
                f"font-size: 11pt; color:{UM_BLUE}; background: #FFCB05; "
                "min-width: 20px; min-height: 26px;"
            )
            y_down_btn.setStyleSheet(
                f"font-size: 11pt; color:{UM_BLUE}; background: #FFCB05; "
                "min-width: 20px; min-height: 20px;"
            )

            # Existing Auto-Y scaling button
            auto_y_btn = QPushButton("AUTO-ON")
            auto_y_btn.setToolTip("Automatically rescales this lead when the visible time window changes.")
            auto_y_btn.setStyleSheet(
                f"font-size: 8pt; color:{UM_BLUE}; background: #FFCB05; "
                "min-width: 20px; min-height: 22px;"
            )

            self.auto_y_buttons.append(auto_y_btn)
            self.auto_y_enabled_by_user.append(True)

            # Stack buttons vertically
            btn_col = QVBoxLayout()
            btn_col.setSpacing(1)
            btn_col.setContentsMargins(0, 0, 0, 0)
            btn_col.addWidget(y_out_btn)
            btn_col.addWidget(y_in_btn)
            btn_col.addWidget(y_up_btn)
            btn_col.addWidget(y_down_btn)
            btn_col.addWidget(auto_y_btn)

            btn_widget = QWidget()
            btn_widget.setLayout(btn_col)
            btn_widget.setFixedWidth(44)
            # Increased slightly so AUTO-ON is not clipped.
            btn_widget.setMaximumWidth(52)
            btn_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            # Row widget: buttons on the left, plot fills rest
            plot_row = QWidget()
            row_layout = QHBoxLayout(plot_row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            row_layout.addWidget(btn_widget)
            row_layout.addWidget(plt, stretch=1)

            plot_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            # Wrap row in compact collapsible section.
            # The caret/label button will sit to the LEFT of btn_widget.
            section = CollapsibleWaveformSection(f"Waveform {lead_idx + 1}", plot_row)
            section.toggled.connect(lambda _expanded: self.handle_waveform_section_toggled())

            self.plots_layout.addWidget(section, stretch=1)

            self.waveform_sections.append(section)
            self.waveform_plots.append(plt)

            # Keeps collapsible title synced if callbacks later do:
            # self.waveform_plots[i].setLabel('left', real_lead_name, ...)
            self._patch_plot_set_label_to_update_section(plt, section)

            # Important:
            # If your callbacks later call plt.setLabel('left', real_lead_name, ...),
            # this keeps the collapsible header synchronized with that real lead name.
            self._patch_plot_set_label_to_update_section(plt, section)
            

        # Add the waveform container to the main layout.
        # Expanded plots share this area; collapsed plots shrink to just their headers.
        main_layout.addWidget(plots_container, stretch=7)

        # Make sure one visible plot has a bottom x-axis.
        self.update_waveform_section_stretches()
        self.update_visible_plot_axes()

        # Connect Shift buttons to handlers
        for idx_shift, (down_btn, up_btn) in enumerate(self.y_shift_buttons):
            down_btn.clicked.connect(lambda _, i=idx_shift: self.shift_y_scale(i, shift="down"))
            up_btn.clicked.connect(lambda _, i=idx_shift: self.shift_y_scale(i, shift="up"))

        # Connect Zoom buttons to handlers
        for idx_zoom, (out_btn, in_btn) in enumerate(self.y_zoom_buttons):
            out_btn.clicked.connect(lambda _, i=idx_zoom: self.adjust_y_scale(i, zoom="out"))
            in_btn.clicked.connect(lambda _, i=idx_zoom: self.adjust_y_scale(i, zoom="in"))

        # Connect auto Y button to handler
        for idx, auto_btn in enumerate(self.auto_y_buttons):
            auto_btn.clicked.connect(lambda _, i=idx: self.toggle_auto_y_for_plot(i))

        for i, plt in enumerate(self.waveform_plots):
            plt.scene().sigMouseClicked.connect(self.make_plot_click_handler(i))

        # ---- Synchronize all plots' x-axes ----
        for plt in self.waveform_plots[1:]:
            plt.setXLink(self.waveform_plots[0])

        # ---- Auto-Y debounce timer ----
        self.auto_y_timer = QTimer(self)
        self.auto_y_timer.setSingleShot(True)
        self.auto_y_timer.timeout.connect(self.autoscale_visible_y_all)

        # Trigger Auto-Y only when the X view changes.
        self.waveform_plots[0].getViewBox().sigXRangeChanged.connect(
            self.schedule_visible_y_autoscale
        )

        # --- Annotation Table ---
        self.ann_table = QTableWidget(0, 7)
        self.ann_table.setHorizontalHeaderLabels([
            "User", "Subject", "CPR", "Rhythm", "Signal Exp.", "Start", "End"
        ])
        self.ann_table.horizontalHeader().setStyleSheet(
            f"color:{UM_BLUE}; font-size:13px; background-color:{UM_MAIZE}; font-weight:bold;")
        table_header = self.ann_table.horizontalHeader()
        table_header.setSectionResizeMode(QHeaderView.Stretch)
        LIGHT_UM_ACCENT = "#e6f0fa" 
        self.ann_table.setStyleSheet(
            f"alternate-background-color: {LIGHT_UM_ACCENT}; background-color:#ffffff; color:{UM_BLUE};")
        self.ann_table.setAlternatingRowColors(True)
        self.ann_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ann_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        main_layout.addWidget(self.ann_table, stretch=1)

        # --- Set main window layout ---
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.addWidget(sidebar)
        container_layout.addWidget(main_panel, stretch=1)
        self.setCentralWidget(container)
        self.setStyleSheet("font-family: Segoe UI, Roboto, Arial, sans-serif; font-size:12px;")
        self.setContentsMargins(0, 0, 0, 0)

        main_layout.setSpacing(4)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # -- SIGNALS wiring - same as before
        self.set_folder_btn.clicked.connect(self.set_base_folder)
        self.load_subject_btn.clicked.connect(self.load_subject_data)
        self.load_annotation_btn.clicked.connect(self.handle_load_annotation)
        self.save_all_btn.clicked.connect(self.save_all_to_file)
        self.mark_btn.clicked.connect(self.handle_mark_clicked)
        self.finalize_waveform_btn.clicked.connect(self.handle_finalize_waveform_clicked)

        self.cpr_yes.toggled.connect(self.update_sidebar_ui)
        self.cpr_no.toggled.connect(self.update_sidebar_ui)
        self.cpr_U2D.toggled.connect(self.update_sidebar_ui)
        self.rhythm_dropdown.currentTextChanged.connect(self.update_sidebar_ui)
        # self.comment_box.textChanged.connect(self.update_sidebar_ui)
        self.rhythm_explanation.textChanged.connect(self.update_sidebar_ui)
        self.username_input.currentTextChanged.connect(self.update_sidebar_ui)
        # self.win_size.valueChanged.connect(self.update_waveform_and_mark)
        # self.x_scrollbar.valueChanged.connect(self.handle_x_scrollbar)

        # --- Autosave Annotation timer (every 2 minutes) ---
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave_annotations)
        self.autosave_timer.start(2*60*1000)

        # ---- UI update ----
        self.update_sidebar_ui()
        self.update_table_data()

        QTimer.singleShot(0, self.finalize_initial_waveform_layout)

    # --- HELPER FUNCTIONS ---

    def finalize_initial_waveform_layout(self):
        """
        Run after the window is actually visible.

        Qt/PyQtGraph can calculate tiny initial plot heights while widgets are still
        being constructed. A delayed layout refresh fixes the initial squished plots
        without needing the user to click a button.
        """
        if hasattr(self, "waveform_sections"):
            self.update_waveform_section_stretches()

        if hasattr(self, "waveform_plots"):
            self.update_visible_plot_axes()

            for plt in self.waveform_plots:
                plt.updateGeometry()
                plt.repaint()

        if hasattr(self, "plots_layout"):
            self.plots_layout.invalidate()
            self.plots_layout.activate()

        central = self.centralWidget()
        if central is not None and central.layout() is not None:
            central.layout().invalidate()
            central.layout().activate()

        self.updateGeometry()
        self.repaint()

    def showEvent(self, event):
        super().showEvent(event)

        if getattr(self, "_initial_waveform_layout_done", False):
            return

        self._initial_waveform_layout_done = True

        # Run once immediately after show, then again shortly after.
        # The second call helps PyQtGraph after it receives its final size.
        QTimer.singleShot(0, self.finalize_initial_waveform_layout)
        QTimer.singleShot(150, self.finalize_initial_waveform_layout)

    def handle_waveform_section_toggled(self):
        self.update_visible_plot_axes()
        self.update_waveform_section_stretches()

        # Let Qt finish show/hide first, then force relayout inside current window.
        QTimer.singleShot(0, self.refresh_waveform_layout)

    def update_waveform_section_stretches(self):
        """
        Expanded rows share available vertical space.
        Collapsed rows take only compact button height.
        """
        if not hasattr(self, "plots_layout"):
            return

        expanded_min_height = 65

        for i, section in enumerate(self.waveform_sections):
            if section.is_expanded():
                self.plots_layout.setStretch(i, 1)
                section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                section.setMinimumHeight(expanded_min_height)
                section.setMaximumHeight(16777215)
            else:
                self.plots_layout.setStretch(i, 0)

                collapsed_h = section.toggle_button.height() + 2
                section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                section.setMinimumHeight(collapsed_h)
                section.setMaximumHeight(collapsed_h)

        self.plots_layout.invalidate()
        self.plots_layout.activate()

    def refresh_waveform_layout(self):
        """
        Recompute layout without allowing the main window to grow off-screen.
        """
        if hasattr(self, "plots_layout"):
            self.plots_layout.activate()

        central = self.centralWidget()
        if central is not None and central.layout() is not None:
            central.layout().activate()

        self.updateGeometry()

        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()

        if screen is None:
            return

        available = screen.availableGeometry()
        current = self.geometry()

        new_width = min(current.width(), available.width())
        new_height = min(current.height(), available.height())

        new_x = current.x()
        new_y = current.y()

        if new_x < available.left():
            new_x = available.left()
        if new_y < available.top():
            new_y = available.top()
        if new_x + new_width > available.right():
            new_x = available.right() - new_width
        if new_y + new_height > available.bottom():
            new_y = available.bottom() - new_height

        self.setGeometry(new_x, new_y, new_width, new_height)

    def update_visible_plot_axes(self):
        """
        Show the bottom x-axis only on the last currently expanded waveform.
        """
        if not hasattr(self, "waveform_sections") or not hasattr(self, "waveform_plots"):
            return

        visible_indices = [
            i for i, section in enumerate(self.waveform_sections)
            if section.is_expanded()
        ]

        for plt in self.waveform_plots:
            plt.hideAxis('bottom')

        if visible_indices:
            self.waveform_plots[visible_indices[-1]].showAxis('bottom')


    def _patch_plot_set_label_to_update_section(self, plot_widget, section):
        """
        Keeps collapsible header text synced with plot left-axis labels.
        """
        original_set_label = plot_widget.setLabel

        def set_label_and_update_header(axis, text=None, units=None, unitPrefix=None, **kwargs):
            result = original_set_label(
                axis,
                text=text,
                units=units,
                unitPrefix=unitPrefix,
                **kwargs
            )

            if axis in ("left", "l") and text is not None and str(text).strip():
                section.set_title(str(text))

            return result

        plot_widget.setLabel = set_label_and_update_header


    def set_waveform_label(self, plot_idx, label):
        """
        Optional explicit helper if you want to update both the plot axis label
        and collapsible header yourself.
        """
        if plot_idx < 0 or plot_idx >= len(self.waveform_plots):
            return

        label = str(label).strip()

        self.waveform_plots[plot_idx].setLabel(
            'left',
            label,
            color=UM_BLUE,
            size="10pt"
        )

        if hasattr(self, "waveform_sections"):
            self.waveform_sections[plot_idx].set_title(label)

    def handle_waveform_section_toggled(self):
        self.update_visible_plot_axes()
        self.update_waveform_section_stretches()

        QTimer.singleShot(0, self.refresh_waveform_layout)


    def refresh_waveform_layout(self):
        """
        Force a layout recalculation inside the current window size.
        This helps prevent reopen/collapse actions from making the top-level
        window grow beyond the screen.
        """
        central = self.centralWidget()
        if central is not None and central.layout() is not None:
            central.layout().activate()

        self.updateGeometry()

        # Clamp the window back inside the available screen if Qt ever nudges it.
        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()

        if screen is None:
            return

        available = screen.availableGeometry()
        current = self.geometry()

        new_width = min(current.width(), available.width())
        new_height = min(current.height(), available.height())

        new_x = current.x()
        new_y = current.y()

        if new_x < available.left():
            new_x = available.left()
        if new_y < available.top():
            new_y = available.top()
        if new_x + new_width > available.right():
            new_x = available.right() - new_width
        if new_y + new_height > available.bottom():
            new_y = available.bottom() - new_height

        self.setGeometry(new_x, new_y, new_width, new_height)


    def get_cpr_val(self):
        if self.cpr_yes.isChecked():
            return "Yes"
        elif self.cpr_no.isChecked():
            return "No"
        elif self.cpr_U2D.isChecked():
            return "Unable to Determine"
        else:
            return None

    def clear_cpr(self):
        self.cpr_yes.setChecked(False)
        self.cpr_no.setChecked(False)
        self.cpr_U2D.setChecked(False)
        self.cpr_yes.setAutoExclusive(False)
        self.cpr_no.setAutoExclusive(False)
        self.cpr_U2D.setAutoExclusive(False)
        # self.cpr_yes.setAutoExclusive(True)


if __name__ == "__main__":
    import pyqtgraph.exporters
    app = QApplication(sys.argv)
    mw = MainApp()
    mw.show()
    sys.exit(app.exec_())