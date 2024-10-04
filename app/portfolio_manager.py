import pandas as pd
from typing import List, Dict
from tinkoff.invest import (
    CandleInterval, Client, MoneyValue,
    OrderDirection, OrderType, InstrumentStatus,
    StopOrderDirection, StopOrderType, StopOrderExpirationType,
    InstrumentIdType
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
                last_price = (client.market_data.get_last_prices(figi=[figi])).last_prices[0].price
                quantity = int(int(amount)//quotation_to_decimal(last_price))
                quantity = min(client.market_data.get_order_book(figi=figi, depth=1).asks[0].quantity, quantity)
                post_order_response = client.orders.post_order(
                    figi=figi,
                    order_id=order_id,
                    quantity=quantity,
                    account_id=self.account_id,
                    direction=OrderDirection.ORDER_DIRECTION_BUY,
                    order_type=OrderType.ORDER_TYPE_MARKET
                )
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
            share_response = client.instruments.share_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, 
                id=figi
            )
        stock_info = {}
        stock_info['lot'] = share_response.instrument.lot
        stock_info['ticker'] = share_response.instrument.ticker
        stock_info['price_step'] = quotation_to_decimal(share_response.instrument.min_price_increment)
        return stock_info
    
    def get_info_by_figi(self, figi: str) -> Dict:
        with self.get_client() as client:
            share_response = client.instruments.share_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, 
                id=figi
            )
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
        
        figi_ticker_df = pd.DataFrame(
            instruments.shares(instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE).instruments,
            columns=['ticker', 'figi']
        )
        for pair in figi_ticker_df.to_dict(orient="records"):
            self.db.update_data(pair['ticker'], pair['figi'])
        
        self.db.save_last_update_time(current_time)
        self.db.save_data_to_file()
      
    
def main():
    test_man = TinkoffOrderManager("TickersToFigi.json")
    # for stock in test_man.get_info_by_ticker('LKOH'):
        # print(stock)
    figi = test_man.get_figi_by_ticker('MTLR')
    with test_man.get_client() as cl:
        print(cl.market_data.get_order_book(figi=figi, depth=1).asks[0].quantity)
    #     last_price = (cl.market_data.get_last_prices(figi=[figi])).last_prices[0].price
    #     print(last_price)
    #     quantity = amount//quotation_to_decimal(last_price)
    #     print(quantity)
    
        
        

if __name__ == "__main__":
    main()