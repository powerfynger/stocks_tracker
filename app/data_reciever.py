from tradingview_screener import Query, Column as col
import pandas as pd
from typing import List


base_strat = ['relative_volume_intraday|5', 'RSI|15', 'EMA10|15', 'relative_volume_10d_calc|5', 'Chaikin Money Flow (20)']


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

class MoneyFlowStrategy(TradingStrategy):
    """
    Стратегия, основанная на движении капитала.
    """

    def get_data(self):
        indicators = ['ChaikinMoneyFlow|15', 'MoneyFlow|14', 'RSI|15', 'volume|15', 'EMA20|15', 'ATR|15']
        self.data = (Query()
            .select('name', 'close', 'volume', 'volume_change', 'relative_volume_10d_calc', 'relative_volume_intraday|5', 'ChaikinMoneyFlow')
            .where(col('volume_change') > 0.5)  # изменение объема более 50%
            .where(col('relative_volume_10d_calc') > 1.2) # относительный объем за 10 дней более 120%
            .where(col('relative_volume_intraday|5') > 2)  # относительный объем за 5 минут более 200%
            .where(col('ChaikinMoneyFlow') > 0.1)  # положительный денежный поток Чайкина
            .where(col('close') > col('open'))  # цена закрытия выше цены открытия (??)
            .limit(self.query_limit)
            .set_markets('russia')).get_scanner_data()[1]

        return self.data.to_dict(orient="records")
    
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)

def main():
    strat = MoneyFlowStrategy()
    strat.get_data()
    strat.check_data()


if __name__ == "__main__":
    main()