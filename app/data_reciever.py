from tradingview_screener import Query, Column as col

import pandas as pd
import numpy as np
import numpy as np

from typing import List

from portfolio_manager import TinkoffOrderManager, TinkoffSandboxOrderManager
from  predictor import RFPredictor
from config import Config

class TradingStrategy:
    """
    Базовый класс для всех стратегий.
    """
    def __init__(self, query_limit=10):
        self.data = []
        self.query_limit=query_limit

    def get_data(self):
        """
        Получает данные для стратегии.
        """
        raise NotImplementedError("Метод get_data должен быть реализован в подклассах.")
    def check_data(self):
        """
        Дополнительно проверяет данные для стратегии.
        """
        raise NotImplementedError("Метод check_data должен быть реализован в подклассах.")
    def check_sell(self):
        raise NotImplementedError("Метод check_sell должен быть реализован в подклассах.")
    def get_data_stock(self, ticker):
        raise NotImplementedError("Метод get_data_stock должен быть реализован в подклассах.")
        

class MoneyFlowStrategy(TradingStrategy):
    """
    Стратегия, основанная на движении капитала.
    """
    def __init__(self, query_limit=10):
        super().__init__(query_limit)
        self.max_score = 4
        self.border_score = 0
        self.indicators = ['name', 'close', 'average_volume_30d_calc|30','relative_volume_10d_calc|30', 'volume|30',\
                'RSI|30', 'MACD.macd|30', 'MACD.signal|30',  'VWAP|30', 'ChaikinMoneyFlow|30', "ADX|30"]
        self.custom_indicators = ['score', 'vwap_diff']
        
    def get_data(self):
        self.data = (Query()
            .select(*self.indicators)
            .where(
            col('relative_volume_10d_calc|30') > 2,
            col('average_volume_10d_calc|30') >= 20000,
            # col('average_volume_30d_calc|30') < col('volume|30'),
            # col('relative_volume_intraday|5') > 1,
            col('ChaikinMoneyFlow|30') > 0.1,
            col('MoneyFlow|30') > 30,  # положительный денежный поток
            # col('MoneyFlow|120') < 70,  # положительный денежный поток
            col('RSI|30') < 70,
            # col('ADX+DI|30') > col('ADX-DI|30'),
            # col('close') < col('VWAP|30'),
            # col('ADX|30') > 25,
            # col('MACD.macd|30') > col('MACD.signal|30')
            )
            .limit(100)
            .set_markets('russia')).get_scanner_data()[1]
        
        self.data['score'] = self.data.apply(self.calculate_buy_score, axis=1)
        self.data['vwap_diff'] = self.data.apply(self.calculate_vwap_diff, axis=1)
        self.data['volume_diff'] = self.data.apply(self.calculate_volume_diff, axis=1)
        self.data = self.data.round(3)
        self.sort_data()
        # TODO:
        # Система оценок
        # self.data = self.data[self.data['score'] >= 3]
        # self.add_scores()
        return self.data.head(self.query_limit).to_dict(orient="records")

    def sort_data(self):
        self.data = self.data\
        .sort_values(
            [
                'volume_diff', 
                'vwap_diff',
                # 'ChaikinMoneyFlow|120'
            ],
            ascending=[False, False])

    def calculate_vwap_diff(self, stock_data):
        vwap_diff = (stock_data['VWAP|30'] - stock_data['close']) / stock_data['close'] * 100
        return vwap_diff

    def calculate_volume_diff(self, stock_data):
        volume_diff = (stock_data['volume|30'] - stock_data['average_volume_30d_calc|30']) / stock_data['average_volume_30d_calc|30'] * 100
        return volume_diff
    
    def calculate_buy_score(self, stock_data):
        score = 0
        # macd_diff = stock_data['MACD.macd|120'] - stock_data['MACD.signal|120']
        # if stock_data['ChaikinMoneyFlow|120'] >= 0.3:
        #     score += 0.5
        # if stock_data['relative_volume_10d_calc|120'] >= 1.5:
        #     score += 0.5
        # if stock_data['relative_volume_10d_calc|120'] >= 2:
        #     score += 0.5
        # if stock_data['RSI|120'] >= 30 and stock_data['RSI|120'] < 70:
        #     score += 0.5
        # if macd_diff >:
            # score += 0.5
        
        return int(score)
    
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)
            
    def get_indicators(self):
        # indicators = self.indicators
        # indicators.append(self.custom_indicators)  
        return self.indicators
    
    def get_maxscore(self):
        return self.max_score

    def get_data_stock(self, ticker):
        self.data = (Query()
        .select(*self.indicators)
        .where(
        col('name') == ticker,
        )
        .set_markets('russia')).get_scanner_data()[1]
        
        self.data['score'] = self.data.apply(self.calculate_buy_score, axis=1)
        self.data['vwap_diff'] = self.data.apply(self.calculate_vwap_diff, axis=1)
        self.data['volume_diff'] = self.data.apply(self.calculate_volume_diff, axis=1)
        self.data = self.data.round(3)
        return self.data.to_dict(orient="records")[0]

    def get_border_score(self):
        return self.border_score

    def check_sell(self, ticker) -> bool:
        stock = self.get_data_stock(ticker)
        
        if stock['ChaikinMoneyFlow|30'] <= 0:
            return True
        # if stock['relative_volume_10d_calc|30'] <= 1:
        #     return True
        if stock['RSI|30'] >= 80:
            return True
        # if stock['relative_volume_intraday|5'] < 1:
            # return True
        return False

