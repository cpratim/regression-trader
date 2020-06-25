from controls import *
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.model_selection import train_test_split 
from sklearn import metrics
import os
import numpy as np
from minute import optimize, common, backtest_model, raw_dump, get_data
from threading import Thread
from datetime import datetime, timedelta
from indicators import rsi, macd


class Regression(object):

    def __init__(self):

        self.classifier = RandomForestClassifier()
        self.regressor = RandomForestRegressor()
        self.dump = raw_dump(0, 60)

    def _signalize(self, dump, freq):
        inp, lows, highs = [], [], []
        for data in dump:
            for i in range(len(data)-2*freq+1):
                _in = np.array([c[0:] for c in data[i:freq+i]])
                inp.append(_in.flatten())
                close = _in[-1][2]
                future = (data[freq+i:2*freq+i])
                high, low = max([max(s[1:]) for s in future]), min([min(s[1:]) for s in future])
                high_p, low_p = (high - close)/close, (close - low)/close
                highs.append(high)
                lows.append(low)
        X, Y_high, Y_low = [np.array(l) for l in [inp, highs, lows]]
        return X, Y_high, Y_low

    def generate_model(self, sym, freq):

        low_regressor = RandomForestRegressor()
        high_regressor = RandomForestRegressor()
        symbol_dump = [d[sym] for d in self.dump if sym in d]
        X, Y_high, Y_low = self._signalize(symbol_dump, freq)
        x_train, x_test, y_train, y_test = train_test_split(X, Y_high, test_size=.2, random_state=1)
        high_regressor.fit(x_train, y_train)
        x_train, x_test, y_train, y_test = train_test_split(X, Y_low, test_size=.2, random_state=1)
        low_regressor.fit(x_train, y_train)
        model = RegressionModel(high_regressor, low_regressor)
        return model

    def backtest(self, sym, model, freq):

        test_data = raw_dump(0, 1)[0][sym]
        profit = backtest_model(test_data, freq, model, raw=False)
        print('Profit:', profit)
                

class RegressionModel(object):

    def __init__(self, high_regressor, low_regressor):

        self.high_regressor = high_regressor
        self.low_regressor = low_regressor

    def predict(self, inp):

        _inp = [np.array(inp).flatten()]
        high = self.high_regressor.predict(_inp)[0]
        low = self.low_regressor.predict(_inp)[0]
        return high, low

