import pandas as pd
from typing import List, Dict
from tinkoff.invest import (
    CandleInterval, Client, MoneyValue,
    OrderDirection, OrderType, InstrumentStatus,
    StopOrderDirection, StopOrderType, StopOrderExpirationType,
    InstrumentIdType, InstrumentType
    )

from tinkoff.invest.services import SandboxService, InstrumentsService, OperationsService, MarketDataService
from tinkoff.invest.sandbox.client import SandboxClient
from tinkoff.invest.utils import decimal_to_quotation, quotation_to_decimal, money_to_decimal, now
from decimal import Decimal

from datetime import datetime, timedelta
import abc
import os, sys
import uuid 

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, '..'))

from config import Config
from data_handler import JsonDBHandler

# Изменить на динамические, в заивисимости от ATR 
TAKE_PROFIT_PERCENTAGE = 0.05
STOP_LOSS_PERCENTAGE = -0.02
MIN_PRICE_STEP = 0.02
STOP_ORDER_EXPIRE_DURATION = timedelta(weeks=2)

class BaseOrderManager(abc.ABC):
    """
    Абстрактный базовый класс для всех брокеров/эмуляторов.
    """

    def __init__(self, api_key):
        self.api_key = api_key
        self.balance = 0
        self.account_id = None

    def get_balance(self):
        return self.balance

    @abc.abstractmethod
    def get_client(self):
        """
        Метод для получения клиента. Должен быть реализован в подклассах.
        """
        pass

    @abc.abstractmethod
    def open_account(self, client):
        """
        Метод для открытия счета. Должен быть реализован в подклассах.
        """
        pass

    @abc.abstractmethod
    def buy_stock_now(self, ticker: str):
        """
        Метод для моментальной покупки акций. Должен быть реализован в подклассах.
        """
        pass
    
    @abc.abstractmethod
    def sell_stock_now(self, ticker: str):
        """
        Метод для моментальной продажи акций. Должен быть реализован в подклассах.
        """
        pass
    @abc.abstractmethod
    def get_portfolio_stocks(self):
        """
        Метод получения акций из портфолио. Должен быть реализован в подклассах.
        """
        pass

