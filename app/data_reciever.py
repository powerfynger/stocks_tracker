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
    def __init__(self, query_limit=10):
        super().__init__(query_limit)
        self.max_score = 5
        
    def get_data(self):
        indicators = ['ChaikinMoneyFlow|15', 'MoneyFlow|14', 'RSI|15', 'volume|15', 'EMA20|15', 'ATR|15']
        self.data = (Query()
            .select('name', 'relative_volume_10d_calc|60', 'relative_volume_intraday|5', 'ChaikinMoneyFlow|60',\
                'MoneyFlow|60', 'ATR', "RSI", "ADX")
            .where(col('relative_volume_10d_calc|60') > 1) # относительный объем за час дней более 120%
            .where(col('relative_volume_intraday|5') > 2)  # относительный объем за 5 минут более 200%
            .where(col('ChaikinMoneyFlow|60') > 0.25)  # положительный денежный поток Чайкина
            # .where(col('MoneyFlow|60') > 0.1)  # положительный денежный поток Чайкина
            .where(col('RSI') > 50) # RSI указывает на силу покупателей
            .where(col('ADX') > 20) # Наличие тренда
            .limit(100)
            # .where(col('close') > col('open'))  # цена закрытия выше цены открытия (??)
            .set_markets('russia')).get_scanner_data()[1]
        
        # self.data['score'] = self.data.apply(self.calculate_buy_score, axis=1)
        self.sort_data()
        # self.data = self.data[self.data['score'] >= 3]
        # self.add_scores()
        return self.data.head(self.query_limit).to_dict(orient="records")

    def sort_data(self):
        self.data = self.data\
        .sort_values('relative_volume_10d_calc|60', ascending=False)\
        # .sort_values('relative_volume_intraday|5', ascending=False)\
        # .sort_values('MoneyFlow|60', ascending=False)\
        # .sort_values('ChaikinMoneyFlow|60', ascending=False)\
        # .sort_values('score', ascending=False)\
    
    def calculate_buy_score(self, stock_data):
        score = 0

        if stock_data['relative_volume_10d_calc|60'] > 2:
            score += 2
        elif stock_data['relative_volume_10d_calc|60'] > 1.5:
            score += 1

        # RSI
        if stock_data['RSI'] > 70:
            score += 1
        elif stock_data['RSI'] > 60:
            score += 0.5

        # ADX
        if stock_data['ADX'] > 30:
            score += 1
        elif stock_data['ADX'] > 25:
            score += 0.5
        
        # Chaikin Money Flow
        if stock_data['ChaikinMoneyFlow'] > 0.3:
            score += 1
        elif stock_data['ChaikinMoneyFlow'] > 0.2:
            score += 0.5

        return int(score)

    
    
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)
            
    def get_maxscore(self):
        return self.max_score

class LorentzianClassificationStrategy(TradingStrategy):
    """
    Стратегия, основанная на алгоритме Lorentzian Classification.
    """
    def __init__(self, query_limit=10):
        super().__init__(query_limit)
        self.max_score = 3

    def get_data(self):
        self.data = (Query()
            .select('name', 'close', 'volume|5', 'volume_change|5', 'relative_volume_10d_calc|5', 'RSI|5', 'ADX|5', 'CCI20|5', 'ChaikinMoneyFlow', 'ATR')
                .where(col('volume_change|5') > 0.8)  # Значительное увеличение объема 
            .where(col('relative_volume_10d_calc|5') > 1.5)  # Высокий относительный объем за 10 дней
            .where(col('RSI|5') > 60)  # RSI указывает на силу покупателей, но не перекупленность
            .where(col('ADX|5') > 20)  # Наличие тренда
            .where(col('CCI20|5') > 100)  # Цена выше среднего значения
            .where(col('ChaikinMoneyFlow') > 0.2)  # Заметный приток капитала
            .where(col('close') > col('open'))  # Бычий день
            .limit(self.query_limit)
        .set_markets('russia')).get_scanner_data()[1]
        
        self.data['score'] = self.data.apply(self.calculate_buy_score, axis=1)

        self.sort_data()
        return self.data.to_dict(orient="records")

    def sort_data(self):    
        self.data = self.data\
        .sort_values('volume_change|5', ascending=False)\
        .sort_values('score', ascending=False)\

        
    def calculate_buy_score(self, stock_data):
        score = 0
        # TODO:
        # Придумать как нормализовать и использовать изменение этих показателей
        # # Объем
        # score += stock_data['volume_change|5']
        # score += stock_data['relative_volume_10d_calc|5']
        # # Chaikin Money Flow
        # score += stock_data['ChaikinMoneyFlow'] 


        # RSI
        if stock_data['RSI|5'] > 60:
            score += 1

        # ADX
        if stock_data['ADX|5'] > 20:
            score += 1

        # CCI
        if stock_data['CCI20|5'] > 100:
            score += 1

        return int(score)
    
    def get_max_score(self):
        return self.max_score
        
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)

class DividendStrategy(TradingStrategy):
    """
    Стратегия, основанная на покупке бумаг с высокими дивидендами и устойчивыми финансовыми показателями.
    """
    def __init__(self, query_limit=10):
        super().__init__(query_limit)
        self.max_score = 0

    def get_data(self):
        self.data = (Query()
            .select('name', 'dividend_yield_recent', 'dividend_payout_ratio_percent_fq', 'long_term_debt_to_equity_fq', 'volume_change|1M', 'relative_volume_10d_calc|1M', 'ATR')
                # .where(col('volume_change|1M') > 0.8)  # Значительное увеличение объема 
            # .where(col('dividend_payout_ratio_percent_fq') not )  
            # .where(col('dividend_payout_ratio_percent_fq') > 0)  
            .limit(self.query_limit)
        .set_markets('russia')).get_scanner_data()[1]
        
        # self.data['score'] = self.data.apply(self.calculate_buy_score, axis=1)

        self.sort_data()
        return self.data.to_dict(orient="records")

    def sort_data(self):    
        self.data = self.data\
        .sort_values('relative_volume_10d_calc|1M', ascending=False)\
        .sort_values('dividend_payout_ratio_percent_fq', ascending=False)\
        # .sort_values('score', ascending=False)\

        
    def calculate_buy_score(self, stock_data):
        score = 0
       
        return int(score)
    
    def get_max_score(self):
        return self.max_score
        
    def check_data(self):
        for stock_info in self.data.to_dict(orient="records"):
            print(stock_info)



def main():
    strat = MoneyFlowStrategy(query_limit=10)
    strat.get_data()
    strat.check_data()


if __name__ == "__main__":
    main()