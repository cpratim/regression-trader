from alpaca_trade_api import REST as AlpacaRest
from time import sleep
from datetime import datetime, timedelta
import numpy as np
from polygon import AlpacaSocket, PolygonRest
from math import floor
import sys
import re
import json
from threading import Thread
from functions import *
from config import KEY_LIVE
from indicators import rsi, macd
from genstat import GenerativeStatistics
#import auto_push

KEY = 'PKE9M0ES661ICMMM7GRN'
SECRET = 'jAPts72bGtfJjYDlW7t8ptHLjHjYs3DL7Z/fWk7G'

def date():
    return str(datetime.now())[:10]

def timestamp():
    return str(datetime.now())[11:19]

def read_data(f):
    with open(f, 'r') as df:
        return json.loads(df.read())

def now():
    return datetime.now()

def until_open():
    now = datetime.now()
    y, m, d = [int(s) for s in str(now)[:10].split('-')]
    market_open = datetime(y, m, d, 10, 5)
    return ((market_open - now).seconds)

def market_close(unix):
    t = datetime.fromtimestamp(unix)
    y, m, d = [int(s) for s in date().split('-')]
    return((datetime(y, m, d, 16, 0, 0) - t).seconds)

def market_open():
    now = datetime.now()
    y, m, d = [int(s) for s in str(now)[:10].split('-')]
    mo = datetime(y, m, d, 9, 30)
    return mo

def until_close(now):
    y, m, d = [int(s) for s in str(now)[:10].split('-')]
    return((datetime(y, m, d, 16, 0, 0) - now).seconds)


