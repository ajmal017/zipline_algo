import os, sys, inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

import pandas as pd
from strategy import Strategy
from alphacompiler.data.sf1_fundamentals import Fundamentals
from alphacompiler.data.NASDAQ import NASDAQSectorCodes, NASDAQIPO
from zipline.pipeline import Pipeline
import numpy as np
from zipline.utils.events import date_rules
from zipline.api import (attach_pipeline, pipeline_output, schedule_function)
from utils.order_controller import (order_target_percent, order_target)
from utils.log_utils import setup_logging
from utils.algo_utils import get_run_mode
from virtual_broker_sample_ltlr_algo.vb_sample_config import config
import argparse
import pickle
import time


# stop loss non addition limit set to 15 days
stop_loss_prevention_days = 15

# max exposure per sector set to 15%
max_sector_exposure = 0.21

logger = setup_logging("virtual_broker_sample")


def initialize(context):
    attach_pipeline(make_pipeline(), 'my_pipeline')
    # context.broker = BacktestBroker()
    context.stop_loss_list = pd.Series()
    context.sector_wise_exposure = dict()
    context.sector_stocks = {}
    context.turnover_count = 0

    if context.live_trading is False:
        schedule_function(
            rebalance,
            date_rule=date_rules.month_start()
        )


def before_trading_start(context, data):
    # cash = context.broker.get_cash(context)
    context.pipeline_data = pipeline_output('my_pipeline')
    if context.live_trading is True:
        try:
            with open('stop_loss_list.pickle', 'rb') as handle:
                context.stop_loss_list = pickle.load(handle)
        except:
            context.stop_loss_list = pd.Series()
        try:
            with open('sector_list.pickle', 'rb') as handle:
                context.sector_stocks = pickle.load(handle)
        except:
            context.sector_stocks = {}
        # schedule_function(rebalance, date_rule=date_rules.every_day())
        # schedule_function(
        #     rebalance,
        #     date_rule=date_rules.month_start()
        # )
    context.logic_run_done = False


def after_trading_end(context, data):
    if context.live_trading is True:
        with open('stop_loss_list.pickle', 'wb') as handle:
            pickle.dump(context.stop_loss_list, handle, protocol=pickle.HIGHEST_PROTOCOL)
        with open('sector_list.pickle', 'wb') as handle:
            pickle.dump(context.sector_stocks, handle, protocol=pickle.HIGHEST_PROTOCOL)


def analyze(context, data):
    pass


def make_pipeline():
    fd = Fundamentals()
    sectors = NASDAQSectorCodes()
    ipos = NASDAQIPO()

    return Pipeline(
        columns={
            'marketcap': fd.marketcap,
            'liabilities': fd.liabilities,
            'revenue': fd.revenue,
            'eps': fd.eps,
            'rnd': fd.rnd,
            'netinc': fd.netinc,
            'pe': fd.pe,
            'ipoyear': ipos,
            'yoy_sales': fd.yoy_sales,
            'qoq_earnings': fd.qoq_earnings,
            'sector': sectors
        },
    )


def recalc_sector_wise_exposure(context, data):
    net = context.portfolio.portfolio_value
    for sector, stocks in context.sector_stocks.items():
        sector_exposure = 0
        for stock in stocks:
            position = context.portfolio.positions.get(stock)
            if position is not None:
                if position.last_sale_price == 0:
                    last_price = data.history(position.asset, 'close', 1, '1d')[0]
                else:
                    last_price = position.last_sale_price
                exposure = (last_price * position.amount) / net
                sector_exposure += exposure
        context.sector_wise_exposure[sector] = sector_exposure


