# # order_book.py

# from datetime import datetime

# # Buy and Sell order books, each containing:
# # { "stock_ticker": [ [price, quantity], [price, quantity], ... ] }
# buy_order_book = {}
# sell_order_book = {}

# # Orders awaiting processing, sorted by timestamp:
# # { "stock_ticker": [ (price, quantity, timestamp), (price, quantity, timestamp) ] }
# buy_order_book_awaiting = {}
# sell_order_book_awaiting = {}

# def add_buy_order(ticker, price, quantity):
#     """
#     Adds a buy order (price, quantity) to buy_order_book[ticker] and sorts afterward.
#     """
#     if ticker not in buy_order_book:
#         buy_order_book[ticker] = []
#     buy_order_book[ticker].append([price, quantity])
#     # Sort after modification (lowest price first, as example)
#     buy_order_book[ticker].sort(key=lambda x: x[0])

# def add_sell_order(ticker, price, quantity):
#     """
#     Adds a sell order (price, quantity) to sell_order_book[ticker] and sorts afterward.
#     """
#     if ticker not in sell_order_book:
#         sell_order_book[ticker] = []
#     sell_order_book[ticker].append([price, quantity])
#     # Sort after modification (lowest price first, can adjust logic if needed)
#     sell_order_book[ticker].sort(key=lambda x: x[0])
    
# def cancel_sell_order(ticker, price, quantity):
#     """
#     Cancels a sell order if it exists in the sell order book.
#     Returns True if successful, False otherwise.
#     """
#     if ticker in sell_order_book:
#         for order in sell_order_book[ticker]:
#             if order[0] == price and order[1] == quantity:
#                 sell_order_book[ticker].remove(order)
#                 return True
#     return False

# def add_buy_order_awaiting(ticker, price, quantity):
#     """
#     Adds a buy order to buy_order_book_awaiting[ticker] with timestamp for sorting.
#     """
#     if ticker not in buy_order_book_awaiting:
#         buy_order_book_awaiting[ticker] = []
#     buy_order_book_awaiting[ticker].append((price, quantity, datetime.now()))

# def add_sell_order_awaiting(ticker, price, quantity):
#     """
#     Adds a sell order to sell_order_book_awaiting[ticker] with timestamp for sorting.
#     """
#     if ticker not in sell_order_book_awaiting:
#         sell_order_book_awaiting[ticker] = []
#     sell_order_book_awaiting[ticker].append((price, quantity, datetime.now()))

# def process_awaiting_orders():
#     """
#     Example of how to process awaiting orders (placeholder).
#     Sort by timestamp and move them into main buy/sell order books.
#     """
#     for ticker, orders in buy_order_book_awaiting.items():
#         # Sort by timestamp
#         orders.sort(key=lambda x: x[2])
#         for order_data in orders:
#             add_buy_order(ticker, order_data[0], order_data[1])
#     buy_order_book_awaiting.clear()

#     for ticker, orders in sell_order_book_awaiting.items():
#         # Sort by timestamp
#         orders.sort(key=lambda x: x[2])
#         for order_data in orders:
#             add_sell_order(ticker, order_data[0], order_data[1])
#     sell_order_book_awaiting.clear()
    
from datetime import datetime
import logging
from pymongo import MongoClient, errors
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='matching_engine.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# MongoDB connection
try:
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
    db = client["trading_system"]
    wallets_collection = db["wallets"]
except errors.ConnectionFailure:
    logging.error("Error: Unable to connect to MongoDB. Ensure MongoDB is running.")