class AlgoBot(object):

    def __init__(self, symbols, funds=5000, wait=True,  
                margin=.005, freq=15, sleeptime=5, sandbox=True):

        print('Starting Model Training')
        base = 'https://api.alpaca.markets'
        mins = 6.5 * 60
        if sandbox is True: base = 'https://paper-api.alpaca.markets'
        self.client = AlpacaRest(KEY, SECRET, base)
        self.polygon = PolygonRest(KEY_LIVE)
        self.margin = margin
        self.regression = Regression()
        self.symbols = symbols
        self.freq = freq
        self.pending = []
        self.alert = '({}) [+] {} {} shares of {} at {} per share \n'
        self.sleeptime = sleeptime
        self.active, self.models, self.barsets, self.funds = [{} for i in range(4)]
        for sym in self.symbols:
            self.funds[sym] = funds/(len(self.symbols))
            print(f'Training Model for [{sym}]')
            model = self.regression.generate_model(sym=sym, 
                                                   freq=self.freq)
            self.models[sym] = model
        print('All Models Generated \n')
        if wait is True:
            self._wait()

    def start(self):

        Thread(target=self._barset_updater).start()
        sleep(1)
        for sym in self.symbols:
            Thread(target=self.ticker, args=(sym,)).start()

    def ticker(self, sym):

        clock = 0
        while until_close(now()) > 60:

            latest_price = self.polygon.get_last_price(sym)
            if sym not in self.active:

                bars = self.barsets[sym]
                high_prediction, low_prediction = self.models[sym].predict(bars)
                percentage = (latest_price - low_prediction)/latest_price
                if low_prediction > self.margin:
                    if sym not in self.pending:
                        self.pending.append(sym)
                        qty = floor(self.funds[sym]/latest_price)
                        args = (sym, qty, low_prediction, high_prediction)
                        Thread(target=self._buy, args=args).start()

            else:

                a = self.active[sym]
                _id, qty, type_, max_time, high, sell = (a['id'], a['qty'], 
                                                         a['type'], a['max_time'], 
                                                         a['high'], a['sell'])
                fill_price = self._fill(_id)
                if fill_price is not None:
                    if type_ == 'buy':
                        print(self.alert.format(timestamp(), 
                                                'Bought', qty,
                                                sym, fill_price,))
                        self.pending.append(sym)
                        self.funds[sym] -= qty * fill_price
                        Thread(target=self._sell, args=(sym, qty, sell)).start()
                        
                    else:
                        print(self.alert.format(timestamp(), 
                                                'Sold', qty,
                                                sym, fill_price,))
                        self.funds[sym] += qty * fill_price
                        del self.active[sym]
                else:
                    if latest_price > high and type_ == 'buy':
                        self.client.cancel_order(_id)
                        del self.active[sym]

                    elif (max_time - now()).seconds > 80000:
                        if type_ == 'buy':
                            self.client.cancel_order(_id)
                        elif type_ == 'sell' and sym not in self.pending:
                            self.pending.append(sym)
                            Thread(target=self._sell, args=(sym, qty,)).start()
                        del self.active[sym]

            clock += self.sleeptime
            sleep(self.sleeptime) 

        self._liquidate()

    def _barset_updater(self):
        
        while until_close(now()) > self.freq * 60:
            bars = self.client.get_barset(
                    symbols=self.symbols, 
                    timeframe='minute', 
                    limit=self.freq)
            for sym in self.symbols:
                self.barsets[sym] = self._handle(bars[sym])
            sleep(60)

    def _handle(self, bars):
        out = []
        for b in bars:
            out.append([b.v, b.o, b.c, b.h, b.l])
        return out
        
    def _log(self, error):

        print(f'Error at [{timestamp()}]:')
        print(error)
        return

    def _buy(self, sym, qty, price, high):

        try:
            profit = price * (1 + self.margin)
            order = self.client.submit_order(
                                symbol=sym, side='buy', 
                                type='limit', limit_price=price, 
                                qty=qty, time_in_force='day',)
            max_time = now() + timedelta(minutes=self.freq)
            self.active[sym] = {'type': 'buy',
                                'max_time': max_time,
                                'id': order.id,
                                'qty': qty,
                                'bought': price, 
                                'sell': profit,
                                'high': high}
            self.pending.remove(sym)
        except Exception as error:
            self._log(error)
            return None
        return price

    def _sell(self, sym, qty, price=None):

        if price is not None:
            try:
                order = self.client.submit_order(
                                    symbol=sym, side='sell', 
                                    type='limit', limit_price=price, 
                                    qty=qty, time_in_force='day',)
                self.active[sym]['type'] = 'sell'
                self.active[sym]['id'] = order.id
                self.pending.remove(sym)
                return 
            except Exception as error:
                self._log(error)
                return 
        else:
            try:
                order = self.client.submit_order(
                                    symbol=sym, side='sell', 
                                    type='market', qty=qty, 
                                    time_in_force='day')

                _id = order.id
                tries = 0
                while self._fill(_id) is None:
                    sleep(2)
                    tries += 1
                    if tries == 5:
                        self.client.cancel_order(_id)
                        self.pending.remove(symbol)
                        return None
                fill_price = self._fill(_id)
                print(self.alert.format(timestamp(), 
                                        'Sold', qty,
                                        sym, fill_price,))

            except Exception as error:
                self._log(error)
            
        return 

    def _fill(self, _id):
        fill_price = self.client.get_order(_id).filled_avg_price
        return float(fill_price) if fill_price is not None else None

    def _wait(self):
        time = until_open()
        print(f'Sleeping {time} seconds until Market Open')
        sleep(time)
        print(f'Starting Bot at {now()} \n')

    def _liquidate(self):
        for order in self.client.list_orders():
            self.client.cancel_order(order.id)
        for position in self.client.list_positions():
            qty = int(position.qty)
            sym = position.symbol
            self.pending.append(s)
            Thread(target=self._sell, args=(sym, qty)).start()
            pass


symbols = ['MRO', 'NCLH', 'ERI', 'PLAY', 'SAVE']
ab = AlgoBot(symbols=symbols, wait=True)
ab.start()