def rebalance(context, data):
    handle_data(context, data)
    print("-----Rebalance method Called-------")
    positions = list(context.portfolio.positions.values())
    pipeline_data = context.pipeline_data
    cash = context.portfolio.cash
    stop_list = context.stop_loss_list

    recalc_sector_wise_exposure(context, data)

    benchmark_dma = get_dma_returns(context, 200, data.current_dt)
    if benchmark_dma < 0:
        return

    interested_assets = pipeline_data.dropna(subset=['marketcap'])

    # filter assets based on
    # 1. market cap is large cap (>10billion)
    # 2. liabilities < 180bn
    # 3. yoy sales > 3% or none
    # 4. ipo should be earlier than at least two years or n/a
    # 5. should have invested more than or equal 6% of total revenue in RND
    # 6. net income should be positive
    # 7. should not have a decrease in earnings
    interested_assets = interested_assets.query("marketcap > 10000000000 "
                                                "and liabilities < 180000000000 "
                                                "and (yoy_sales >= 0.03 or yoy_sales != yoy_sales)"
                                                "and (ipoyear < {} or ipoyear == -1)"
                                                "and ((100 * rnd) / revenue) >= 6"
                                                "and netinc >= 0"
                                                "and qoq_earnings >= 0"
                                                .format(data.current_dt.year - 2))

    # sort the buy candidate stocks based on their quarterly earnings
    interested_assets = interested_assets.replace([np.inf, -np.inf], np.nan)
    interested_assets = interested_assets.dropna(subset=['qoq_earnings'])
    interested_assets = interested_assets.sort_values(by=['qoq_earnings'], ascending=False)

    net = context.portfolio.portfolio_value
    for position in context.portfolio.positions.values():
        if position.last_sale_price == 0:
            last_price = data.history(position.asset, 'close', 1, '1d')[0]
        else:
            last_price = position.last_sale_price
        exposure = (last_price * position.amount) / net
        # selling half to book profit
        if exposure > 0.15:
            order_target_percent(position.asset, exposure / 2)
            strategy.SendMessage('Book Profit Sell Order', 'Book Profit by selling half of '+str(position.asset.symbol))
            context.turnover_count += 1
            print("Half profit booking done for {}".format(position.asset.symbol))

    position_list = []
    for position in positions:
        position_list.append(position.asset)

    exempt_list = ['MELI', 'GENZ', 'FRX', 'HSP', 'AGN1', 'BXLT', 'MEDI', 'ETEK1', 'DNA', 'PNU', 'SDS1', 'LLTC', 'KEYS', 'RHT', 'ULTI']

    # Buy logic
    if len(position_list) < 25:
        for stock in interested_assets.index.values:
            # if stock not in position_list and stock not in stop_list and stock.exchange in ('NASDAQ', 'NYSE'):
            if stock not in position_list and stock not in stop_list and stock.symbol not in exempt_list:

                # Condition 1
                # avg_vol = data.history(stock, 'volume', 50, '1d').mean()
                # if avg_vol < 10000:
                #     continue
                try:
                    avg_vol = data.history(stock, 'volume', 52, '1d')[:-2].mean()
                    min_vol = data.history(stock, 'volume', 52, '1d')[:-2].min()
                    price = data.history(stock, 'price', 1, '1d').item()
                except:
                    print("Stock not present in IB: {}").format(str(stock.symbol))
                    continue
                if (price * min_vol) < 10000 or (price * avg_vol) < 20000:
                    continue

                # # Condition 2
                # month_old_price = data.history(stock, 'close', 22, '1d')
                # monthly_gain_loss = float(
                #     "{0:.2f}".format((month_old_price[-1] - month_old_price[0]) * 100 / month_old_price[0]))
                # if monthly_gain_loss < -5:
                #     continue

                sector = interested_assets.loc[stock].sector
                quantity = get_quantity(context.portfolio.portfolio_value,
                                        context.sector_wise_exposure, sector, price, cash)

                if quantity > 0 and data.can_trade(stock):
                    order_target(stock, quantity)
                    strategy.SendMessage('Buy Order', 'Buy {} shares of {}'.format(str(quantity), str(stock.symbol)))
                    context.turnover_count += 1
                    cash -= quantity * data.current(stock, 'price')
                    if context.sector_stocks.get(sector, None) is None:
                        context.sector_stocks.update({sector: [stock]})
                    else:
                        context.sector_stocks[sector].append(stock)
                    print("Buy order triggered for: {} on {} for {} shares"
                          .format(stock.symbol, data.current_dt.strftime('%d/%m/%Y'), quantity))
                    position_list.append(stock)
                if len(position_list) >= 25:
                    break


def handle_data(context, data):
    if context.logic_run_done is False:
        try:
            core_logic(context, data)
            context.logic_run_done = True
        except ValueError as e:
            print(e)


