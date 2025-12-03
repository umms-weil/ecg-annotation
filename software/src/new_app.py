import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QRadioButton, QComboBox, QTextEdit, QSlider, QSpinBox, QTableWidget,
    QAbstractItemView, QButtonGroup, QHeaderView,
)
from PyQt5.QtCore import (Qt, QTimer)
import pyqtgraph as pg
from new_callbacks import AnnotationAppCallbacks
import pyqtgraph as pg

UM_MAIZE = "#FFCB05"
UM_BLUE = "#00274C"
UM_ACCENT = "#285680"
UM_WHITE = "#FFFFFF"


class MainApp(QMainWindow, AnnotationAppCallbacks):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Waveform Annotation App (U-M Theme)")
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(screen.width(), screen.height())
        # or, for a margin:
        self.resize(int(screen.width() * 0.95), int(screen.height() * 0.95))
        self.move(screen.left() + int(screen.width()*0.025), screen.top() + int(screen.height()*0.025))
        self.base_folder = ""
        self.data_store = {}
        self.annotations = []
        self.current_marker = None
        self.last_mark = 0.0
        self.n_mark_clicks = 0
        self.triggered_by_mark_btn = False

        font_css = f"font-size:13px; color:{UM_BLUE}; background:white; border:2px solid black;"

        # --- SIDEBAR Layout ---
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar.setMaximumWidth(355)
        sidebar.setStyleSheet(f"background-color: {UM_MAIZE}; border-right:2px solid {UM_BLUE};")

        header = QLabel("Annotations")
        header.setStyleSheet(f"font-size:21px; font-weight: bold; color: {UM_BLUE}; margin-bottom:8px;")
        sidebar_layout.addWidget(header)

        # User/subject input
        lab = QLabel("User Name:"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        sidebar_layout.addWidget(lab)
        self.username_input = QLineEdit(); self.username_input.setStyleSheet(font_css)
        sidebar_layout.addWidget(self.username_input)

        lab = QLabel("Subject:"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        sidebar_layout.addWidget(lab)
        self.subject_dropdown = QComboBox(); self.subject_dropdown.setStyleSheet(font_css)
        sidebar_layout.addWidget(self.subject_dropdown)

        row = QHBoxLayout()
        self.load_subject_btn = QPushButton("Load Subject");
        self.load_subject_btn.setStyleSheet(f"background:{UM_BLUE}; color:{UM_MAIZE}; font-size:13px; font-weight:bold; border-radius:4px;")
        # self.plot_btn = QPushButton("Plot")
        row.addWidget(self.load_subject_btn); 
        # row.addWidget(self.plot_btn)
        sidebar_layout.addLayout(row)

        lab = QLabel("Is this segment Interpretable?"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        sidebar_layout.addWidget(lab)

        # self.radio_interp_yes = QRadioButton("Yes"); self.radio_interp_no = QRadioButton("No")
        # self.radio_interp_yes.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        # self.radio_interp_no.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        # interp_row = QHBoxLayout(); interp_row.addWidget(self.radio_interp_yes); interp_row.addWidget(self.radio_interp_no)
        # sidebar_layout.addLayout(interp_row)
        # Exclusive block-style radio for Interpretable
        self.radio_interp_yes = QPushButton('YES')
        self.radio_interp_no = QPushButton('NO')
        self.radio_interp_yes.setCheckable(True)
        self.radio_interp_no.setCheckable(True)
        # Exclusive group:
        self.interp_btn_group = QButtonGroup()
        self.interp_btn_group.addButton(self.radio_interp_yes)
        self.interp_btn_group.addButton(self.radio_interp_no)
        self.interp_btn_group.setExclusive(True)

        # Block styling
        block_css = """
        QPushButton {
            background-color: #FFCB05;
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

        self.radio_interp_yes.setStyleSheet(block_css)
        self.radio_interp_no.setStyleSheet(block_css)

        # Add to layout
        interp_row = QHBoxLayout()
        interp_row.addWidget(self.radio_interp_yes)
        interp_row.addWidget(self.radio_interp_no)
        sidebar_layout.addLayout(interp_row)

        lab = QLabel("Comment/Explanation"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        sidebar_layout.addWidget(lab)
        self.comment_box = QTextEdit()
        self.comment_box.setMaximumHeight(40)  
        self.comment_box.setStyleSheet(font_css)
        sidebar_layout.addWidget(self.comment_box)

        lab = QLabel("Is this Cardiac Arrest?"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        sidebar_layout.addWidget(lab)

        # self.cardiac_arrest_yes = QRadioButton("Yes"); self.cardiac_arrest_no = QRadioButton("No")
        # self.cardiac_arrest_yes.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        # self.cardiac_arrest_no.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        # ca_row = QHBoxLayout(); ca_row.addWidget(self.cardiac_arrest_yes); ca_row.addWidget(self.cardiac_arrest_no)
        # sidebar_layout.addLayout(ca_row)
        self.cardiac_arrest_yes = QPushButton('YES')
        self.cardiac_arrest_no = QPushButton('NO')
        self.cardiac_arrest_yes.setCheckable(True)
        self.cardiac_arrest_no.setCheckable(True)
        self.ca_btn_group = QButtonGroup()
        self.ca_btn_group.addButton(self.cardiac_arrest_yes)
        self.ca_btn_group.addButton(self.cardiac_arrest_no)
        self.ca_btn_group.setExclusive(True)
        self.cardiac_arrest_yes.setStyleSheet(block_css)
        self.cardiac_arrest_no.setStyleSheet(block_css)
        ca_row = QHBoxLayout()
        ca_row.addWidget(self.cardiac_arrest_yes)
        ca_row.addWidget(self.cardiac_arrest_no)
        sidebar_layout.addLayout(ca_row)

        lab = QLabel("Is this CPR?"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        sidebar_layout.addWidget(lab)

        # self.cpr_yes = QRadioButton("Yes"); self.cpr_no = QRadioButton("No")
        # self.cpr_yes.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        # self.cpr_no.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        # cpr_row = QHBoxLayout(); cpr_row.addWidget(self.cpr_yes); cpr_row.addWidget(self.cpr_no)
        # sidebar_layout.addLayout(cpr_row)
        self.cpr_yes = QPushButton('YES')
        self.cpr_no = QPushButton('NO')
        self.cpr_yes.setCheckable(True)
        self.cpr_no.setCheckable(True)
        self.cpr_btn_group = QButtonGroup()
        self.cpr_btn_group.addButton(self.cpr_yes)
        self.cpr_btn_group.addButton(self.cpr_no)
        self.cpr_btn_group.setExclusive(True)
        self.cpr_yes.setStyleSheet(block_css)
        self.cpr_no.setStyleSheet(block_css)
        cpr_row = QHBoxLayout()
        cpr_row.addWidget(self.cpr_yes)
        cpr_row.addWidget(self.cpr_no)
        sidebar_layout.addLayout(cpr_row)


        lab = QLabel("Rhythm Type"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        sidebar_layout.addWidget(lab)
        self.rhythm_dropdown = QComboBox(); self.rhythm_dropdown.setStyleSheet(font_css)
        self.rhythm_dropdown.addItems([
            "Normal Heart Rhythm", "Sinus tachycardia", "Bradycardia",
            "Supraventricular tachycardia", "Atrial Flutter", "Atrial Fibrillation",
            "Ventricular Tachycardia", "Ventricular Fibrillation",
            "Atrial Pacing Rhythm", "Ventricular Pacing Rhythm", "Idioventricular Rhythm",
            "Unable to Determine", "Other"
        ])
        sidebar_layout.addWidget(self.rhythm_dropdown)

        lab = QLabel("Rhythm Explanation"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        sidebar_layout.addWidget(lab)

        self.rhythm_explanation = QTextEdit()
        self.rhythm_explanation.setMaximumHeight(40)  
        self.rhythm_explanation.setStyleSheet(font_css)
        sidebar_layout.addWidget(self.rhythm_explanation)

        # lab = QLabel("Navigation step size (seconds):"); lab.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        # sidebar_layout.addWidget(lab)
        # self.nav_step_size = QSpinBox(); self.nav_step_size.setMinimum(1); self.nav_step_size.setValue(1)
        # self.nav_step_size.setStyleSheet(font_css)
        # sidebar_layout.addWidget(self.nav_step_size)
        # navrow = QHBoxLayout()
        # self.prev_btn = QPushButton("←"); self.next_btn = QPushButton("→")
        # for btn in [self.prev_btn, self.next_btn]:
        #     btn.setStyleSheet(f"background:{UM_BLUE}; color:{UM_MAIZE}; font-size:13px; font-weight:bold; border-radius:4px;")
        # navrow.addWidget(self.prev_btn); navrow.addWidget(self.next_btn)
        # sidebar_layout.addLayout(navrow)

        self.mark_btn = QPushButton("Mark"); self.mark_btn.setStyleSheet(
            f"background:{UM_BLUE}; color:{UM_MAIZE}; font-size:13px; font-weight:bold; border-radius:4px;")
        sidebar_layout.addWidget(self.mark_btn)
        self.mark_warning = QLabel(""); sidebar_layout.addWidget(self.mark_warning); self.mark_warning.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        # saved_ann = sidebar_layout.addWidget(QLabel("Saved Annotations:")); saved_ann.setStyleSheet(f"font-size:13px; color:{UM_BLUE};")
        self.save_all_btn = QPushButton("Save All Annotations"); self.save_all_btn.setStyleSheet(f"background:{UM_BLUE}; color:{UM_MAIZE}; font-size:13px; font-weight:bold; border-radius:4px;")
        sidebar_layout.addWidget(self.save_all_btn)
        self.save_message = QLabel(""); sidebar_layout.addWidget(self.save_message)

        self.interp_group = QButtonGroup()
        self.interp_group.addButton(self.radio_interp_yes)
        self.interp_group.addButton(self.radio_interp_no)
        self.interp_group.setExclusive(True)

        self.ca_group = QButtonGroup()
        self.ca_group.addButton(self.cardiac_arrest_yes)
        self.ca_group.addButton(self.cardiac_arrest_no)
        self.ca_group.setExclusive(True)

        self.cpr_group = QButtonGroup()
        self.cpr_group.addButton(self.cpr_yes)
        self.cpr_group.addButton(self.cpr_no)
        self.cpr_group.setExclusive(True)

        sidebar_layout.setSpacing(4)
        sidebar_layout.setContentsMargins(4, 2, 4, 2)

        # --- MAIN PANEL Layout ---
        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_panel.setStyleSheet(f"background-color: {UM_WHITE}; border:none;")

        folderrow = QHBoxLayout()
        folderlab = QLabel("Select Base Data Folder:"); folderlab.setStyleSheet(f"font-size:13px; color:{UM_ACCENT}; font-weight: bold;")
        folderrow.addWidget(folderlab)
        self.folder_input = QLineEdit(); self.folder_input.setStyleSheet(font_css)
        folderrow.addWidget(self.folder_input)
        self.set_folder_btn = QPushButton("Set Folder"); self.set_folder_btn.setStyleSheet(f"background:{UM_BLUE}; color:{UM_MAIZE}; font-size:13px; font-weight:bold; border-radius:1px;")
        folderrow.addWidget(self.set_folder_btn)
        main_layout.addLayout(folderrow)

        self.folder_status = QLabel("")
        self.folder_status.setStyleSheet(f"font-size:12px; color:{UM_BLUE}; margin-top:0px; margin-bottom:0px; font-weight:bold;")
        main_layout.addWidget(self.folder_status)

        # winrow = QHBoxLayout()
        # winlab = QLabel("Waveform view window (seconds):"); winlab.setStyleSheet(f"font-size:13px; color:{UM_BLUE}; font-weight: bold;")
        # winrow.addWidget(winlab)
        # self.win_size = QSpinBox(); self.win_size.setMinimum(1); self.win_size.setMaximum(10000); self.win_size.setValue(10)
        # self.win_size.setStyleSheet(font_css)
        # winrow.addWidget(self.win_size)
        # main_layout.addLayout(winrow)

        # self.x_scrollbar = QSlider(Qt.Horizontal); self.x_scrollbar.setMinimum(0); self.x_scrollbar.setMaximum(100)
        # self.x_scrollbar.setStyleSheet(f"background:{UM_ACCENT};")
        # main_layout.addWidget(self.x_scrollbar)

        self.waveform_plots = []
        self.y_zoom_buttons = []

        for lead_idx in range(7):
            plt = pg.PlotWidget()
            plt.setBackground(UM_WHITE)
            plt.showGrid(x=True, y=True, alpha=0.3)
            plt.setMinimumHeight(75)
            plt.setStyleSheet(f"border: 1.5px solid {UM_ACCENT}; margin-bottom:2px;")
            plt.setLabel('left', f"Lead {lead_idx+1}/7", color=UM_BLUE, size="10pt")
            if lead_idx != 6:
                plt.hideAxis('bottom')

            # Create small Y+ / Y– buttons
            y_up_btn = QPushButton("Y-IN")
            y_down_btn = QPushButton("Y-OUT")
            self.y_zoom_buttons.append((y_down_btn, y_up_btn))
            # Smaller styling
            y_up_btn.setStyleSheet(f"font-size: 11pt ;color:{UM_BLUE}; background: #FFCB05; min-width: 20px; min-height: 26px;")
            y_down_btn.setStyleSheet(f"font-size: 11pt; color:{UM_BLUE}; background: #FFCB05; min-width: 20px; min-height: 20px;")

            # Stack buttons vertically
            btn_col = QVBoxLayout()
            btn_col.setSpacing(1)
            btn_col.setContentsMargins(0,0,0,0)
            btn_col.addWidget(y_up_btn)
            btn_col.addWidget(y_down_btn)

            btn_widget = QWidget()
            btn_widget.setLayout(btn_col)
            btn_widget.setMaximumWidth(36)

            # Row widget: buttons on the left, plot fills rest
            plot_row = QWidget()
            row_layout = QHBoxLayout(plot_row)
            row_layout.setContentsMargins(0,0,0,0)
            row_layout.setSpacing(2)
            row_layout.addWidget(btn_widget)
            row_layout.addWidget(plt)

            main_layout.addWidget(plot_row)
            self.waveform_plots.append(plt)

        # Connect buttons to handlers
        for idx, (down_btn, up_btn) in enumerate(self.y_zoom_buttons):
            down_btn.clicked.connect(lambda _, i=idx: self.adjust_y_scale(i, zoom="down"))
            up_btn.clicked.connect(lambda _, i=idx: self.adjust_y_scale(i, zoom="up"))
        
        for i, plt in enumerate(self.waveform_plots):
            plt.scene().sigMouseClicked.connect(self.make_plot_click_handler(i))

        # ---- Synchronize all plots' x-axes ----
        for plt in self.waveform_plots[1:]:
            plt.setXLink(self.waveform_plots[0])

        self.ann_table = QTableWidget(0, 10)
        self.ann_table.setHorizontalHeaderLabels([
            "User", "Subject", "Interpretable", "NonInterp Exp.", "Cardiac Arrest", "CPR", "Rhythm",
             "Rhythm Exp.", "Start", "End"
        ])
        self.ann_table.horizontalHeader().setStyleSheet(
            f"color:{UM_BLUE}; font-size:13px; background-color:{UM_MAIZE}; font-weight:bold;")
        table_header = self.ann_table.horizontalHeader()
        table_header.setSectionResizeMode(QHeaderView.Stretch)
        LIGHT_UM_ACCENT = "#e6f0fa"  # or your preferred light color
        self.ann_table.setStyleSheet(
            f"alternate-background-color: {LIGHT_UM_ACCENT}; background-color:#ffffff; color:{UM_BLUE};")
        self.ann_table.setAlternatingRowColors(True)
        self.ann_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ann_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        main_layout.addWidget(self.ann_table, stretch=1)

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
        self.save_all_btn.clicked.connect(self.save_all_to_file)
        self.mark_btn.clicked.connect(self.handle_mark_clicked)

        self.radio_interp_yes.toggled.connect(self.update_sidebar_ui)
        self.radio_interp_no.toggled.connect(self.update_sidebar_ui)
        self.cardiac_arrest_yes.toggled.connect(self.update_sidebar_ui)
        self.cardiac_arrest_no.toggled.connect(self.update_sidebar_ui)
        self.cpr_yes.toggled.connect(self.update_sidebar_ui)
        self.cpr_no.toggled.connect(self.update_sidebar_ui)
        self.rhythm_dropdown.currentTextChanged.connect(self.update_sidebar_ui)
        self.comment_box.textChanged.connect(self.update_sidebar_ui)
        self.rhythm_explanation.textChanged.connect(self.update_sidebar_ui)
        self.username_input.textChanged.connect(self.update_sidebar_ui)
        # self.win_size.valueChanged.connect(self.update_waveform_and_mark)
        # self.x_scrollbar.valueChanged.connect(self.handle_x_scrollbar)

        # Autosave
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave_annotations)
        self.autosave_timer.start(2*60*1000)

        self.update_sidebar_ui()
        self.update_table_data()

    # ---- Helper functions for your callbacks.py ----
    def get_interp_val(self):
        if self.radio_interp_yes.isChecked():
            return "Yes"
        elif self.radio_interp_no.isChecked():
            return "No"
        else:
            return None

    def get_ca_val(self):
        if self.cardiac_arrest_yes.isChecked():
            return "Yes"
        elif self.cardiac_arrest_no.isChecked():
            return "No"
        else:
            return None

    def get_cpr_val(self):
        if self.cpr_yes.isChecked():
            return "Yes"
        elif self.cpr_no.isChecked():
            return "No"
        else:
            return None

    def clear_cardiac_arrest(self):
        self.cardiac_arrest_yes.setAutoExclusive(False)
        self.cardiac_arrest_yes.setChecked(False)
        self.cardiac_arrest_no.setChecked(False)
        self.cardiac_arrest_yes.setAutoExclusive(True)

    def clear_cpr(self):
        self.cpr_yes.setAutoExclusive(False)
        self.cpr_yes.setChecked(False)
        self.cpr_no.setChecked(False)
        self.cpr_yes.setAutoExclusive(True)


    # def handle_mark_clicked(self):
    #     self.triggered_by_mark_btn = True
    #     self.n_mark_clicks += 1
    #     self.update_waveform_and_mark()
    #     self.triggered_by_mark_btn = False
    #     # Move the start up: next mark starts here!
    #     self.last_mark = self.current_marker
    #     self.current_marker = None
    #     self.update_sidebar_ui()

if __name__ == "__main__":
    import pyqtgraph.exporters
    app = QApplication(sys.argv)
    mw = MainApp()
    mw.show()
    sys.exit(app.exec_())