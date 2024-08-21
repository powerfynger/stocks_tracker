import pandas as pd

from tinkoff.invest import (
    CandleInterval, Client, MoneyValue,
    OrderDirection, OrderType, InstrumentStatus,
    StopOrderDirection, StopOrderType, StopOrderExpirationType
    )
from tinkoff.invest.services import SandboxService, InstrumentsService
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
        Метод для покупки акций. Должен быть реализован в подклассах.
        """
        pass

class TinkoffOrderManager(BaseOrderManager):
    def __init__(self, db_filepath, api_key=Config.TINKOFF_REAL_TOKEN):
        super().__init__(api_key)
        self.db = JsonDBHandler(db_filepath)

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

    def buy_stock_now(self, ticker: str):
        with self.get_client() as client:
            order_id = uuid.uuid4().hex
            figi = self.get_figi_by_ticker(ticker)

            # Покупка 
            post_order_response = client.orders.post_order(
                figi=figi,
                order_id=order_id,
                quantity=1,
                account_id=self.account_id,
                direction=OrderDirection.ORDER_DIRECTION_BUY,
                order_type=OrderType.ORDER_TYPE_MARKET
            )

            executed_order_price = money_to_decimal(post_order_response.executed_order_price)
            self.set_take_profit(client, figi, executed_order_price)
            self.set_stop_loss(client, figi, executed_order_price)

        return True

    def set_take_profit(self, client, figi, executed_order_price):
        take_profit_price = executed_order_price * Decimal(1 + TAKE_PROFIT_PERCENTAGE)
        take_profit_price -= take_profit_price % Decimal(MIN_PRICE_STEP)
        client.stop_orders.post_stop_order(
            quantity=1,
            price=decimal_to_quotation(take_profit_price),
            stop_price=decimal_to_quotation(take_profit_price),
            direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL,
            account_id=self.account_id,
            stop_order_type=StopOrderType.STOP_ORDER_TYPE_TAKE_PROFIT,
            instrument_id=figi,
            expire_date=now() + STOP_ORDER_EXPIRE_DURATION,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_DATE,
        )

    def set_stop_loss(self, client, figi, executed_order_price):
        stop_loss_price = executed_order_price * Decimal(1 + STOP_LOSS_PERCENTAGE)
        stop_loss_price -= stop_loss_price % Decimal(MIN_PRICE_STEP)
        client.stop_orders.post_stop_order(
            quantity=1,
            stop_price=decimal_to_quotation(stop_loss_price),
            direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL,
            account_id=self.account_id,
            stop_order_type=StopOrderType.STOP_ORDER_TYPE_STOP_LOSS,
            instrument_id=figi,
            expire_date=now() + STOP_ORDER_EXPIRE_DURATION,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_DATE,
        )  
    
    def get_figi_by_ticker(self, ticker: str):
        return self.db.get_info_by_ticker(ticker)

    def reload_ticker_figi_db(self, instruments):
        figi_ticker_df = pd.DataFrame(
            instruments.shares(instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE).instruments,
            columns=['ticker', 'figi']
        )
        for pair in figi_ticker_df.to_dict(orient="records"):
            self.db.update_data(pair['ticker'], pair['figi'])
        self.db.save_data_to_file()
      


    
def main():
    test_man = TinkoffOrderManager("TickersToFigi.json")
    print(test_man.get_balance())

if __name__ == "__main__":
    main()