class NadarayaWatsonStrategy(TradingStrategy):
    def __init__(self, tinkObj: TinkoffOrderManager, bandwith=23, r=20, x0=25, query_limit=100):
        super().__init__(query_limit)
        self.max_score = 0
        self.border_score = 0
        self.indicators = ['name', 'relative_volume_10d_calc|15', 'MACD.macd|15', 'MACD.signal|15', 'MoneyFlow|15']
        self.custom_indicators = ['close']
        self.tinkObj = tinkObj
        self.x0 = x0
        self.bandwith = bandwith
        self.r = r
        self.days_back = 1
        self.predictor = RFPredictor(self.bandwith)

        
        
    def get_indicators(self):
        return (self.indicators + self.custom_indicators)
    
    def get_data(self):
        self.data = (Query()
            .select(*self.indicators)
            .where(
            # col('Recommend.All|60') >= 0.5,
            col('relative_volume_10d_calc|15') > 2,
            col('volume|15') > 60000,
            col('MoneyFlow|15') < 75,
            # col('ADX|15') > 20,
            # col('MACD.macd|15') > col('MACD.signal|15')
            )
            .limit(100)
            .set_markets('russia')).get_scanner_data()[1]
        print(self.data)
        self.data = self.data.round(3)
        self.data['score'] = self.data.apply(self.calculate_buy_score, axis=1)
        self.data = self.data.head(self.query_limit).to_dict(orient="records")
        data_to_buy = []
        
        for stock in self.data:
            historical_data = self.tinkObj.get_historical_data(stock['name'], self.days_back)
            if not historical_data:
                continue
            res = generate_signals(historical_data, x_0=self.x0, r=self.r, lag=2, smooth_colors=True, h=self.bandwith).to_dict(orient="records")[-1]
            # print(close_prices, res, stock['name'])
            if res['plotColor'] == 'green' and self.predictor.get_prediction_next_close(stock['name'], historical_data) > historical_data[-1]['close']:
                data_to_buy.append(stock)
        return data_to_buy

    def get_border_score(self):
        return self.border_score
    
    def get_maxscore(self):
        return self.max_score

    def check_sell(self, ticker):
        historical_data = self.tinkObj.get_historical_data(ticker, self.days_back)
        if not historical_data:
            return True
        res = generate_signals(historical_data, x_0=self.x0, r=self.r, lag=2, smooth_colors=True, h=self.bandwith).to_dict(orient="records")[-1]
        if res['plotColor'] == 'red':
            return True
        if self.get_data_stock(ticker)['MoneyFlow|15'] >= 80:
            return True
        
        return False
    def get_nadaray(self):
        for stock in self.tinkObj.db.get_data().keys():
            # print(stock)
            close_prices = self.tinkObj.get_close_prices(stock, self.days_back)
            if not close_prices:
                continue
            res = generate_signals(close_prices, x_0=self.x0, r=self.r, lag=2, smooth_colors=True, h=self.bandwith).to_dict(orient="records")[-1]
            print(res)
            
            if res['plotColor'] == 'green':
                print(f"--> купить ", stock)
            else:
                print(f"--> продать ", stock)
    
    def get_data_stock(self, ticker):
        data = (Query()
        .select(*self.indicators)
        .where(
        col('name') == ticker,
        )
        .set_markets('russia')).get_scanner_data()[1].to_dict(orient="records")[0]
        
        data['score'] = self.border_score
        historical_data = self.tinkObj.get_historical_data(data['name'], self.days_back)
        if not historical_data:
            return data 
        
        res = generate_signals(historical_data, x_0=self.x0, r=self.r, lag=2, smooth_colors=True, h=self.bandwith).to_dict(orient="records")[-1]
        data['close'] = historical_data[-1]['close']
        return data

    def calculate_buy_score(self, stock_data):
        score = 0

        return int(score)

