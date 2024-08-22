import json
from datetime import datetime

class JsonDBHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        self.file = open(self.file_path, 'r+')
        self.data = self.load_data_from_file()

    def __del__(self):
        self.file.close()

    def clean_data(self):
        self.data = {}
        self.save_data_to_file()
    
    def load_data_from_file(self):
        try:
            return json.load(self.file)
        except Exception as e:
            print(e)
        return {}

    def save_data_to_file(self):
        with open(self.file_path, 'w') as file:
            json.dump(self.data, file, indent=4)

    def get_data(self):
        return self.data

    def get_info_by_ticker(self, ticker):
        return self.data[ticker]
    
    def get_ticker_by_info(self, stock_info):
        for ticker, info in self.data.items():
            if stock_info == info:
                return ticker
        return None    
    
    def update_data(self, ticker, stock_info):
        self.data[ticker] = stock_info

    def get_last_update_time(self):
        last_update_str = self.data.get('last_update_time')
        if last_update_str:
            return datetime.strptime(last_update_str, "%Y-%m-%d %H:%M:%S")
        return None

    def save_last_update_time(self, current_time):
        # Сохраняем дату последнего обновления в базу данных
        self.data['last_update_time'] = current_time.strftime("%Y-%m-%d %H:%M:%S")

    def close(self):
        self.save_data_to_file()