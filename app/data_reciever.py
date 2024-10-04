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
        self.max_score = 4
        self.border_score = 0
        self.indicators = ['name', 'close', 'relative_volume_10d_calc|120', 'relative_volume_intraday|5', 'ChaikinMoneyFlow|120',\
                'RSI|120', 'MACD.macd|120', 'MACD.signal|120',  'VWAP|120', 'ChaikinMoneyFlow|30', 'relative_volume_10d_calc|30']
        
    def get_data(self):
        self.data = (Query()
            .select(*self.indicators)
            .where(
            col('relative_volume_10d_calc|120') > 1.1,
            col('ChaikinMoneyFlow|120') > 0.25,
            # col('MoneyFlow|120') > 30,  # положительный денежный поток
            col('MoneyFlow|120') < 70,  # положительный денежный поток
            col('RSI|120') < 70,
            # col('close') < col('VWAP|120'),
            # col('ADX') > 20,
            col('MACD.macd|120') > col('MACD.signal|120')
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
                'relative_volume_10d_calc|120', 
                'ChaikinMoneyFlow|120'
            ],
            ascending=[False, False])

    def calculate_buy_score(self, stock_data):
        score = 0
        macd_diff = stock_data['MACD.macd|120'] - stock_data['MACD.signal|120']
        if stock_data['ChaikinMoneyFlow|120'] >= 0.3:
            score += 0.5
        if stock_data['relative_volume_10d_calc|120'] >= 1.5:
            score += 0.5
        if stock_data['relative_volume_10d_calc|120'] >= 2:
            score += 0.5
        if stock_data['RSI|120'] >= 30 and stock_data['RSI|120'] < 70:
            score += 0.5
        # if macd_diff >:
            # score += 0.5
        
        return int(score)
    
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)
            
    def get_indicators(self):
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
        return self.data.to_dict(orient="records")

    def get_border_score(self):
        return self.border_score

    def check_sell(self, ticker) -> bool:
        stock = self.get_data_stock(ticker)[0]
        if stock['ChaikinMoneyFlow|30'] <= 0.15:
            return True
        if stock['relative_volume_10d_calc|30'] <= 1:
            return True
        if stock['RSI|120'] > 80:
            return True
        if stock['relative_volume_intraday|5'] < 1:
            return True
        return False
                
def main():
    strat = MoneyFlowStrategy(query_limit=100)
    strat.get_data()
    strat.check_data()


if __name__ == "__main__":
    main()
