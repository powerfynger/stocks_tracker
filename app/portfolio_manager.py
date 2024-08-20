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

import os, sys

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(script_dir, '..'))

from config import Config
from data_handler import JsonDBHandler

# Изменить на динамические, в заивисимости от ATR 
TAKE_PROFIT_PERCENTAGE = 0.05
STOP_LOSS_PERCENTAGE = -0.02
MIN_PRICE_STEP = 0.02
STOP_ORDER_EXPIRE_DURATION = timedelta(weeks=2)

class TestOrderManager:
    def __init__(self, db_filepath, api_key=Config.TINKOFF_SANDBOX_TOKEN, initial_balance=100000):
        self.api_key = api_key
        self.db = JsonDBHandler(db_filepath)
        
        with SandboxClient(Config.TINKOFF_SANDBOX_TOKEN) as client:
            self.reload_ticker_figi_db(client.instruments)
            
            accounts = client.users.get_accounts().accounts
            if len(accounts) == 0:
                client.sandbox.open_sandbox_account() 
                accounts = client.users.get_accounts().accounts
            self.account_id = accounts[0].id
            
            if len(client.operations.get_positions(account_id=self.account_id).money) == 0:
                self.add_money(client=client, money=initial_balance)
            self.balance = float(
                    quotation_to_decimal(
                        client.operations.get_positions(account_id=self.account_id).money[0]
                    )
            )
            if self.balance < initial_balance:
                self.add_money(client=client, money=initial_balance-self.balance)

    
    def get_balance(self):
        return self.balance
    
    def buy_stock_now(self, ticker: str):
        with SandboxClient(Config.TINKOFF_SANDBOX_TOKEN) as client:
            figi = self.get_figi_by_ticker(ticker)
            # Покупка
            post_order_response = client.sandbox.post_sandbox_order(
                figi=figi,
                quantity=1,
                account_id=self.account_id,
                order_id=datetime.now().strftime("%Y-%m-%dT %H:%M:%S"),
                direction=OrderDirection.ORDER_DIRECTION_BUY,
                order_type=OrderType.ORDER_TYPE_MARKET
            )
            # Тейк-профит
            executed_order_price = money_to_decimal(post_order_response.executed_order_price)
            take_profit_price = executed_order_price * Decimal((1 + TAKE_PROFIT_PERCENTAGE))
            take_profit_price -= take_profit_price % Decimal(MIN_PRICE_STEP)
            take_profit_response = client.stop_orders.post_stop_order(
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
            # Стоп-лосс
            stop_loss_price = executed_order_price * Decimal((1 + STOP_LOSS_PERCENTAGE))
            stop_loss_price -= stop_loss_price % Decimal(MIN_PRICE_STEP)
            take_profit_response = client.stop_orders.post_stop_order(
                quantity=1,
                stop_price=decimal_to_quotation(stop_loss_price),
                direction=StopOrderDirection.STOP_ORDER_DIRECTION_SELL,
                account_id=self.account_id,
                stop_order_type=StopOrderType.STOP_ORDER_TYPE_STOP_LOSS,
                instrument_id=figi,
                expire_date=now() + STOP_ORDER_EXPIRE_DURATION,
                expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_DATE,
            )
            
            
            
        return True
    
    def add_money(self, client, money, currency="rub"):
        money = decimal_to_quotation(Decimal(money))
        return client.sandbox.sandbox_pay_in(
            account_id=self.account_id,
            amount=MoneyValue(units=money.units, nano=money.nano, currency=currency),
        )
        
    def get_figi_by_ticker(self, ticker: str):
        return self.db.get_info_by_ticker(ticker)
    
    def reload_ticker_figi_db(self, instruments: InstrumentsService):
        figi_ticker_df = pd.DataFrame(
            instruments.shares(instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE).instruments,
            columns=['ticker', 'figi']
        )
        for pair in figi_ticker_df.to_dict(orient="records"):
            # print(pair, type(pair))
            self.db.update_data(pair['ticker'], pair['figi'])
        self.db.save_data_to_file()
        

    
def main():
    test_man = TestOrderManager("TickersToFigi.json")
    print(test_man.get_balance())

if __name__ == "__main__":
    main()