class TinkoffOrderManager(BaseOrderManager):
    def __init__(self, db_filepath, capital=Config.CAPITAL, api_key=Config.TINKOFF_REAL_TOKEN):
        super().__init__(api_key)
        self.db = JsonDBHandler(db_filepath)
        self.capital = capital
        
        with self.get_client() as client:
            self.reload_ticker_figi_db(client.instruments)
            self.open_account(client)
            self.load_balance(client)

    def get_client(self):
        return Client(self.api_key)

    def open_account(self, client):
        accounts = client.users.get_accounts().accounts
        self.account_id = accounts[0].id

    def load_balance(self, client):
        positions = client.operations.get_positions(account_id=self.account_id).money
        self.balance = float(quotation_to_decimal(positions[0]))
        
    def get_balance(self):
        return self.balance

    def sell_stock_now(self, ticker: str, quantity: int) -> Decimal:
        """
        Возращается число -- суммарное цена всей заявки
        """
        with self.get_client() as client:
            order_id = uuid.uuid4().hex
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)
            post_order_response = client.orders.post_order(
                figi=figi,
                order_id=order_id,
                quantity=quantity,
                account_id=self.account_id,
                direction=OrderDirection.ORDER_DIRECTION_SELL,
                order_type=OrderType.ORDER_TYPE_MARKET
            )

        return round(money_to_decimal(post_order_response.total_order_amount),2)

    def buy_stock_now(self, ticker: str, quantity: int, atr=None) -> Decimal:
        """
        Возращается число -- суммарное цена всей заявки
        """
        with self.get_client() as client:
            order_id = uuid.uuid4().hex
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)
            post_order_response = client.orders.post_order(
                figi=figi,
                order_id=order_id,
                quantity=quantity,
                account_id=self.account_id,
                direction=OrderDirection.ORDER_DIRECTION_BUY,
                order_type=OrderType.ORDER_TYPE_MARKET
            )

            executed_order_price = money_to_decimal(post_order_response.executed_order_price)
            info = self.get_info_by_figi(figi)
            if not info:
                return Decimal(0)
            try:
                self.set_take_profit(client, figi, executed_order_price, quantity, info, atr)
                self.set_stop_loss(client, figi, executed_order_price, quantity, info, atr)
            except Exception as e:
                print(e)
            
        return round(money_to_decimal(post_order_response.total_order_amount),2)

    def set_take_profit(self, client, figi, executed_order_price, quantity, stock_info, atr=None):
        price_step = stock_info['price_step']
        if atr:
            take_profit_price = round((executed_order_price + Decimal(atr))/price_step, 0) * price_step
        else: 
            take_profit_price = executed_order_price * Decimal(1 + TAKE_PROFIT_PERCENTAGE)
            take_profit_price -= take_profit_price % price_step
        client.stop_orders.post_stop_order(
            quantity=quantity,
            price=decimal_to_quotation(take_profit_price),
            stop_price=decimal_to_quotation(take_profit_price),
            direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL,
            account_id=self.account_id,
            stop_order_type=StopOrderType.STOP_ORDER_TYPE_TAKE_PROFIT,
            instrument_id=figi,
            expire_date=now() + STOP_ORDER_EXPIRE_DURATION,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_DATE,
        )

    def set_stop_loss(self, client, figi, executed_order_price, quantity, stock_info, atr=None):
        price_step = stock_info['price_step']
        if atr:
            stop_loss_price = round((executed_order_price - Decimal(atr))/price_step, 0) * price_step
        else:
            stop_loss_price = executed_order_price * Decimal(1 + STOP_LOSS_PERCENTAGE)
            stop_loss_price -= stop_loss_price % price_step
        client.stop_orders.post_stop_order(
            quantity=quantity,
            stop_price=decimal_to_quotation(stop_loss_price),
            direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL,
            account_id=self.account_id,
            stop_order_type=StopOrderType.STOP_ORDER_TYPE_STOP_LOSS,
            instrument_id=figi,
            expire_date=now() + STOP_ORDER_EXPIRE_DURATION,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_DATE,
        )  
    
    def buy_stock_for_amount(self, ticker: str, amount: float) -> Decimal:
        with self.get_client() as client:
            order_id = uuid.uuid4().hex
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)
            try:
                tink_info = self.get_info_by_figi(figi)
                if not tink_info:
                    return Decimal(0)
                last_price = (client.market_data.get_last_prices(figi=[figi])).last_prices[0].price
                quantity = int(int(amount)//(quotation_to_decimal(last_price) * tink_info['lot']))
                quantity = min(client.market_data.get_order_book(figi=figi, depth=1).asks[0].quantity, quantity)
                if quantity == 0:
                    return 0.0
                post_order_response = client.orders.post_order(
                    figi=figi,
                    order_id=order_id,
                    quantity=quantity,
                    account_id=self.account_id,
                    direction=OrderDirection.ORDER_DIRECTION_BUY,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )
                executed_order_price = money_to_decimal(post_order_response.executed_order_price)
                info = self.get_info_by_figi(figi)
                if not info:
                    return Decimal(0)
                self.set_take_profit(client, figi, executed_order_price, quantity, info)
                self.set_stop_loss(client, figi, executed_order_price, quantity, info)
            except Exception as e:
                print(e)
                return str(e)
        return round(money_to_decimal(post_order_response.total_order_amount),2)        
    
    def get_portfolio_stocks(self) -> List[Dict]:
        with self.get_client() as client:
            stocks = [] 
            for position in client.operations.get_portfolio(account_id=self.account_id).positions:
                stock = {}
                stock['ticker'] = self.get_ticker_by_figi(position.figi)
                stock['worth_current'] = round(money_to_decimal(position.current_price) * quotation_to_decimal(position.quantity),2)
                stock['quantity'] = int(quotation_to_decimal(position.quantity_lots))
                stock['profit_current'] = round(quotation_to_decimal(position.expected_yield)/stock['worth_current'] * 100, 2)
                stocks.append(stock)
            return stocks
    
    def get_info_by_ticker(self, ticker: str) -> Dict:
        with self.get_client() as client:
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)
            try:
                share_response = client.instruments.share_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, 
                    id=figi
                )
            except:
                return {}
        stock_info = {}
        stock_info['lot'] = share_response.instrument.lot
        stock_info['ticker'] = share_response.instrument.ticker
        stock_info['price_step'] = quotation_to_decimal(share_response.instrument.min_price_increment)
        return stock_info
    
    def get_info_by_figi(self, figi: str) -> Dict:
        with self.get_client() as client:
            try:
                share_response = client.instruments.share_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, 
                    id=figi
                )
            except:
                return {}
        stock_info = {}
        stock_info['lot'] = share_response.instrument.lot
        stock_info['ticker'] = share_response.instrument.ticker
        stock_info['price_step'] = quotation_to_decimal(share_response.instrument.min_price_increment)
        return stock_info

    def get_figi_by_ticker(self, ticker: str):
        return self.db.get_info_by_ticker(ticker)

    def get_ticker_by_figi(self, figi: str):
        return self.db.get_ticker_by_info(figi)

    def reload_ticker_figi_db(self, instruments):
        current_time = datetime.now()
        
        last_update_time = self.db.get_last_update_time()
        if last_update_time and (current_time - last_update_time) < timedelta(days=1):
            return
        
        shares = instruments.shares(
            instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
        )
        
        russian_shares = [
            share
            for share in shares.instruments
            if share.currency == "rub" 
        ]
        
        figi_ticker_df = pd.DataFrame(
            russian_shares,
            columns=['ticker', 'figi']
        )
        for pair in figi_ticker_df.to_dict(orient="records"):
            self.db.update_data(pair['ticker'], pair['figi'])
        
        self.db.save_last_update_time(current_time)
        self.db.save_data_to_file()

    def get_close_prices(self, ticker, days) -> List:
        with self.get_client() as cl:
            close_prices = []
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)
            try:
                for candle in cl.get_all_candles(
                    figi=figi,
                    from_= now() - timedelta(days=days),
                    interval=CandleInterval.CANDLE_INTERVAL_15_MIN,
                    ):
                    close_prices.append(float(quotation_to_decimal(candle.close)))
            except:
                pass
            return close_prices
        
    def get_historical_data(self, ticker, days) -> List:
        with self.get_client() as cl:
            historical_data = []
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)

            try:
                for candle in cl.get_all_candles(
                    figi=figi,
                    from_= now() - timedelta(days=days),
                    interval=CandleInterval.CANDLE_INTERVAL_2_MIN,
                    ):
                    historical_data.append(
                        {
                            'close': float(quotation_to_decimal(candle.close)),
                            'open': float(quotation_to_decimal(candle.open)),
                            'high': float(quotation_to_decimal(candle.high)),
                            'low': float(quotation_to_decimal(candle.low)),
                            'volume': candle.volume
                        }
                        )
            except:
                pass
            return historical_data