def generate_signals(data_array, h=8, r=8, x_0=25, smooth_colors=False, lag=2):
    """
    Generates buy/sell signals based on kernel regression.

    Args:
        close_prices (pd.Series): Series of closing prices.
        h (float): Lookback window.
        r (float): Relative weighting of time frames.
        x_0 (int): Bar index to start regression.
        smooth_colors (bool): Use smooth color transitions.
        lag (int): Lag for crossover detection.

    Returns:
        pd.DataFrame: DataFrame with buy/sell signals and colors.
    """

    df = pd.DataFrame(data_array)
    size = len(data_array)

    # Kernel Regression Calculation
    df['yhat1'] = df['close'].rolling(window=h).apply(lambda x: kernel_regression(src=x, h=h, x_0=x_0, r=r), raw=True)
    df['yhat2'] = df['close'].rolling(window=h - lag).apply(lambda x: kernel_regression(x, h=h - lag, x_0=x_0, r=r), raw=True)

    # Rates of Change
    df['wasBearish'] = df['yhat1'].shift(2) > df['yhat1'].shift(1)
    df['wasBullish'] = df['yhat1'].shift(2) < df['yhat1'].shift(1)
    df['isBearish'] = df['yhat1'].shift(1) > df['yhat1']
    df['isBullish'] = df['yhat1'].shift(1) < df['yhat1']
    df['isBearishChange'] = df['isBearish'] & df['wasBullish']
    df['isBullishChange'] = df['isBullish'] & df['wasBearish']

    # Crossovers
    df['isBullishCross'] = (df['yhat2'].shift(1) < df['yhat1'].shift(1)) & (df['yhat2'] > df['yhat1'])
    df['isBearishCross'] = (df['yhat2'].shift(1) > df['yhat1'].shift(1)) & (df['yhat2'] < df['yhat1'])

    # Smooth Crossovers
    df['isBullishSmooth'] = df['yhat2'] > df['yhat1']
    df['isBearishSmooth'] = df['yhat2'] < df['yhat1']

    # Determine colors based on smoothColors
    df['colorByCross'] = np.where(df['isBullishSmooth'], 'green', 'red')  # Assuming green for bullish, red for bearish
    df['colorByRate'] = np.where(df['isBullish'], 'green', 'red')
    df['plotColor'] = np.where(smooth_colors, df['colorByCross'], df['colorByRate'])

    # Generate alert signals
    df['alertBullish'] = np.where(smooth_colors, df['isBearishCross'], df['isBullishChange'])
    df['alertBearish'] = np.where(smooth_colors, df['isBullishCross'], df['isBullishChange'])

    return df[['close', 'yhat1', 'yhat2', 'plotColor', 'alertBullish', 'alertBearish']]

