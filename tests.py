import alpaca_trade_api as alpaca


KEY = ''
SECRET = ''
base = 'https://paper-api.alpaca.markets'
client = alpaca.REST(KEY, SECRET, base)

'''
o = client.submit_order(symbol='AAPL', 
                    	side='buy', 
                    	type='limit', 
                 		limit_price=430, 
                 		qty=1, 
                 		time_in_force='day',
                 		take_profit=dict(
                                    limit_price=440,
                        ),
                        stop_loss=dict(
                        	limit_price=300,
                        	))

print(o)
'''
def get_order(sym):
	for order in client.list_orders():
		if order.symbol == sym:
			return order

print(get_order('AAPL'))