class TinkoffSandboxOrderManager(BaseOrderManager):
    def __init__(self, db_filepath, capital=Config.CAPITAL, api_key=Config.TINKOFF_REAL_TOKEN):
        super().__init__(api_key=api_key)
        self.db = JsonDBHandler(db_filepath)
        self.capital = capital
        self.balance = capital
        self.portfolio_stocks = []
                
        with self.get_client() as client:
            self.reload_ticker_figi_db(client.instruments)

    def get_client(self):
        return Client(self.api_key)

    def open_account(self, client):
        pass
    
    def load_balance(self, client: Client):
        pass
            
    def get_balance(self):
        return self.balance

    def sell_stock_now(self, ticker: str, quantity: int) -> Decimal:
        worth_total = 0
        with self.get_client() as client:
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)
            tink_info = self.get_info_by_figi(figi)
            if not tink_info:
                return Decimal(0)
            last_price = quotation_to_decimal((client.market_data.get_last_prices(figi=[figi])).last_prices[0].price)
            for stock in self.portfolio_stocks:
                if quantity == 0:
                    break
                if stock['ticker'] == ticker:
                    if stock['quantity'] <= quantity:
                        worth_total += stock['quantity'] * last_price * tink_info['lot']
                        self.balance += worth_total
                        quantity -= stock['quantity']
                        self.portfolio_stocks.remove(stock)
        return worth_total
                
    def buy_stock_now(self, ticker: str, quantity: int, atr=None) -> Decimal:
        """
        TODO
        """
        pass
    
    def set_take_profit(self, client, figi, executed_order_price, quantity, stock_info, atr=None):
        pass
    
    def set_stop_loss(self, client, figi, executed_order_price, quantity, stock_info, atr=None):
        pass    
    
    def buy_stock_for_amount(self, ticker: str, amount: float) -> Decimal:
        with self.get_client() as client:
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)
            try:
                tink_info = self.get_info_by_figi(figi)
                if not tink_info:
                    return Decimal(0)
                last_price = quotation_to_decimal((client.market_data.get_last_prices(figi=[figi])).last_prices[0].price)
                quantity = int(int(amount)//(last_price * tink_info['lot']))
                quantity = min(client.market_data.get_order_book(figi=figi, depth=1).asks[0].quantity, quantity)
                if quantity == 0:
                    return Decimal(0)
                self.balance -= quantity * last_price * tink_info['lot']
                stock = {}
                stock['ticker'] = ticker
                stock['quantity'] = quantity
                stock['origin_price'] = last_price
                self._add_stock_to_portfolio(stock)
            except Exception as e:
                print(e)
                return str(e)

        return round(quantity * last_price * tink_info['lot'],2)        
    
    def get_portfolio_stocks(self) -> List[Dict]:
        with self.get_client() as client:
            stocks = [] 
            for stock in self.portfolio_stocks:
                stock_display = stock
                figi = self.get_figi_by_ticker(stock['ticker'])
                if not figi:
                    return Decimal(0)
                tink_info = self.get_info_by_figi(figi)
                if not tink_info:
                    return Decimal(0)
                last_price = quotation_to_decimal((client.market_data.get_last_prices(figi=[figi])).last_prices[0].price)
                stock_display['worth_current'] = round(last_price * stock['quantity'] * tink_info['lot'],2)
                stock_display['profit_current'] = round((last_price - stock['origin_price'])/stock['origin_price']*100, 2)
                stocks.append(stock_display)
            return stocks
    
    def _add_stock_to_portfolio(self, stock: Dict):
        # TODO
        # Учитывать разные цены покупки для одного актива
        for portfolio_stock in self.portfolio_stocks:
            if portfolio_stock['ticker'] == stock['ticker']:
                portfolio_stock['quantity'] += stock['quantity']
                return
        self.portfolio_stocks.append(stock)
    
    def get_info_by_ticker(self, ticker: str) -> Dict:
        with self.get_client() as client:
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)
            try:
                share_response = client.instruments.share_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, 
                    id=figi
                )
            except:
                return {}
        stock_info = {}
        stock_info['lot'] = share_response.instrument.lot
        stock_info['ticker'] = share_response.instrument.ticker
        stock_info['price_step'] = quotation_to_decimal(share_response.instrument.min_price_increment)
        return stock_info
    
    def get_info_by_figi(self, figi: str) -> Dict:
        with self.get_client() as client:
            try:
                share_response = client.instruments.share_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, 
                    id=figi
                )
            except:
                return {}
        stock_info = {}
        stock_info['lot'] = share_response.instrument.lot
        stock_info['ticker'] = share_response.instrument.ticker
        stock_info['price_step'] = quotation_to_decimal(share_response.instrument.min_price_increment)
        return stock_info
    
    def get_figi_by_ticker(self, ticker: str):
        return self.db.get_info_by_ticker(ticker)

    def get_ticker_by_figi(self, figi: str):
        return self.db.get_ticker_by_info(figi)

    def reload_ticker_figi_db(self, instruments):
        current_time = datetime.now()
        
        last_update_time = self.db.get_last_update_time()
        if last_update_time and (current_time - last_update_time) < timedelta(days=1):
            return
        
        shares = instruments.shares(
            instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
        )
        
        russian_shares = [
            share
            for share in shares.instruments
            if share.currency == "rub" 
        ]
        
        figi_ticker_df = pd.DataFrame(
            russian_shares,
            columns=['ticker', 'figi']
        )
        for pair in figi_ticker_df.to_dict(orient="records"):
            self.db.update_data(pair['ticker'], pair['figi'])
        
        self.db.save_last_update_time(current_time)
        self.db.save_data_to_file()

    def get_close_prices(self, ticker, days) -> List:
        with self.get_client() as cl:
            close_prices = []
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)

            try:
                for candle in cl.get_all_candles(
                    figi=figi,
                    from_= now() - timedelta(days=days),
                    interval=CandleInterval.CANDLE_INTERVAL_15_MIN,
                    ):
                    close_prices.append(float(quotation_to_decimal(candle.close)))
            except:
                pass
            return close_prices
    
    def get_historical_data(self, ticker, days) -> List:
        with self.get_client() as cl:
            historical_data = []
            figi = self.get_figi_by_ticker(ticker)
            if not figi:
                return Decimal(0)

            try:
                for candle in cl.get_all_candles(
                    figi=figi,
                    from_= now() - timedelta(days=days),
                    interval=CandleInterval.CANDLE_INTERVAL_2_MIN,
                    ):
                    historical_data.append(
                        {
                            'close': float(quotation_to_decimal(candle.close)),
                            'open': float(quotation_to_decimal(candle.open)),
                            'high': float(quotation_to_decimal(candle.high)),
                            'low': float(quotation_to_decimal(candle.low)),
                            'volume': candle.volume
                        }
                        )
            except:
                pass
            return historical_data

    
def main():
    # test_man = TinkoffOrderManager("TickersToFigiRus.json")
    test_man = TinkoffSandboxOrderManager("TickersToFigiRus.json",api_key=Config.TINKOFF_SANDBOX_TOKEN, )
    test_man.buy_stock_for_amount('GAZP', 3000)
    print(test_man.get_portfolio_stocks())
    # for stock in test_man.db.get_data().values():
        # print(stock)
    
    # figi = test_man.get_figi_by_ticker('NKNC')
            
        

if __name__ == "__main__":
    main()