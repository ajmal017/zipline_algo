from PyQt5 import QtCore, QtWidgets
import matplotlib.pyplot as plt
from analyzer.views.overview import OverviewTab
from analyzer.views.performance import PerformanceTab
from analyzer.views.holdings import HoldingsTab
from analyzer.views.transactions import TransactionsTab
from analyzer.views.comparison import ComparisonTab
from analyzer.analysis_data import AnalysisData
from analyzer.exporter import PdfGenerator
import os
from utils.log_utils import results_path
import os


class AnalyzerWindow(QtWidgets.QMainWindow):
    all_tabs_dict = {}
    updateSignal = QtCore.pyqtSignal(AnalysisData)

    def __init__(self, analysis_data, app):
        self.app = app
        self.analysis_data = analysis_data
        QtWidgets.QMainWindow.__init__(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(self.analysis_data.info_data['algo_name'])

        plt.style.use('seaborn-bright')
        self.setMinimumHeight(720)
        self.setMinimumWidth(960)

        overview_tab = OverviewTab(self, self.analysis_data)
        performance_tab = PerformanceTab(self, self.analysis_data)
        holdings_tab = HoldingsTab(self)
        transactions_tab = TransactionsTab(self)
        comparison_tab = ComparisonTab(self)

        self.all_tabs_dict[overview_tab.get_tab_name()] = overview_tab
        self.all_tabs_dict[performance_tab.get_tab_name()] = performance_tab
        self.all_tabs_dict[holdings_tab.get_tab_name()] = holdings_tab
        self.all_tabs_dict[transactions_tab.get_tab_name()] = transactions_tab
        self.all_tabs_dict[comparison_tab.get_tab_name()] = comparison_tab

        self.main_widget = QtWidgets.QWidget(self)

        layout = QtWidgets.QVBoxLayout(self.main_widget)
        layout.setSpacing(10)

        self.tab_widget = TabWidget(self)

        layout.addWidget(self.tab_widget)

        export_menu = QtWidgets.QMenu('&Export', self)
        # generate pdf action
        self.generate_pdf_action = QtWidgets.QAction('&PDF Export', self)
        self.generate_pdf_action.triggered.connect(self.generate_pdf)
        self.generate_pdf_action.setShortcut(QtCore.Qt.CTRL + QtCore.Qt.Key_P)
        self.generate_pdf_action.setVisible(True)

        export_menu.addAction('&Transactions Report', self.export_transactions_data, QtCore.Qt.CTRL + QtCore.Qt.Key_T)
        export_menu.addAction('&Comparison Report', self.export_comparisons_data, QtCore.Qt.CTRL + QtCore.Qt.Key_C)
        export_menu.addSeparator()
        export_menu.addAction(self.generate_pdf_action)

        self.menuBar().addMenu(export_menu)

        self.main_widget.setFocus()
        self.setCentralWidget(self.main_widget)

        self.add_tab(overview_tab.get_tab_name())
        self.add_tab(performance_tab.get_tab_name())
        self.add_tab(holdings_tab.get_tab_name())
        self.add_tab(transactions_tab.get_tab_name())
        self.add_tab(comparison_tab.get_tab_name())

        self.tab_widget.tabs.setCurrentIndex(0)

        # connect to event
        self.updateSignal.connect(self.update_plot)

    def generate_pdf(self):
        pdf_generator = PdfGenerator(tabs=self.all_tabs_dict, analysis_data=self.analysis_data, app=self.app)
        pdf_generator.generate()

    def export_transactions_data(self):
        export_file = os.path.join(results_path, 'transactions.csv')
        self.analysis_data.transactions_data.to_csv(export_file, index=False)

    def export_comparisons_data(self):
        export_file = os.path.join(results_path, 'comparison.csv')
        self.analysis_data.comparison_data.to_csv(export_file, index=False)

    @QtCore.pyqtSlot(AnalysisData)
    def update_plot(self, analysis_data):
        if analysis_data is not None:
            self.analysis_data = analysis_data

        try:
            self.tab_widget.tabs.currentWidget().update_plot(self.analysis_data)
        except Exception as e:
            print(e)

    def add_tab(self, name):
        tab_object = self.all_tabs_dict[name]
        if tab_object is not None:
            self.tab_widget.tabs.addTab(tab_object, name)


class TabWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super(QtWidgets.QWidget, self).__init__(parent)
        self.layout = QtWidgets.QVBoxLayout(self)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.setAcceptDrops(False)

        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
