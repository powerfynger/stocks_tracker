from tradingview_screener import Query, Column as col
import pandas as pd
from typing import List

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
    def __init__(self, query_limit=10):
        super().__init__(query_limit)
        self.max_score = 0
        self.indicators = ['name', 'close', 'relative_volume_10d_calc|60', 'relative_volume_intraday|5', 'ChaikinMoneyFlow|60',\
                'MoneyFlow|60', 'ATR', "RSI", "ADX"]
        
    def get_data(self):
        self.data = (Query()
            .select(*self.indicators)
            .where(
            col('relative_volume_10d_calc|60') > 1,
            col('relative_volume_intraday|5') > 1,
            col('ChaikinMoneyFlow|60') > 0.25,
            #col('MoneyFlow|60') > 0.1,  # положительный денежный поток
            col('RSI') > 40,
            col('ADX') > 20 
            )
            .limit(100)
            .set_markets('russia')).get_scanner_data()[1]
        
        self.data['score'] = self.data.apply(self.calculate_buy_score, axis=1)
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
                'relative_volume_10d_calc|60', 
                'relative_volume_intraday|5', 
            ],
            ascending=[False, False])

    def calculate_buy_score(self, stock_data):
        score = 0
        # TODO:
        # Добавить подсчтёт оценки для данной стратегии
        
        return int(score)
    
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)
            
    def get_indicators(self):
        return self.indicators
    
    def get_maxscore(self):
        return self.max_score


def main():
    strat = MoneyFlowStrategy(query_limit=10)
    strat.get_data()
    strat.check_data()


if __name__ == "__main__":
    main()
