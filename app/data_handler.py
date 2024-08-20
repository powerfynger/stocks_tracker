import json
import os

class DBHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        self.data = self.load_data_from_file()

    def load_data_from_file(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as f:
                return json.load(f)
        return {}

    def save_data_to_file(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def get_data(self):
        return self.data

    def update_data(self, ticker, stock_info):
        self.data[ticker] = stock_info
        self.save_data_to_file()
