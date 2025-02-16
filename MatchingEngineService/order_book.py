
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

# MongoDB connection with retry mechanism
max_retries = 5
retry_delay = 3  # seconds between retries

for attempt in range(max_retries):
    try:
        client = MongoClient(os.getenv("MONGO_URI", "mongodb://mongo:27017/trading_system"), serverSelectionTimeoutMS=5000)
        db = client["trading_system"]
        wallets_collection = db["wallets"]
        portfolios_collection = db["portfolios"]  # Ensure portfolios collection is initialized
        stock_transactions_collection = db["stock_transactions"]  # New collection for transactions

        # Ensure necessary indexes for faster lookups
        stock_transactions_collection.create_index("tx_id", unique=True)  # Use tx_id, not user_id

        logging.info("MongoDB connection established successfully.")
        break  # Exit the loop if connection is successful

    except errors.ConnectionFailure:
        logging.warning(f"MongoDB connection attempt {attempt + 1} failed. Retrying in {retry_delay} seconds...")
        time.sleep(retry_delay)
else:
    logging.error("Failed to connect to MongoDB after multiple attempts. Exiting...")
    raise RuntimeError("MongoDB connection failed after 5 retries.")

class OrderBook:
    def __init__(self):
        self.buy_orders = {}  # { "ticker": [[user_id, price, quantity, timestamp, transaction_id], ...] }
        self.sell_orders = {}  # { "ticker": [[user_id, price, quantity, timestamp, transaction_id], ...] }

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
        """
        Handles a MARKET BUY order in a loop, allowing partial fills.
        1. Continually purchases from the lowest-priced sell order until:
        - The buy quantity is filled, or
        - No more sell orders left, or
        - Buyer runs out of funds.
        2. Logs partial fills vs. completed orders.
        3. Queues leftover (unfilled) quantity if no sellers remain.
        """

        # Make sure it's a market order (price == None).
        # If you *only* allow MARKET buys, you could reject any non-None price.
        if price is not None:
            logging.warning(f"BUY ORDER REJECTED: Limit buy not allowed for {user_id}")
            return {"success": False, "error": "Only market buy orders are allowed"}
        
        # Use the incoming order_id as the parent transaction ID (stock_tx_id)
        parent_tx_id = order_id
        stock_transactions_collection.insert_one({
            "tx_id": parent_tx_id,
            "stock_id": stock_id,
            "ticker": ticker,
            "user_id": user_id,
            "order_type": "MARKET_BUY",
            "original_quantity": quantity,
            "remaining_quantity": quantity,
            "status": "IN_PROGRESS",
            "created_at": datetime.now().isoformat()
        })

        if ticker not in self.sell_orders or not self.sell_orders[ticker]:
            # No sellers available at all -> queue the entire order as unfilled
            # Mark status as INCOMPLETE, and put this buy into a "market buy queue".
            self._queue_market_buy(user_id, parent_tx_id, quantity, ticker)  # We'll define this helper below
            logging.warning(f"BUY MARKET ORDER: No sellers. Queued {quantity} shares for {user_id}.")
            return {
                "success": True,
                "message": "No sellers available. Order queued as market buy.",
                "order_status": "INCOMPLETE",
                "trade_details": [],
                "stock_tx_id": parent_tx_id
            }

        remaining_qty = quantity
        executed_trades = []
        order_status = "INCOMPLETE"  # Will update as we fill

        while remaining_qty > 0 and self.sell_orders.get(ticker):
            # 1. Get best available (lowest price) sell order
            best_sell_order = self.sell_orders[ticker][0]
            seller_id, sell_price, sell_quantity, sell_time = best_sell_order

            # 2. How many shares can we buy from this particular seller?
            trade_qty = min(remaining_qty, sell_quantity)
            trade_value = trade_qty * sell_price

            # 3. Check buyer wallet
            buyer_wallet_balance = self.get_wallet_balance(user_id)
            if buyer_wallet_balance < trade_value:
                # Buyer has insufficient funds to buy 'trade_qty' at 'sell_price'
                # Maybe buyer can buy fewer shares or break out.
                # Usually for a market order, it's "all or partial" until we run out of money.
                max_shares_can_buy = int(buyer_wallet_balance // sell_price)
                if max_shares_can_buy == 0:
                    # If we can't buy even 1 share, we stop
                    logging.warning(f"User {user_id} out of funds. Partially filled so far.")
                    if executed_trades:
                        order_status = "PARTIALLY_COMPLETED"
                    else:
                        order_status = "INCOMPLETE"  # nothing executed
                    break
                else:
                    # We can partially buy some shares from this sell order
                    trade_qty = max_shares_can_buy
                    trade_value = trade_qty * sell_price
                    logging.info(f"User {user_id} can only buy {trade_qty} shares due to insufficient funds.")

            # 4. Execute trade
            self.update_wallet_balance(seller_id, trade_value)   # Seller receives money
            self.update_wallet_balance(user_id, -trade_value)    # Buyer pays money

            # 5. Update order books
            # Reduce the sell order by 'trade_qty'
            if sell_quantity > trade_qty:
                self.sell_orders[ticker][0][2] -= trade_qty
            else:
                # If fully filled, remove it
                self.sell_orders[ticker].pop(0)

            # 6. Update buyer's remaining quantity
            remaining_qty -= trade_qty
            
            # Log partial fill with a new transaction record
            partial_tx_id = str(uuid.uuid4())
            stock_transactions_collection.insert_one({
                "tx_id": partial_tx_id,
                "parent_tx_id": parent_tx_id,
                "stock_id": stock_id,
                "ticker": ticker,
                "quantity": trade_qty,
                "price": sell_price,
                "status": "COMPLETED",
                "buyer_id": user_id,
                "seller_id": seller_id,
                "timestamp": datetime.now().isoformat()
            })

            # 7. Record this partial execution
            executed_trades.append({
                "tx_id": partial_tx_id,
                "parent_tx_id" : parent_tx_id,
                "ticker": ticker,
                "quantity": trade_qty,
                "price": sell_price,
                "buyer_id": user_id,
                "seller_id": seller_id,
                "timestamp": datetime.now().isoformat()
            })

            logging.info(f"BUY MARKET TRADE: {user_id} bought {trade_qty} shares of {ticker} @ {sell_price}")

            # If we've run out of sellers, the loop will break automatically since self.sell_orders[ticker] might be empty

        # End of the while loop
        # Determine the final order status
        filled = quantity - remaining_qty
        if filled == 0:
            # No shares actually bought
            order_status = "INCOMPLETE"
            # Optionally queue the entire order as a market buy
            self._queue_market_buy(user_id, parent_tx_id, remaining_qty, ticker)
        elif remaining_qty > 0:
            # Some portion was filled, but not all
            order_status = "PARTIALLY_COMPLETED"
            # The leftover can also be queued as a market buy if desired
            self._queue_market_buy(user_id, parent_tx_id, remaining_qty, ticker)
        else:
            # All shares were filled
            order_status = "COMPLETED"
            
        # Update parent transaction record with final status and remaining quantity
        stock_transactions_collection.update_one(
            {"tx_id": parent_tx_id},
            {"$set": {"remaining_quantity": remaining_qty, "status": order_status}}
        )

        return {
            "success": True,
            "message": f"Market buy of {quantity} shares of {ticker} processed. {filled} filled.",
            "order_status": order_status,
            "trade_details": executed_trades,
            "stock_tx_id": parent_tx_id
    }

    def _queue_market_buy(self, user_id, order_id, quantity, ticker):
        """
        Helper method to queue leftover market buys if desired.
        For example, you might store them in self.buy_orders[ticker]
        with price=None. This is optional and depends on your design.
        """
        if quantity <= 0:
            return

        # If you want to store leftover as a 'market' entry in the buy book:
        if ticker not in self.buy_orders:
            self.buy_orders[ticker] = []

        # We'll store price as None to represent a market buy
        self.buy_orders[ticker].append([user_id, None, quantity, datetime.now(), order_id])

        # You don't necessarily need to deduct funds here, because
        # no trade is happening yet. The user will pay once a seller appears.

        logging.info(f"Queued leftover market buy for {user_id}: {quantity} shares of {ticker}")

    def get_user_stock_balance(user_id, ticker):
        """Fetches the user's stock balance for a given ticker from MongoDB."""
        try:
            user_stock = wallets_collection.find_one({"user_id": user_id, "stocks.ticker": ticker}, 
                                                    {"stocks.$": 1})
            if user_stock and "stocks" in user_stock:
                return user_stock["stocks"][0]["quantity"]
            return 0  # User does not own this stock
        except Exception as e:
            logging.error(f"Error fetching stock balance for {user_id}, {ticker}: {e}")
            return 0

    def update_user_stock_balance(user_id, ticker, quantity):
        """Subtracts stock quantity from the user's holdings after placing a sell order."""
        try:
            wallets_collection.update_one(
                {"user_id": user_id, "stocks.ticker": ticker},
                {"$inc": {"stocks.$.quantity": -quantity}}  # Subtracts stock quantity
            )
            logging.info(f"Updated stock balance for {user_id}: Sold {quantity} of {ticker}")
            return True
        except Exception as e:
            logging.error(f"Error updating stock balance for {user_id}, {ticker}: {e}")
            return False

    def add_sell_order(self, user_id, order_id, stock_id, price, quantity):
        """ Adds a sell order only if the user has enough stock balance. """

        # Check if user has enough stock in MongoDB
        current_stock_balance = get_user_stock_balance(user_id, stock_id)
        
        # Check if user has enough stock in MongoDB
        user_portfolio = portfolios_collection.find_one(
            {"user_id": user_id, "data.stock_id": ticker},
            {"data.$": 1}  # Fetch only the relevant stock data
        )
        
        if not user_portfolio or not user_portfolio.get("data"):
            logging.warning(f"SELL ORDER FAILED: {user_id} does not own stock {ticker}.")
            return {"success": False, "error": "User does not own this stock."}
        
        #if no error continue
        user_stock = user_portfolio["data"][0]  # Extract stock details
        current_stock_balance = user_stock["quantity_owned"]
        
        if quantity > current_stock_balance:
            logging.warning(f"SELL ORDER FAILED: {user_id} tried to sell {quantity} of {stock_id}, but only has {current_stock_balance}.")
            return {"success": False, "error": "Insufficient stock balance"}

    # Deduct stock from user's portfolio
        result = portfolios_collection.update_one(
            {"user_id": user_id, "data.stock_id": stock_id},
            {"$inc": {"data.$.quantity_owned": -quantity}}
        )
        if result.matched_count == 0:
            logging.error(f"SELL ORDER ERROR: Failed to update portfolio for {user_id}.")
            return {"success": False, "error": "Portfolio update failed"}
        
         # Log sell order in `stock_transactions_collection`
        stock_tx_id = str(uuid.uuid4())  # Unique transaction ID
        stock_transactions_collection.insert_one({
            "tx_id": stock_tx_id,
            "user_id": user_id,
            "stock_id": stock_id,   
            "quantity": quantity,
            "order_type": "SELL",
            "price": price,
            "status": "PENDING",
            "timestamp": datetime.now().isoformat()
        })

        # Add sell order to order book
        if stock_id not in self.sell_orders:
            self.sell_orders[stock_id] = []
        
        self.sell_orders[stock_id].append([user_id, price, quantity, datetime.now(), order_id]) #added order_id
        self.sell_orders[stock_id].sort(key=lambda x: (x[1], x[3]))  # Lowest price first, FIFO

        logging.info(f"SELL ORDER: {user_id} listed {quantity} shares of {stock_id} at {price}")
        return {"success": True, "message": "Sell order placed successfully"}

    def match_orders(self):
        """ Matches buy and sell orders using FIFO logic. Market orders execute immediately. """
        executed_trades = []

        for cur_stock in list(self.sell_orders.keys()):  # Start with sell orders
            while self.sell_orders.get(cur_stock) and self.buy_orders.get(cur_stock):
                buyer_id, buy_price, buy_quantity, buy_time, buy_order_id, stock_id = self.buy_orders[cur_stock][0]
                seller_id, sell_price, sell_quantity, sell_time, sell_order_id, stock_id = self.sell_orders[cur_stock][0]

                # MARKET ORDER: Buy at best available sell price
                if buy_price is None:
                    buy_price = sell_price  # Execute at best available sell price

                traded_quantity = min(buy_quantity, sell_quantity)
                trade_value = traded_quantity * sell_price  # Trade happens at sell price
                
                # Update seller's wallet (add money)
                wallets_collection.update_one(
                    {"user_id": seller_id},
                    {"$inc": {"balance": trade_value}},  # Add the money to seller's balance
                    upsert=True
                )
                
                # Deduct from buyer's wallet
                wallets_collection.update_one(
                    {"user_id": buyer_id},
                    {"$inc": {"balance": -trade_value}},  # Deduct money from buyer's balance
                    upsert=True
                )
                
                    # Add stock to buyer's portfolio
                result = portfolios_collection.update_one(
                    {"user_id": buyer_id, "data.stock_id": stock_id},
                    {"$inc": {"data.$.quantity_owned": traded_quantity}},
                    upsert=False
                )
                
                if result.matched_count == 0:
                    portfolios_collection.update_one(
                        {"user_id": buyer_id},
                        {"$push": {"data": {"stock_id": cur_stock, "quantity_owned": traded_quantity}}},
                        upsert=True
                    )
                    
                 # Log transaction in `stock_transactions_collection`
                stock_tx_id = str(uuid.uuid4())  # Unique transaction ID
                stock_transactions_collection.insert_one({
                    "tx_id": stock_tx_id,
                    "quantity": traded_quantity,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "buyer_id": buyer_id,
                    "seller_id": seller_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "COMPLETED"
                })

                executed_trades.append({
                    "tx_id": stock_tx_id,
                    "quantity": traded_quantity,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "buyer_id": buyer_id,
                    "seller_id": seller_id,
                    "timestamp": datetime.now().isoformat()
                })
                logging.info(f"MATCHED ORDER: {buyer_id} bought {traded_quantity} shares of {cur_stock} from {seller_id} at {sell_price}")

                # # Update wallet balances
                # self.update_wallet_balance(seller_id, trade_value)  # Seller receives money
                # self.update_wallet_balance(buyer_id, -trade_value)  # Buyer is charged

                # Adjust remaining quantities
                if buy_quantity > traded_quantity:
                    self.buy_orders[cur_stock][0][2] -= traded_quantity
                else:
                    self.buy_orders[cur_stock].pop(0)  # Remove fully matched buy order

                if sell_quantity > traded_quantity:
                    self.sell_orders[cur_stock][0][2] -= traded_quantity
                else:
                    self.sell_orders[cur_stock].pop(0)  # Remove fully matched sell order

        return executed_trades
    
    def cancel_user_order(self, user_id, ticker, order_type, transaction_id):
        # Decide which dictionary to check
        is_buy = "BUY" in order_type.upper()
        order_dict = self.buy_orders if is_buy else self.sell_orders

        # 1) Check if the ticker is in the relevant dictionary
        if ticker not in order_dict:
            print(f"No active {'buy' if is_buy else 'sell'} orders for {ticker}. Nothing to cancel.")
            return False, "No active order."
        
        order_list = order_dict[ticker]
        
        # 2) Find the matching order entry by user_id and transaction_id
        found_item = None
        for item in order_list:
            # Example item format: [user_id, price, quantity, timestamp, transaction_id]
            if item[0] == user_id and item[4] == transaction_id:
                found_item = item
                break
        
        if not found_item:
            print(f"Order with transaction_id={transaction_id} not found in {ticker} list.")
            return False, "Transaction ID not found in ticker list"

        # Extract relevant info
        quantity = found_item[2]
        price = found_item[1]

        # 3) Remove the order from the in-memory list
        order_list.remove(found_item)
        print(f"Removed {order_type} order for user={user_id}, ticker={ticker}, tx_id={transaction_id}")

        # 4) Update a transaction/order record in MongoDB to "CANCELLED" 
        self.db["transactions"].update_one(
            {"tx_id": transaction_id, "user_id": user_id},
            {"$set": {"status": "CANCELLED", "cancelled_at": datetime.now.utcnow()}}
            )

        # 5) If it's a SELL order, optionally return quantity to the user's portfolio in MongoDB
        if not is_buy:
            # Doc { "user_id": ..., "stocks": [{ "ticker": "AAPL", "quantity": ...}, ...] }
            self.wallets_collection.update_one(
                {"user_id": user_id, "stocks.ticker": ticker},
                {"$inc": {"stocks.$.quantity": quantity}}
            )
            print(f"Returned {quantity} shares of {ticker} to user {user_id}'s portfolio.")
        
        return True, "Cancellation is complete and successful"

# Instantiate a shared order book
orderBookInst = OrderBook()
