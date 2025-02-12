# order_book.py

from datetime import datetime

# Buy and Sell order books, each containing:
# { "stock_ticker": [ [price, quantity], [price, quantity], ... ] }
buy_order_book = {}
sell_order_book = {}

# Orders awaiting processing, sorted by timestamp:
# { "stock_ticker": [ (price, quantity, timestamp), (price, quantity, timestamp) ] }
buy_order_book_awaiting = {}
sell_order_book_awaiting = {}

def add_buy_order(ticker, price, quantity):
    """
    Adds a buy order (price, quantity) to buy_order_book[ticker] and sorts afterward.
    """
    if ticker not in buy_order_book:
        buy_order_book[ticker] = []
    buy_order_book[ticker].append([price, quantity])
    # Sort after modification (lowest price first, as example)
    buy_order_book[ticker].sort(key=lambda x: x[0])

def add_sell_order(ticker, price, quantity):
    """
    Adds a sell order (price, quantity) to sell_order_book[ticker] and sorts afterward.
    """
    if ticker not in sell_order_book:
        sell_order_book[ticker] = []
    sell_order_book[ticker].append([price, quantity])
    # Sort after modification (lowest price first, can adjust logic if needed)
    sell_order_book[ticker].sort(key=lambda x: x[0])

def add_buy_order_awaiting(ticker, price, quantity):
    """
    Adds a buy order to buy_order_book_awaiting[ticker] with timestamp for sorting.
    """
    if ticker not in buy_order_book_awaiting:
        buy_order_book_awaiting[ticker] = []
    buy_order_book_awaiting[ticker].append((price, quantity, datetime.now()))

def add_sell_order_awaiting(ticker, price, quantity):
    """
    Adds a sell order to sell_order_book_awaiting[ticker] with timestamp for sorting.
    """
    if ticker not in sell_order_book_awaiting:
        sell_order_book_awaiting[ticker] = []
    sell_order_book_awaiting[ticker].append((price, quantity, datetime.now()))

def process_awaiting_orders():
    """
    Example of how to process awaiting orders (placeholder).
    Sort by timestamp and move them into main buy/sell order books.
    """
    for ticker, orders in buy_order_book_awaiting.items():
        # Sort by timestamp
        orders.sort(key=lambda x: x[2])
        for order_data in orders:
            add_buy_order(ticker, order_data[0], order_data[1])
    buy_order_book_awaiting.clear()

    for ticker, orders in sell_order_book_awaiting.items():
        # Sort by timestamp
        orders.sort(key=lambda x: x[2])
        for order_data in orders:
            add_sell_order(ticker, order_data[0], order_data[1])
    sell_order_book_awaiting.clear()

