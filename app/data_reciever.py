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
    def sort_data(self):
        """
        Сортирует данные для стратегии по значениям индикаторов.
        """
        raise NotImplementedError("Метод sort_data должен быть реализован в подклассах.")

class MoneyFlowStrategy(TradingStrategy):
    """
    Стратегия, основанная на движении капитала.
    """

    def get_data(self):
        indicators = ['ChaikinMoneyFlow|15', 'MoneyFlow|14', 'RSI|15', 'volume|15', 'EMA20|15', 'ATR|15']
        self.data = (Query()
            .select('name', 'close', 'volume', 'volume_change', 'relative_volume_10d_calc', 'relative_volume_intraday|5', 'ChaikinMoneyFlow', 'ATR')
            .where(col('volume_change') > 0.5)  # изменение объема более 50%
            .where(col('relative_volume_10d_calc') > 1.2) # относительный объем за 10 дней более 120%
            .where(col('relative_volume_intraday|5') > 2)  # относительный объем за 5 минут более 200%
            .where(col('ChaikinMoneyFlow') > 0.1)  # положительный денежный поток Чайкина
            .where(col('close') > col('open'))  # цена закрытия выше цены открытия (??)
            .limit(self.query_limit)
            .set_markets('russia')).get_scanner_data()[1]
        self.sort_data()
        return self.data.to_dict(orient="records")

    def sort_data(self):
        self.data = self.data\
        .sort_values('volume_change', ascending=False)\
        .sort_values('relative_volume_10d_calc', ascending=False)\
        .sort_values('ChaikinMoneyFlow', ascending=False)
        
    
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)

class LorentzianClassificationStrategy(TradingStrategy):
    """
    Стратегия, основанная на алгоритме Lorentzian Classification.
    """

    def get_data(self):
        self.data = (Query()
            .select('name', 'close', 'volume|5', 'volume_change|5', 'relative_volume_10d_calc|5', 'RSI|5', 'ADX|5', 'CCI20|5', 'ChaikinMoneyFlow')
                .where(col('volume_change|5') > 0.8)  # Значительное увеличение объема 
            .where(col('relative_volume_10d_calc|5') > 1.5)  # Высокий относительный объем за 10 дней
            .where(col('RSI|5') > 60)  # RSI указывает на силу покупателей, но не перекупленность
            .where(col('ADX|5') > 20)  # Наличие тренда
            .where(col('CCI20|5') > 100)  # Цена выше среднего значения
            .where(col('ChaikinMoneyFlow') > 0.2)  # Заметный приток капитала
            .where(col('close') > col('open'))  # Бычий день
            .limit(self.query_limit)
        .set_markets('russia')).get_scanner_data()[1]
        
        self.sort_data()
        return self.data.to_dict(orient="records")

    def sort_data(self):    
        buy_data = self.data
        buy_data['score'] = (
            buy_data['volume_change|5'] / buy_data['volume_change|5'].max() +
            2 * buy_data['relative_volume_10d_calc|5'] / buy_data['relative_volume_10d_calc|5'].max() +
            (buy_data['RSI|5'] > 60).astype(int) +
            (buy_data['ADX|5'] > 20).astype(int) +
            (buy_data['CCI20|5'] > 100).astype(int) +
            2 * buy_data['ChaikinMoneyFlow'] / buy_data['ChaikinMoneyFlow'].max()
        )
        buy_data = buy_data.sort_values('score', ascending=False)
        self.data = buy_data
        
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)


def main():
    strat = MoneyFlowStrategy(5)
    strat.get_data()
    strat.check_data()


if __name__ == "__main__":
    main()