def core_logic(context, data):
    if context.live_trading is True:
        for symbol, position in context.portfolio.positions.items():
            data.current(symbol, 'price')
        time.sleep(60)

    stop_list = context.stop_loss_list
    # update stop loss list
    for i1, s1 in stop_list.items():
        stop_list = stop_list.drop(labels=[i1])
        s1 -= 1
        if s1 > 0:
            stop_list = stop_list.append(pd.Series([s1], index=[i1]))

    positions = list(context.portfolio.positions.values())

    benchmark_dma = get_dma_returns(context, 200, data.current_dt)
    if benchmark_dma < 0:
        sell_all(positions, context)
        return

    position_list = []
    # Sell logic
    for position in positions:
        position_list.append(position.asset)
        if not position.amount > 0:
            continue
        if position.last_sale_price == 0:
            last_price = data.history(position.asset, 'close', 1, '1d')[0]
        else:
            last_price = position.last_sale_price

        # prev_price = data.history(position.asset, 'close', 2, '1d')[0]
        # if last_price <= 0 or prev_price <= 0:
        if last_price <= 0:
            raise ValueError("Prices not available")
        net_gain_loss = float("{0:.2f}".format((last_price - position.cost_basis) * 100 / position.cost_basis))

        # daily_net_gain_loss = float("{0:.2f}".format((last_price - prev_price) * 100 / prev_price))
        # if net_gain_loss < -3 or daily_net_gain_loss < -3:
        if net_gain_loss < -3:
            print("{} to be sold. last price = {}, cost basis = {} and net_gain_loss = {}"
                  .format(str(position.asset.symbol), str(last_price), str(position.cost_basis), str(net_gain_loss)))
            order_target(position.asset, 0)
            strategy.SendMessage('Stop loss Sell Order', 'Sell all shares of {}'.format(str(position.asset.symbol)))
            context.turnover_count += 1
            try:
                context.sector_stocks[context.pipeline_data.loc[position.asset].sector].remove(position.asset)

                print("Stop loss triggered for: {} on {}".format(position.asset.symbol,
                                                                 data.current_dt.strftime('%d/%m/%Y')))
                stop_loss = pd.Series([stop_loss_prevention_days], index=[position.asset])
                stop_list = stop_list.append(stop_loss)
            except Exception as e:
                print(e)

        # if net_gain_loss > 25:
        #     order_target(position.asset, 0)
        #     print("Profit booked for: {} on {}".format(position.asset.symbol, data.current_dt.strftime('%d/%m/%Y')))

    context.stop_loss_list = stop_list
    print("Daily handle data processed for {}".format(data.current_dt.strftime('%d/%m/%Y')))


def get_quantity(portfolio_value, sector_wise_exposure, sector, price, cash):
    available_exposure = cash / portfolio_value
    if sector in sector_wise_exposure:
        sector_exposure = sector_wise_exposure.get(sector)
        if sector_exposure < max_sector_exposure:
            exposure = min(max_sector_exposure - sector_exposure, 0.07, available_exposure)
            exposure = round(exposure, 4)
            sector_wise_exposure[sector] += exposure
        else:
            exposure = 0
    else:
        exposure = min(0.07, available_exposure)
        sector_wise_exposure[sector] = exposure
    quantity = int((exposure * portfolio_value) / price)
    return quantity


def sell_all(positions, context):
    print("Sell All rule triggered for "+str(len(positions)))
    for position in positions:
        order_target_percent(position.asset, 0)
        strategy.SendMessage('Sell All and Exit Market', 'Sell all shares of {}'.format(str(position.asset.symbol)))
        context.turnover_count += 1


def get_dma_returns(context, period, dma_end_date):
    returns = context.trading_environment.benchmark_returns[:dma_end_date]
    if returns.size > period:
        returns = 1 + returns[-period:]
    else:
        return 0
    dma_return = 100 * (returns.prod() - 1)
    return dma_return


if __name__ == '__main__':
    start_date = pd.to_datetime(config.get('start_date'), format='%Y%m%d').tz_localize('UTC')
    end_date = pd.to_datetime(config.get('end_date'), format='%Y%m%d').tz_localize('UTC')

    parser = argparse.ArgumentParser(description='live mode.')
    parser.add_argument('--live_mode', help='True for live mode', default='backtest')
    args = parser.parse_args()

    kwargs = {'start': start_date, 'end': end_date, 'initialize': initialize, 'handle_data': handle_data,
              'analyze': analyze, 'before_trading_start': before_trading_start, 'after_trading_end': after_trading_end,
              'bundle': 'quandl', 'capital_base': config.get('capital_base'), 'algo_name': config.get('name'),
              'algo_id': config.get('id'), 'benchmark_symbol': config.get('benchmark_symbol'),
              'tws_uri': get_run_mode(args.live_mode)[0], 'live_trading': get_run_mode(args.live_mode)[1]}

    if args.live_mode == 'live':
        if os.path.exists('test.state'):
            os.remove('test.state')

    strategy = Strategy(kwargs)
    strategy.run_algorithm()

    if args.live_mode != 'True':
        input("Press any key to exit")
