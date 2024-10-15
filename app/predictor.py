import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import root_mean_squared_error


class RFPredictor():
    def __init__(self, window=7):
        self.models = {}
        """
        {
            ticker : 
            {
                hist_data, # Оригинальные данные 'open', 'high', 'low', 'close', 'volume' + значения индикаторов
                model,
                prediction # Последнее рассчитанное значение model.predict
            }
        }
        """
        self.features = ['volatility', 'volume_SMA', 'RSI', 'open', 'high', 'low', 'close', 'volume']
        self.window = window
        
    
    def _create_lags(self, df, n_lags):
        for col in self.features:
            for lag in range(1, n_lags + 1):
                df.loc[:, f'{col}_lag_{lag}'] = df[col].shift(lag)
        
        return df

    def _calculate_rsi(self, data):        
        delta = data['close'].diff(1)
        gain = (delta.where(delta > 0, 0)).rolling(window=self.window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _train_model_predict(self, historical_data):
        historical_data['volatility'] = historical_data['close'].rolling(window=self.window).std()
        historical_data['volume_SMA'] = historical_data['volume'].rolling(window=self.window).mean()
        historical_data['RSI'] = self._calculate_rsi(historical_data)

        # historical_data = historical_data.dropna()

        historical_data = self._create_lags(historical_data, 1)

        # Разделение на признаки и целевую переменную
        X = historical_data.drop(columns=['close'])
        y = historical_data['close']

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

        model = RandomForestRegressor(n_estimators=100)

        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        
        return model, y_pred
    
    def get_prediction_next_close(self, ticker: str, historical_data: list):
        historical_data = pd.DataFrame(historical_data)
        if ticker in self.models:
            if self.models['ticker']['hist_data']['close'].equals(historical_data['close']):
               return self.models['ticker']['prediction'][-1]
            else:
                self.models['ticker']['model'], self.models['ticker']['prediction'] = self._train_model_predict(historical_data)
                return self.models['ticker']['prediction'][-1]
        else:
            model, pred = self._train_model_predict(historical_data)
            self.models['ticker'] = {
                'model' : model,
                'prediction': pred,
                'hist_data': historical_data
            }
            return pred[-1]

    