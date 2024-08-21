import json
import os

class JsonDBHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        self.data = {}
        self.file = open(self.file_path, 'w')

    def __del__(self):
        self.file.close()

    def load_data_from_file(self):
        try:
            return json.load(self.file)
        except BaseException:
            pass
        return {}

    def save_data_to_file(self):
        with open(self.file_path, 'w') as file:
            json.dump(self.data, file, indent=4)

    def get_data(self):
        return self.data

    def get_info_by_ticker(self, ticker):
        return self.data[ticker]
    
    def update_data(self, ticker, stock_info):
        self.data[ticker] = stock_info

    def close(self):
        self.save_data_to_file()