class OrderBook:
    def __init__(self):
        self.buy_orders = {}  # { "ticker": [[user_id, price, quantity, timestamp], ...] }
        self.sell_orders = {}  # { "ticker": [[user_id, price, quantity, timestamp], ...] }

    def get_wallet_balance(self, user_id):
        """Fetches wallet balance from MongoDB for the user."""
        try:
            wallet = wallets_collection.find_one({"user_id": user_id}, {"balance": 1})
            if wallet and "balance" in wallet:
                return wallet["balance"]
            return 0  # Default balance if wallet doesn't exist
        except Exception as e:
            logging.error(f"Error fetching wallet balance for {user_id}: {e}")
            return 0

    def update_wallet_balance(self, user_id, amount):
        """Updates the user's wallet balance after a trade."""
        try:
            wallets_collection.update_one(
                {"user_id": user_id},
                {"$inc": {"balance": amount}},  # Deducts if negative, adds if positive
                upsert=True
            )
            logging.info(f"Updated wallet balance for {user_id} by {amount}")
        except Exception as e:
            logging.error(f"Error updating wallet balance for {user_id}: {e}")
            

    def add_buy_order(self, user_id, order_id, stock_id, ticker, price, quantity):
        """ Handles buy orders (limit or market). If market order, executes immediately at best sell price. """
        
        if price is None:  # Market Order
            if ticker not in self.sell_orders or not self.sell_orders[ticker]:
                logging.warning(f"No sellers available for {ticker}. Market order cannot be executed immediately.")
                return {"success": False, "error": "No available sellers for market order"}

            # Take the best available (lowest price) sell order
            best_sell_order = self.sell_orders[ticker][0]
            seller_id, sell_price, sell_quantity, sell_time = best_sell_order

            traded_quantity = min(quantity, sell_quantity)
            trade_value = traded_quantity * sell_price  # Trade happens at sell price

            # Check wallet balance of buyer
            wallet_balance = self.get_wallet_balance(user_id)
            if wallet_balance < trade_value:
                logging.warning(f"User {user_id} has insufficient funds for {traded_quantity} shares of {ticker} at {sell_price}")
                return {"success": False, "error": "Insufficient wallet balance"}

            # Execute trade
            self.update_wallet_balance(seller_id, trade_value)  # Seller receives money
            self.update_wallet_balance(user_id, -trade_value)  # Buyer pays money

            # Update order books
            if sell_quantity > traded_quantity:
                self.sell_orders[ticker][0][2] -= traded_quantity
            else:
                self.sell_orders[ticker].pop(0)  # Remove fully matched sell order

            logging.info(f"BUY MARKET ORDER EXECUTED: {user_id} bought {traded_quantity} shares of {ticker} at {sell_price}")

            return {
                "success": True,
                "message": f"Market order executed: {traded_quantity} shares of {ticker} at {sell_price}",
                "order_status": "COMPLETED",
                "trade_details": {
                    "ticker": ticker,
                    "quantity": traded_quantity,
                    "price": sell_price,
                    "buyer_id": user_id,
                    "seller_id": seller_id,
                    "timestamp": datetime.now().isoformat()
                }
            }

        # If it's a LIMIT order, add to order book
        total_cost = price * quantity
        wallet_balance = self.get_wallet_balance(user_id)

        if wallet_balance < total_cost:
            logging.warning(f"User {user_id} has insufficient funds for {quantity} shares of {ticker} at {price}")
            return {"success": False, "error": "Insufficient wallet balance"}

        if ticker not in self.buy_orders:
            self.buy_orders[ticker] = []
        self.buy_orders[ticker].append([user_id, price, quantity, datetime.now()])
        self.buy_orders[ticker].sort(key=lambda x: (-x[1], x[3]))  # Highest price first, FIFO

        # Deduct money immediately for limit orders
        self.update_wallet_balance(user_id, -total_cost)
        logging.info(f"BUY LIMIT ORDER: {user_id} placed order for {quantity} shares of {ticker} at {price}")

        return {"success": True, "message": "Limit buy order placed successfully"}

    def add_sell_order(self, user_id, order_id, ticker, price, quantity):
        """ Adds a sell order and maintains ascending order of price. """
        if ticker not in self.sell_orders:
            self.sell_orders[ticker] = []
        self.sell_orders[ticker].append([user_id, price, quantity, datetime.now()])
        self.sell_orders[ticker].sort(key=lambda x: (x[1], x[3]))  # Lowest price first, FIFO
        logging.info(f"SELL ORDER: {user_id} listed {quantity} shares of {ticker} at {price}")
        return {"success": True, "message": "Sell order placed successfully"}

    def match_orders(self):
        """ Matches buy and sell orders using FIFO logic. Market orders execute immediately. """
        executed_trades = []

        for ticker in list(self.sell_orders.keys()):  # Start with sell orders
            while self.sell_orders.get(ticker) and self.buy_orders.get(ticker):
                buyer_id, buy_order_id, buy_price, buy_quantity, buy_time, stock_id = self.buy_orders[ticker][0]
                seller_id, sell_order_id, sell_price, sell_quantity, sell_time, stock_id = self.sell_orders[ticker][0]

                # MARKET ORDER: Buy at best available sell price
                if buy_price is None:
                    buy_price = sell_price  # Execute at best available sell price

                traded_quantity = min(buy_quantity, sell_quantity)
                trade_value = traded_quantity * sell_price  # Trade happens at sell price

                executed_trades.append({
                    "ticker": ticker,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "quantity": traded_quantity,
                    "buyer_id": buyer_id,
                    "seller_id": seller_id,
                    "timestamp": datetime.now().isoformat()
                })
                logging.info(f"MATCHED ORDER: {buyer_id} bought {traded_quantity} shares of {ticker} from {seller_id} at {sell_price}")

                # Update wallet balances
                self.update_wallet_balance(seller_id, trade_value)  # Seller receives money
                self.update_wallet_balance(buyer_id, -trade_value)  # Buyer is charged

                # Adjust remaining quantities
                if buy_quantity > traded_quantity:
                    self.buy_orders[ticker][0][2] -= traded_quantity
                else:
                    self.buy_orders[ticker].pop(0)  # Remove fully matched buy order

                if sell_quantity > traded_quantity:
                    self.sell_orders[ticker][0][2] -= traded_quantity
                else:
                    self.sell_orders[ticker].pop(0)  # Remove fully matched sell order

        return executed_trades
# Instantiate a shared order book
orderBookInst = OrderBook()