import json
import os

class JsonDBHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        self.data = self.load_data_from_file()
        self.file = open(self.file_path, 'w')

    def __del__(self):
        self.file.close()

    def load_data_from_file(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as f:
                return json.load(f)
        return {}

    def save_data_to_file(self):
        json.dump(self.data, self.file, indent=4)

    def get_data(self):
        return self.data

    def get_info_by_ticker(self, ticker):
        return self.data[ticker]
    
    def update_data(self, ticker, stock_info):
        self.data[ticker] = stock_info
        self.save_data_to_file()