def kernel_regression(src, h, x_0=25, r=8):
    """
    Функция ядерной регрессии.
    
    :param src: Исходные данные (например, временной ряд).
    :param size: Размер окна для регрессии.
    :param h: Ширина ядра (параметр сглаживания).
    :param r: Параметр, определяющий форму ядра.
    :return: Сглаженное значение.
    """
    n = len(src)
    current_weight = 0.0
    cumulative_weight = 0.0
    
    # Итерируемся по окну
    for i in range(max(0, n - x_0), n):
        y = src[i]
        w = (1 + (i - (n - x_0)) ** 2 / (h ** 2 * 2 * r)) ** (-r)  # Ядровая функция
        current_weight += y * w
        cumulative_weight += w
    
    if cumulative_weight == 0:
        return np.nan  # Возвращаем NaN, если сумма весов равна нулю
    
    return current_weight / cumulative_weight

def kernel_regression_vectorized(series, h, x_0, r):
    size = len(series)
    i = np.arange(size)
    w = np.power(1 + (np.power(i - x_0, 2) / ((h**2 * 2 * r))), -r)
    current_weight = (series * w).sum()
    cumulative_weight = w.sum()
    return current_weight / cumulative_weight

def calculate_yhat(df, h, x_0, r, lag=0):
    # Центрируем x_0 относительно текущего окна
    x_0_adjusted = x_0 + h - lag -1 # Индекс центра окна
    return kernel_regression_vectorized(df['Close'], h - lag, x_0_adjusted, r)

def kernel_rsegression(src, size, h, x_0=25, r=8):
    """
    Calculates the kernel regression estimation.

    Args:
        src (pd.Series): Series of closing prices within the rolling window.
        size (int): Size of the entire data series.
        h (float): Lookback window.
        x_0 (int): Bar index to start regression.
        r (float): Relative weighting of time frames.

    Returns:
        float: Kernel regression estimation.
    """
    # src = src.to_numpy()  # Convert Series to numpy array for indexing
    current_weight = 0.0
    cumulative_weight = 0.0
    for i in range(x_0, len(src)):
        y = src[i]
        w = (1 + ((i)**2 / ((h**2 * 2 * r))))**(-r)
        current_weight += y * w
        cumulative_weight += w
    return current_weight / cumulative_weight


def main():
    # ndstrat = NadarayaWatsonStrategy(query_limit=100, tinkObj=TinkoffOrderManager(db_filepath="TickersToFigiRus.json",api_key=Config.TINKOFF_REAL_TOKEN))
    # strat = MoneyFlowStrategy(query_limit=100)
    # print(ndstrat.get_nadaray())
    broker = TinkoffSandboxOrderManager(db_filepath="TickersToFigiRus.json",api_key=Config.TINKOFF_REAL_TOKEN)
    predictor = RFPredictor()
    # close_prices=broker.get_close_prices('MOEX', 1)
    # print(close_prices)
    # print(ndstrat.get_data())
    # signals_df=generate_signals(close_prices, h=8)
    # signals_df = test_generate_signals(close_prices, r=ndstrat.r, lag=2, smooth_colors=True, h=ndstrat.bandwith)
    # signals_df = generate_signals(close_prices, r=ndstrat.r, lag=2, smooth_colors=True, h=ndstrat.bandwith)
    # print(signals_df.tail(60))
    hist_data = broker.get_historical_data('TTLK', 1)
    # pred = predictor(stock['name'], historical_data) 
    h = hist_data[-1]['close']
    print(predictor.get_prediction_next_close('TTLK', hist_data))
    

if __name__ == "__main__":
    main()
