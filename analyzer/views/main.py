from PyQt5 import QtCore, QtWidgets
import matplotlib.pyplot as plt
from analyzer.views.overview import OverviewTab
from analyzer.views.performance import PerformanceTab
from analyzer.views.holdings import HoldingsTab
from analyzer.views.transactions import TransactionsTab
from analyzer.views.comparison import ComparisonTab
from analyzer.analysis_data import AnalysisData
from analyzer.exporter import PdfGenerator
from utils.log_utils import results_path
import os
import pandas as pd
import empyrical


class AnalyzerWindow(QtWidgets.QMainWindow):
    all_tabs_dict = {}
    updateSignal = QtCore.pyqtSignal(AnalysisData)

    def __init__(self, analysis_data, strategy_data, app):
        self.app = app
        self.analysis_data = analysis_data
        QtWidgets.QMainWindow.__init__(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(self.analysis_data.info_data['algo_name'])

        plt.style.use('seaborn-bright')
        self.setMinimumHeight(720)
        self.setMinimumWidth(960)

        overview_tab = OverviewTab(self, self.analysis_data)
        performance_tab = PerformanceTab(self, strategy_data, self.analysis_data)
        holdings_tab = HoldingsTab(self)
        transactions_tab = TransactionsTab(self)
        comparison_tab = ComparisonTab(self, self.analysis_data)

        self.all_tabs_dict[overview_tab.get_tab_name()] = overview_tab
        self.all_tabs_dict[performance_tab.get_tab_name()] = performance_tab
        self.all_tabs_dict[holdings_tab.get_tab_name()] = holdings_tab
        self.all_tabs_dict[transactions_tab.get_tab_name()] = transactions_tab
        self.all_tabs_dict[comparison_tab.get_tab_name()] = comparison_tab

        self.main_widget = QtWidgets.QWidget(self)

        layout = QtWidgets.QVBoxLayout(self.main_widget)
        layout.setSpacing(10)

        self.tab_widget = TabWidget(self)
        self.tab_widget.tabs.currentChanged.connect(self.tab_changed)
        layout.addWidget(self.tab_widget)

        export_menu = QtWidgets.QMenu('&Export', self)
        # generate pdf action
        self.generate_pdf_action = QtWidgets.QAction('&PDF Export', self)
        self.generate_pdf_action.triggered.connect(self.generate_pdf)
        self.generate_pdf_action.setShortcut(QtCore.Qt.CTRL + QtCore.Qt.Key_P)
        self.generate_pdf_action.setVisible(True)

        export_menu.addAction('&Holdings Report', self.export_holdings_data, QtCore.Qt.CTRL + QtCore.Qt.Key_H)
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

    def tab_changed(self):
        if self.analysis_data is not None:
            try:
                self.updateSignal.emit(self.analysis_data)
            except Exception as e:
                print(e)

    def generate_pdf(self):
        pdf_generator = PdfGenerator(tabs=self.all_tabs_dict, analysis_data=self.analysis_data, app=self.app)
        pdf_generator.generate()

    def export_transactions_data(self):
        export_file = os.path.join(results_path, 'transactions.csv')
        self.analysis_data.transactions_data.to_csv(export_file, index=False)

    def export_holdings_data(self):
        export_file = os.path.join(results_path, 'holdings.csv')
        self.analysis_data.holdings_data_historical['date'] = self.analysis_data.holdings_data_historical[
            ~self.analysis_data.holdings_data_historical.duplicated('date')]
        self.analysis_data.holdings_data_historical.fillna('', inplace=True)
        self.analysis_data.holdings_data_historical.to_csv(export_file, index=False)

    def export_comparisons_data(self):

        self.analysis_data.chart_data['alpha'] = empyrical.roll_alpha(self.analysis_data.chart_data.returns,
                                                                      self.analysis_data.chart_data.benchmark_returns,
                                                                      252) * 100
        self.analysis_data.chart_data['beta'] = empyrical.roll_beta(self.analysis_data.chart_data.returns,
                                                                    self.analysis_data.chart_data.benchmark_returns,
                                                                    252)
        self.analysis_data.chart_data['sharpe'] = empyrical.roll_sharpe_ratio(self.analysis_data.chart_data.returns,
                                                                              252)

        self.analysis_data.chart_data['benchmark_sharpe'] = empyrical.roll_sharpe_ratio(
            self.analysis_data.chart_data.benchmark_returns, 252)

        self.analysis_data.chart_data['std'] = self.analysis_data.chart_data.returns.rolling(252).std() * 100

        self.analysis_data.chart_data['benchmark_std'] = self.analysis_data.chart_data.benchmark_returns.rolling(
            252).std() * 100

        self.analysis_data.chart_data['outperformance'] = self.analysis_data.chart_data['returns'] - \
                                                          self.analysis_data.chart_data['benchmark_returns']

        self.analysis_data.chart_data.to_csv(os.path.join(results_path, 'comparison_daily.csv'))

        self.analysis_data.chart_data.index = pd.to_datetime(self.analysis_data.chart_data.index)

        idx = pd.date_range(self.analysis_data.chart_data.index[:1][0], self.analysis_data.chart_data.index[-1:][0])
        filled_data = self.analysis_data.chart_data.reindex(idx, method='ffill')
        returns_data = self.analysis_data.chart_data[['returns', 'benchmark_returns']]
        drawdown_data = self.analysis_data.chart_data[['drawdown', 'benchmark_drawdown']]

        yearly_comparison_returns = (returns_data + 1).resample('Y').prod() - 1
        yearly_comparison_returns['outperformance'] = yearly_comparison_returns['returns'] - \
                                                       yearly_comparison_returns['benchmark_returns']
        yearly_comparison_drawdown = drawdown_data.resample('Y').min()
        yearly_comparison_init = pd.concat([yearly_comparison_returns, yearly_comparison_drawdown],
                                           axis=1, join_axes=[yearly_comparison_returns.index]) * 100
        yearly_comparison_data = pd.concat([yearly_comparison_init, filled_data[['positions_count', 'alpha', 'beta',
                                                                                 'sharpe', 'benchmark_sharpe', 'std',
                                                                                 'benchmark_std']]],
                                           axis=1, join_axes=[yearly_comparison_init.index])

        monthly_comparison_returns = (returns_data + 1).resample('M').prod() - 1
        monthly_comparison_returns['annual_returns'] = pow((monthly_comparison_returns['returns']+1), 12) - 1
        monthly_comparison_returns['annual_bm_returns'] = pow((monthly_comparison_returns['benchmark_returns']+1), 12) - 1
        monthly_comparison_returns['outperformance'] = monthly_comparison_returns['returns'] -\
                                                       monthly_comparison_returns['benchmark_returns']
        monthly_comparison_drawdown = drawdown_data.resample('M').min()
        monthly_comparison_init = pd.concat([monthly_comparison_returns, monthly_comparison_drawdown],
                                           axis=1, join_axes=[monthly_comparison_returns.index]) * 100
        monthly_comparison_data = pd.concat([monthly_comparison_init, filled_data[['positions_count', 'alpha', 'beta',
                                                                                 'sharpe', 'benchmark_sharpe', 'std',
                                                                                 'benchmark_std']]],
                                           axis=1, join_axes=[monthly_comparison_init.index])

        weekly_comparison_returns = (returns_data + 1).resample('W').prod() - 1
        weekly_comparison_returns['annual_returns'] = pow((weekly_comparison_returns['returns']+1), 52) - 1
        weekly_comparison_returns['annual_bm_returns'] = pow((weekly_comparison_returns['benchmark_returns']+1), 52) - 1
        weekly_comparison_returns['outperformance'] = weekly_comparison_returns['returns'] - \
                                                       weekly_comparison_returns['benchmark_returns']
        weekly_comparison_drawdown = drawdown_data.resample('W').min()
        weekly_comparison_init = pd.concat([weekly_comparison_returns, weekly_comparison_drawdown],
                                           axis=1, join_axes=[weekly_comparison_returns.index]) * 100
        weekly_comparison_data = pd.concat([weekly_comparison_init, filled_data[['positions_count', 'alpha', 'beta',
                                                                                 'sharpe', 'benchmark_sharpe', 'std',
                                                                                 'benchmark_std']]],
                                           axis=1, join_axes=[weekly_comparison_init.index])

        yearly_comparison_data.to_csv(os.path.join(results_path, 'comparison_yearly.csv'))

        monthly_comparison_data.to_csv(os.path.join(results_path, 'comparison_monthly.csv'))

        weekly_comparison_data.to_csv(os.path.join(results_path, 'comparison_weekly.csv'))

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
