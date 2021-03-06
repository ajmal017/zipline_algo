from analyzer.views.analysistab import AnalysisTab
from PyQt5 import QtWidgets, QtGui, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib import gridspec
import empyrical
import pandas as pd
from utils.log_utils import results_path
import os
import copy


class PerformanceTab(AnalysisTab):
    def __init__(self, parent, strategy_data, analysis_data):
        super(QtWidgets.QWidget, self).__init__(parent)
        self.plotter = Plotter(self)
        self.analysis_data = analysis_data

        self.main_widget = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(self.main_widget)
        layout.setSpacing(10)

        start_date = strategy_data.get('start')
        end_date = strategy_data.get('end')

        self.dateWindow = QtWidgets.QWidget()
        self.start_date_widget = DateWidget(self)
        self.start_date_widget.setDate(start_date)
        self.start_date_widget.setDateRange(start_date, end_date)
        self.start_date_widget.setEnabled(False)
        self.end_date_widget = DateWidget(self)
        self.end_date_widget.setDate(end_date)
        self.end_date_widget.setDateRange(start_date, end_date)
        self.end_date_widget.setEnabled(False)

        self.hbox = QtWidgets.QHBoxLayout()
        start_label = QtWidgets.QLabel("<font color='#666666'><strong>Start Date:</font></strong>", self)
        start_label.setFixedWidth(80)
        self.hbox.addWidget(start_label)
        self.hbox.addWidget(self.start_date_widget)
        self.hbox.insertSpacing(2, 60)
        end_label = QtWidgets.QLabel("<font color='#666666'><strong>End Date:</font></strong>", self)
        end_label.setFixedWidth(70)
        self.hbox.addWidget(end_label)
        self.hbox.addWidget(self.end_date_widget)
        self.hbox.insertSpacing(5, 100)

        self.date_range_go_button = QtWidgets.QPushButton("Go")
        self.date_range_go_button.setFixedWidth(60)
        self.date_range_go_button.setEnabled(False)
        self.date_range_go_button.clicked.connect(self.date_range_change)
        self.hbox.addWidget(self.date_range_go_button)

        self.dateWindow.setLayout(self.hbox)
        layout.addWidget(self.dateWindow)

        firstgroup_widget = QtWidgets.QWidget()
        firstgroup_layout = QtWidgets.QVBoxLayout(firstgroup_widget)
        firstgroup_layout.addWidget(self.plotter)
        firstgroup_layout.setSpacing(0)
        firstgroup_layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(firstgroup_widget)
        self.setLayout(layout)

    def contextMenuEvent(self, a0: QtGui.QContextMenuEvent):
        contextManu = QtWidgets.QMenu(self)

        returns_action = contextManu.addAction("Returns")
        drawdown_action = contextManu.addAction("Drawdown")
        alpha_action = contextManu.addAction('Alpha')
        beta_action = contextManu.addAction('Beta')
        sharpe_action = contextManu.addAction('Sharpe')
        std_dev = contextManu.addAction('Std Dev')
        positions = contextManu.addAction('Positions')

        action = contextManu.exec_(self.mapToGlobal(a0.pos()))

        if action == returns_action:
            self.plotter.plot_type = 'returns'
        elif action == drawdown_action:
            self.plotter.plot_type = 'drawdown'
        elif action == alpha_action:
            self.plotter.plot_type = 'alpha'
        elif action == beta_action:
            self.plotter.plot_type = 'beta'
        elif action == sharpe_action:
            self.plotter.plot_type = 'sharpe'
        elif action == std_dev:
            self.plotter.plot_type = 'std_dev'
        elif action == positions:
            self.plotter.plot_type = 'positions'

        self.update_plot(self.analysis_data)

    def get_tab_name(self):
        return 'Performance'

    def get_tab_description(self):
        return 'some description'

    def date_range_change(self):
        start_date = self.start_date_widget.date()
        end_date = self.end_date_widget.date()
        filtered_data = copy.deepcopy(self.analysis_data)
        filtered_data.chart_data = filtered_data.chart_data[start_date: end_date]
        self.plotter.plot(filtered_data)

    def enable_date_range_selection(self):
        self.date_range_go_button.setEnabled(True)

    def update_plot(self, analysis_data):
        self.analysis_data = analysis_data
        self.plotter.plot(analysis_data)
        if analysis_data.info_data['date_range_go_button']:
            self.date_range_go_button.setEnabled(True)
            self.start_date_widget.setEnabled(True)
            self.end_date_widget.setEnabled(True)

    def generate_report(self):
        report = {}
        graph_list = ['returns', 'drawdown', 'alpha', 'beta', 'sharpe', 'std_dev', 'positions']

        for graph in graph_list:
            # Load the corresponding graph on UI
            self.plotter.plot_type = graph
            self.update_plot(self.analysis_data)
            # Define image path
            img_path = os.path.join(results_path, graph+'.png')
            # Remove image if already exist
            if os.path.exists(img_path):
                os.remove(img_path)
            # create plotter image file
            self.plotter.print_figure(img_path)
            # define URL
            img_url = QtCore.QUrl.fromLocalFile(results_path).toString() + "/" + graph + ".png"
            report[graph] = img_url

        return report


class Plotter(FigureCanvas):
    def __init__(self, masterWindow):
        self.fig = Figure(figsize=(10, 7))
        gs = gridspec.GridSpec(1, 1)
        self.returns_ax = self.fig.add_subplot(gs[0, 0], xticks=[], yticks=[])
        FigureCanvas.__init__(self, self.fig)
        self.setParent(masterWindow)
        self.plot_type = 'returns'
        FigureCanvas.setSizePolicy(self, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        FigureCanvas.updateGeometry(self)

    def plot(self, analysis_data=None):
        if analysis_data is not None:
            self.analysis_data = analysis_data

        if self.analysis_data is None or self.analysis_data.chart_data is None:
            return

        self.returns_ax.cla()

        if self.plot_type == 'returns':
            self.plot_returns()
        elif self.plot_type == 'drawdown':
            self.plot_drawdown()
        elif self.plot_type == 'alpha':
            self.plot_alpha()
        elif self.plot_type == 'beta':
            self.plot_beta()
        elif self.plot_type == 'sharpe':
            self.plot_sharpe()
        elif self.plot_type == 'std_dev':
            self.plot_std_dev()
        elif self.plot_type == 'positions':
            self.plot_positions()

        self.returns_ax.grid(True)

        self.draw()

    def plot_returns(self):
        self.portfolio_total_returns = empyrical.cum_returns(self.analysis_data.chart_data.returns) * 100
        self.benchmark_total_returns = empyrical.cum_returns(self.analysis_data.chart_data.benchmark_returns) * 100

        self.returns_ax.plot(self.portfolio_total_returns)
        self.returns_ax.plot(self.benchmark_total_returns)

        self.returns_ax.legend(['Strategy', 'SPY'], loc='upper left')
        self.returns_ax.set_ylabel('Return')

    def plot_drawdown(self):
        self.returns_ax.set_ylabel('Drawdown')
        self.returns_ax.yaxis.tick_right()

        self.plotdata = pd.concat([(100 * self.analysis_data.chart_data.drawdown), (100 * self.analysis_data.chart_data.benchmark_drawdown)], axis=1)

        self.returns_ax.plot(self.plotdata.drawdown)
        self.returns_ax.plot(self.plotdata.benchmark_drawdown)
        self.returns_ax.legend(['Strategy', 'SPY'], loc='upper left')

    def plot_alpha(self):
        self.returns_ax.set_ylabel('Alpha')
        self.returns_ax.yaxis.tick_right()
        series = empyrical.roll_alpha(self.analysis_data.chart_data.returns,
                                      self.analysis_data.chart_data.benchmark_returns,
                                      252) * 100

        if series is not None and series.shape[0] > 0:
            series = series.reindex(self.analysis_data.chart_data.index)
            self.plotdata = pd.DataFrame(series)
            self.returns_ax.set_ylim(min(0, series.min()), max(0, series.max()))
            self.returns_ax.plot(series)

            self.returns_ax.legend(['Strategy'], loc='upper left')

    def plot_beta(self):
        self.returns_ax.set_ylabel('Beta')
        self.returns_ax.yaxis.tick_right()
        series = empyrical.roll_beta(self.analysis_data.chart_data.returns,
                                      self.analysis_data.chart_data.benchmark_returns,
                                     252)

        if series is not None and series.shape[0] > 0:
            series = series.reindex(self.analysis_data.chart_data.index)
            self.plotdata = pd.DataFrame(series)
            self.returns_ax.set_ylim(min(0, series.min()), max(0, series.max()))
            self.returns_ax.plot(series)

            self.returns_ax.legend(['Strategy'], loc='upper left')

    def plot_sharpe(self):
        self.returns_ax.set_ylabel('Sharpe')
        self.returns_ax.yaxis.tick_right()

        series = empyrical.roll_sharpe_ratio(self.analysis_data.chart_data.returns, 252)
        series = series.reindex(self.analysis_data.chart_data.index)
        self.plotdata = pd.DataFrame(series)

        self.returns_ax.set_ylim(min(0, series.min()), max(0, series.max()))
        self.returns_ax.plot(series)

        self.returns_ax.legend(['Strategy'], loc='upper left')

    def plot_std_dev(self):
        self.returns_ax.set_ylabel('Std Dev')
        self.returns_ax.yaxis.tick_right()

        series = self.analysis_data.chart_data.returns.rolling(252).std()
        series = 100 * series.reindex(self.analysis_data.chart_data.index)
        self.plotdata = pd.DataFrame(series)

        self.returns_ax.set_ylim(min(0, series.min()), max(0, series.max()))
        self.returns_ax.plot(series)

        self.returns_ax.legend(['Strategy'], loc='upper left')

    def plot_positions(self):
        self.returns_ax.set_ylabel('Positions')
        self.returns_ax.yaxis.tick_right()

        series = self.analysis_data.chart_data.positions_count
        self.plotdata = pd.DataFrame(series)

        self.returns_ax.set_ylim(min(0, series.min()-1), max(0, series.max()+1))
        self.returns_ax.plot(series)

        self.returns_ax.legend(['Strategy'], loc='upper left')


class DateWidget(QtWidgets.QDateEdit):
    """docstring for DateWidget"""
    def __init__(self, parent=None):
        super(DateWidget, self).__init__()
        self.parent = parent

        self.setCalendarPopup(True)
        self.setDisplayFormat('dd/MM/yyyy')
        self.cal = self.calendarWidget()
        self.cal.setFirstDayOfWeek(QtCore.Qt.Monday)
        self.cal.setHorizontalHeaderFormat(QtWidgets.QCalendarWidget.SingleLetterDayNames)
        self.cal.setVerticalHeaderFormat(QtWidgets.QCalendarWidget.NoVerticalHeader)
        self.cal.setGridVisible(True)
