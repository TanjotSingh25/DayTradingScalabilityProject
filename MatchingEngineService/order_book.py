import time
from datetime import datetime
import logging
from pymongo import MongoClient, errors, UpdateOne
import os
from dotenv import load_dotenv
from uuid import uuid4
import redis

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='matching_engine.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

cur_best_stock_prices = {}
# MongoDB connection with retry mechanism
max_retries = 5
retry_delay = 3

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Make sure it's defined in docker-compose.yml.")

for attempt in range(max_retries):
    try:
        # 1.5 minutes
        client = MongoClient(MONGO_URI, maxPoolSize=250, minPoolSize=50, maxIdleTimeMS=90000)
        # Initialize to mongodb client, and to the collections
        db = client["trading_system"]
        portfolios_collection = db["portfolios"]
        # New collection for transactions
        stock_transactions_collection = db["stock_transactions"]
        wallet_transactions_collection = db["wallets_transaction"]
        stocks_collection = db["stocks"]
        # Ensure necessary indexes for faster lookups
        stock_transactions_collection.create_index("stock_tx_id", unique=True)
        wallet_transactions_collection.create_index("user_id", unique = True)

        logging.info("MongoDB connection established successfully.")
        break

    except errors.ConnectionFailure:
        logging.warning(f"MongoDB connection attempt {attempt + 1} failed. Retrying in {retry_delay} seconds...")
        time.sleep(retry_delay)
else:
    logging.error("Failed to connect to MongoDB after multiple attempts. Exiting...")
    raise RuntimeError("MongoDB connection failed after 5 retries.")

# Attempt to connect to Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis_wallet_cache")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

if not REDIS_HOST:
    raise RuntimeError("REDIS_HOST is not set. Make sure it's defined in docker-compose.yml.")
if not REDIS_PORT:
    raise RuntimeError("REDIS_PORT is not set. Make sure it's defined in docker-compose.yml.")

for attempt in range(5):
    try:
        # decode = Convert to Python Strings
        # Create the connection pool with max connections, if there are too many connections,
        # redis can refuse new connections
        pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=0, max_connections=250)
        # Create Redis client using the connection pool
        redis_client = redis.StrictRedis(connection_pool=pool, decode_responses=True)
        #redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        logging.info("Redis connection established successfully on Order Service.")
        break
    except Exception as err:
        print(f"Error Connecting to Redis, retrying. Error: {err}")
        time.sleep(2)
    pass
else:
    logging.error("Failed to connect to Redis after multiple attempts. Exiting...")
    raise RuntimeError("Redis connection failed after 5 retries.")
class OrderBook:
    def __init__(self):
        # self.buy_orders[stock_id].append([user_id, price, quantity, datetime.now(), order_id])
        self.buy_orders = {}
        # { "ticker": [[user_id, price, quantity, timestamp (datetime.now()), transaction_id], ...] }
        self.sell_orders = {}  

    def get_wallet_balance(self, user_id):
        """
            Fetches wallet balance from Redis for the given user_id.
            Returns the balance as an integer; if not found, returns 0.
        """
        try:
            balance = redis_client.get(f"wallet_balance:{user_id}")
            return int(float(balance)) if balance else 0
        except Exception as e:
            logging.error(f"Error fetching wallet balance for {user_id}: {e}")
            return 0

    def update_wallet_balance(self, buyer_id, seller_id, trade_value):
        """
        Updates both the buyer's and seller's wallet balances in Redis atomically.
        The seller's balance is incremented by trade_value while the buyer's is decremented by trade_value.
        Ensures that if the wallet key does not exist, it is first initialized to 0.
        """
        try:
            pipe = redis_client.pipeline()
            buyer_key = f"wallet_balance:{buyer_id}"
            seller_key = f"wallet_balance:{seller_id}"
            
            # Ensure wallet keys exist by setting them to 0 if not already present
            if redis_client.get(buyer_key) is None:
                pipe.set(buyer_key, 0)
            if redis_client.get(seller_key) is None:
                pipe.set(seller_key, 0)
                
            # Perform both balance updates in one atomic pipeline call
            pipe.incrbyfloat(seller_key, trade_value)
            pipe.incrbyfloat(buyer_key, -trade_value)
            pipe.execute()
            
            logging.info(f"Updated wallet balances: buyer {buyer_id} by {-trade_value}, seller {seller_id} by {trade_value}")
        except Exception as err:
            logging.error(f"Error updating wallet balances for buyer {buyer_id} and seller {seller_id}: {err}")

    # def update_wallet_balance(self, user_id, amount):
    #     """
    #     Updates the user's wallet balance in Redis by incrementing it by 'amount'.
    #     Ensures that the wallet key exists by setting it to 0 if it is not present.
    #     """
    #     try:
    #         # Initialize the balance to 0 if the key does not exist
    #         if redis_client.get(f"wallet_balance:{user_id}") is None:
    #             redis_client.set(f"wallet_balance:{user_id}", 0)
    #         # Increment the wallet balance by the given amount
    #         redis_client.incrbyfloat(f"wallet_balance:{user_id}", amount)
    #         logging.info(f"Updated wallet balance for {user_id} by {amount}")
    #     except Exception as err:
    #         logging.error(f"Error updating wallet balance for {user_id}: {err}")
    def update_wallet_balance(self, user_id, amount):
        """
        Updates the user's wallet balance in Redis by incrementing it by 'amount'.
        Ensures that the wallet key exists by setting it to 0 if it is not present.
        Logs the balance before and after the increment.
        """
        key = f"wallet_balance:{user_id}"
        try:
            # Initialize the balance to 0 if the key does not exist
            if redis_client.get(key) is None:
                redis_client.set(key, 0)
            #make this int?s
            # Get the balance before increment and convert to float
            before_balance = float(redis_client.get(key))
            logging.info(f"Wallet balance for {user_id} before increment: {before_balance}")

            # Increment the wallet balance by the given amount
            redis_client.incrbyfloat(key, amount)

            # Get the balance after increment
            after_balance = float(redis_client.get(key))
            logging.info(f"Wallet balance for {user_id} after increment: {after_balance} (incremented by {amount})")
        except Exception as err:
            logging.error(f"Error updating wallet balance for {user_id}: {err}")

    def add_buy_order(self, user_id, stock_id, price, quantity):
        """
        Handles a MARKET BUY order in a loop, allowing partial fills.
        Go until buy quantity is filled, no more sell order left (queue), or buyer runs out of funds
        """        
        # unique transaction IDs for parent_tx_id which the child transactions will point to.
        parent_tx_id = str(uuid4())
        global cur_best_stock_prices
        stock_transactions_collection.insert_one({
            "stock_tx_id": parent_tx_id,
            "parent_stock_tx_id": None,  # Explicitly setting parent_stock_tx_id as null, only child transactions set this.
            "stock_id": stock_id,
            "wallet_tx_id": None,  # Only set after order_status is completed
            "user_id": user_id,
            "order_status": "IN_PROGRESS",
            "is_buy": True,  # Market BUY = is_buy = True
            "order_type": "MARKET",
            "stock_price": price,
            "quantity": quantity,
            "time_stamp": datetime.now().isoformat()
        })

        # No sellers available at all (Mark status as INCOMPLETE) -> queue the entire order as unfilled
        if stock_id not in self.sell_orders or not self.sell_orders[stock_id]:
            self._queue_market_buy(user_id, None, quantity, parent_tx_id, stock_id) 
            logging.warning(f"BUY MARKET ORDER: No sellers. Queued {quantity} shares for User:{user_id}.")
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

        # 1. Get best available (lowest price) sell order
        while remaining_qty > 0 and self.sell_orders.get(stock_id):
            wallet_tx_id = str(uuid4())
            best_sell_order = self.sell_orders[stock_id][0]
            # Extract all values from sell_orders dictionary
            seller_id, sell_price, sell_quantity, sell_time, seller_tx_id = best_sell_order

            valid_sell_index = None
            for idx, order in enumerate(self.sell_orders[stock_id]):
                seller_id, sell_price, sell_quantity, sell_time, seller_tx_id = order
                # Buyer cannot be the same as the seller
                if seller_id != user_id:
                    valid_sell_index = idx
                    break

            # If none found, no valid sellers
            if valid_sell_index is None:
                logging.warning(f"No valid sellers for user {user_id} (self-trade skipped).")
                break

            seller_id, sell_price, sell_quantity, sell_time, seller_tx_id = \
                self.sell_orders[stock_id][valid_sell_index]
            
            # Max amount of stocks that can be purchased in this transaction.
            trade_qty = min(remaining_qty, sell_quantity)
            trade_value = trade_qty * sell_price

            # 3. Check buyer wallet by querying wallet db
            buyer_wallet_balance = self.get_wallet_balance(user_id)
            if buyer_wallet_balance < trade_value:
                max_shares_can_buy = buyer_wallet_balance // sell_price
                if max_shares_can_buy == 0:
                    logging.warning(f"User {user_id} out of funds. Partially filled so far.")
                    order_status = "PARTIALLY_COMPLETED" if executed_trades else "INCOMPLETE"
                    break
                else:
                    # We can partially buy some shares from this sell order
                    trade_qty = max_shares_can_buy
                    trade_value = trade_qty * sell_price
                    logging.info(f"User {user_id} can only buy {trade_qty} shares due to insufficient funds.")
                    
            # Update user portfolio (buyer gets stocks)
            r = self.update_user_stock_balance(user_id, stock_id, trade_qty)
            if r == False:
                return {"success": False, "error": "updateStockBalance,Returned false"}

            # 4. Execute trade, update balance in mongodb wallets collection
            self.update_wallet_balance(seller_id, trade_value)   # Seller receives money
            self.update_wallet_balance(user_id, -trade_value)    # Buyer pays money

            # 5. Update order books by adding stock quantity and removing order from sell_orders
            if sell_quantity > trade_qty:
                self.sell_orders[stock_id][0][2] -= trade_qty
            else:
                # If fully filled, remove it
                self.sell_orders[stock_id].pop(0)
                if self.sell_orders[stock_id]:
                    cur_best_stock_prices[stock_id] = self.sell_orders[stock_id][0]
                else:
                    del cur_best_stock_prices[stock_id]
            # 6. Update buyer's remaining quantity
            remaining_qty -= trade_qty
            
            # Log partial fill with a new transaction record
            partial_tx_id = str(uuid4())
            date_time = datetime.now().isoformat()
            stock_transactions_collection.insert_one({
                "stock_tx_id": partial_tx_id,
                "parent_stock_tx_id": parent_tx_id, #if remaining_qty > 0 else None,
                "stock_id": stock_id,
                "wallet_tx_id": wallet_tx_id,
                "quantity": trade_qty,
                "stock_price": sell_price,
                "order_status": "COMPLETED",
                "is_buy": True,
                "user_id": user_id,
                "seller_id": seller_id,
                "time_stamp": date_time
            })

            # Initialize transactions of wallet transactions in list
            transactions = [
                UpdateOne(
                    {"user_id": user_id},
                    {
                        "$push": {
                            "transactions": {
                                "stock_tx_id": parent_tx_id,
                                "wallet_tx_id": wallet_tx_id,
                                "is_debit": True,
                                "amount": trade_value,
                                "time_stamp": date_time
                            }
                        }
                    },
                    upsert=True
                ),
                UpdateOne(
                    {"user_id": seller_id},
                    {
                        "$push": {
                            "transactions": {
                                "stock_tx_id": parent_tx_id,
                                "wallet_tx_id": wallet_tx_id,
                                "is_debit": False,
                                "amount": trade_value,
                                "time_stamp": date_time
                            }
                        }
                    },
                    upsert=True
                )
            ]

            # Execute bulk operation
            wallet_transactions_collection.bulk_write(transactions)

            # 7. Record this partial execution
            executed_trades.append({
                "stock_tx_id": partial_tx_id,
                "parent_stock_tx_id": parent_tx_id, # if remaining_qty > 0 else None,
                "stock_id": stock_id,
                "wallet_tx_id": wallet_tx_id,
                "quantity": trade_qty,
                "stock_price": sell_price,
                "buyer_id": user_id,
                "seller_id": seller_id,
                "time_stamp": datetime
            })
            logging.info(f"BUY MARKET TRADE: User:{user_id} bought {trade_qty} shares of {stock_id} @ {sell_price}")

        # End of the while loop - Determine the final order status
        filled = quantity - remaining_qty
        if filled == 0:
            # No shares actually bought
            order_status = "INCOMPLETE"
            # Thus queue market buy order
            self._queue_market_buy(user_id, None, remaining_qty, parent_tx_id, stock_id)
            # Update parent transaction (no fill, keep price=None)
            stock_transactions_collection.update_one(
                {"stock_tx_id": parent_tx_id},
                {"$set": {
                    "remaining_quantity": remaining_qty,
                    "order_status": order_status
                }}
            )
        else:
            if remaining_qty > 0:
                # Some portion was filled, but not all
                order_status = "PARTIALLY_COMPLETED"
                # The leftover can also be queued as a market buy if desired
                self._queue_market_buy(user_id, None, remaining_qty, parent_tx_id, stock_id)
            else:
                # All shares filled
                order_status = "COMPLETED"
                total_cost = 0
                total_shares = 0
                for trade in executed_trades:
                    total_cost += trade["quantity"] * trade["stock_price"]
                    total_shares += trade["quantity"]
                avg_fill_price = total_cost / total_shares if total_shares else 0
                avg_fill_price_int = int(avg_fill_price)

                # Update parent transaction record with final status and remaining quantity
                stock_transactions_collection.update_one(
                    {"stock_tx_id": parent_tx_id},
                    {"$set": {
                        "remaining_quantity": remaining_qty,
                        "order_status": order_status,
                        "stock_price": avg_fill_price_int,  # <--- Now numeric, NOT None
                        "wallet_tx_id": wallet_tx_id
                    }}
                )

        return {
            "success": True,
            "message": f"Market buy of {quantity} shares of {stock_id} processed. {filled} filled.",
            "order_status": order_status,
            "trade_details": executed_trades,
            "stock_tx_id": parent_tx_id
    }

    def _queue_market_buy(self, user_id, price, quantity, order_id, stock_id):
        # Helper method to queue leftover market buy orders
        if quantity <= 0:
            return
        # If you want to store leftover as a 'market' entry in the buy book:
        if stock_id not in self.buy_orders:
            self.buy_orders[stock_id] = []

        # store price as None to represent a market buy
        self.buy_orders[stock_id].append([user_id, price, quantity, datetime.now(), order_id])
        # No deduction of funds, because no order has been completed
        logging.info(f"Queued leftover market buy for user: {user_id}: {quantity} shares of {stock_id}")

    # gets the stock info from the portflio collectoion in the db mongo
    def get_user_stock_balance(self, user_id, stock_id):
        # Fetches the user's stock balance for a given stock_id from MongoDB portfolios collection
        try:
            user_portfolio = portfolios_collection.find_one(
                {"user_id": user_id, "data.stock_id": stock_id},
                # Postional operator
                {"data.$": 1}
            )

            # # Extract stock quantity
            if user_portfolio and "data" in user_portfolio and len(user_portfolio["data"]) > 0:
                return user_portfolio["data"][0]["quantity_owned"]  
            # User does not own this stock
            return 0  
        except Exception as e:
            logging.error(f"Error fetching stock balance for {user_id}, {stock_id}: {e}")
            return 0

    def update_user_stock_balance(self, user_id, stock_id, quantity):
        """
        Works for both BUY (quantity>0) and SELL (quantity<0).
        Removes the stock from 'data' if new quantity is 0.
        """
        try:
            # 1) Attempt to increment the existing stock entry
            result = portfolios_collection.update_one(
                {"user_id": user_id, "data.stock_id": stock_id},
                {"$inc": {"data.$.quantity_owned": quantity}}
            )

            if result.matched_count == 0:
                # 2) Fallback if it's a brand-new BUY
                if quantity > 0:
                    # Fetch the stock name from stocks_collection
                    stock_doc = stocks_collection.find_one({"stock_id": stock_id}, {"stock_name": 1})
                    stock_name = stock_doc["stock_name"] if stock_doc else "Unknown"

                    portfolios_collection.update_one(
                        {"user_id": user_id},
                        {
                            "$push": {
                                "data": {
                                    "stock_id": stock_id,
                                    "stock_name": stock_name,
                                    "quantity_owned": quantity
                                }
                            }
                        },
                        upsert=True
                    )
                    logging.info(f"Created new stock {stock_id} with quantity={quantity} for user {user_id}")
                    return True
                else:
                    # User doesn't own stock
                    logging.warning(f"Sell order failed: user {user_id} doesn't own stock {stock_id}")
                    return False

            # 3) After the increment, check if the quantity is now 0
            updated_doc = portfolios_collection.find_one(
                {"user_id": user_id, "data.stock_id": stock_id},
                {"data.$": 1}
            )
            if updated_doc and "data" in updated_doc:
                new_qty = updated_doc["data"][0].get("quantity_owned", 0)
                if new_qty <= 0:
                    # Remove stock from data array
                    portfolios_collection.update_one(
                        {"user_id": user_id},
                        {"$pull": {"data": {"stock_id": stock_id}}}
                    )
                    logging.info(f"Removed stock {stock_id} from user {user_id}'s portfolio (qty=0).")

            logging.info(f"Updated stock balance for user {user_id}: {quantity} shares of {stock_id}")
            return True

        except Exception as e:
            logging.error(f"Error updating stock balance for user: {user_id}, {stock_id}: {e}")
            return False

    def add_sell_order(self, user_id, stock_id, price, quantity):
        # Add sell order only if have enough quantity
        global cur_best_stock_prices
        # Get the user's stock balance (returns an integer)
        stock_balance = self.get_user_stock_balance(user_id, stock_id)

        # Ensure user has enough stock
        if stock_balance <= 0:
            logging.warning(f"SELL ORDER FAILED USER: {user_id} does not own stock {stock_id}.")
            return {"success": False, "error": "User does not own this stock."}

        # Amount you want to sell is more than the amount you want to sell
        if quantity > stock_balance:
            logging.warning(f"SELL ORDER FAILED USER: {user_id} tried to sell {quantity} of {stock_id}, but only has {stock_balance}.")
            return {"success": False, "error": "Insufficient stock balance."}

        # Deduct stock from user's portfolio
        result = self.update_user_stock_balance(user_id, stock_id, -quantity)

        if result == False:
            logging.error(f"SELL ORDER ERROR: Failed to update portfolio for User: {user_id}.")
            return {"success": False, "error": "Portfolio update failed."}

        # Insert order into stock_transactions_collection
        st_tx_id = str(uuid4())
        try:
            stock_transactions_collection.insert_one({
                "stock_tx_id": st_tx_id,
                "parent_stock_tx_id": None,
                "stock_id": stock_id,
                "wallet_tx_id": None,
                "user_id": user_id,
                "order_status": "IN_PROGRESS",
                "is_buy": False,
                "order_type": "LIMIT",
                "stock_price": price,
                "quantity": quantity,
                "time_stamp": datetime.now().isoformat()
            })
        except errors.DuplicateKeyError:
            logging.error(f"DUPLICATE KEY ERROR: stock_tx_id={st_tx_id} already exists. Retrying...")
            return {"success": False, "error": "Duplicate stock transaction ID. Try again."}

        # Add the sell order to in-memory order book
        if stock_id not in self.sell_orders:
            self.sell_orders[stock_id] = []
        self.sell_orders[stock_id].append([user_id, price, quantity, datetime.now(), st_tx_id])

        # Ensure orders are sorted (Lowest price first, FIFO for equal prices)
        self.sell_orders[stock_id].sort(key=lambda x: (x[1], x[3]))
        cur_best_stock_prices[stock_id] = self.sell_orders[stock_id][0]

        logging.info(f"SELL ORDER USER: {user_id} listed {quantity} shares of {stock_id} at {price}")
        return {"success": True, "message": "Sell order placed successfully"}

    def match_orders(self):
        # Matches buy and sell orders using FIFO logic. Market orders execute immediately
        executed_trades = []
        global cur_best_stock_prices
        # For loop to go through sell orders until all market buys are executed
        for cur_stock in list(self.sell_orders.keys()):
            while self.sell_orders.get(cur_stock) and self.buy_orders.get(cur_stock):
                buyer_id, buy_price, buy_quantity, buy_time, buy_order_id = self.buy_orders[cur_stock][0]
                seller_id, sell_price, sell_quantity, sell_time, sell_order_id = self.sell_orders[cur_stock][0]
                
                # 2) Find the first valid seller (skipping self-trade orders)
                valid_sell_index = None
                for idx, order in enumerate(self.sell_orders[cur_stock]):
                    sid, sprice, squantity, stime, sorder_id = order
                    if sid != buyer_id:  # Skip if the same user
                        valid_sell_index = idx
                        break

                # If no valid seller found, break out
                if valid_sell_index is None:
                    logging.warning(f"No valid sellers for buyer {buyer_id} (self-trade skipped).")
                    break

                # Extract the valid sell order
                seller_id, sell_price, sell_quantity, sell_time, sell_order_id = \
                    self.sell_orders[cur_stock][valid_sell_index]

                # MARKET ORDER: Buy at best available sell price
                if buy_price is None:
                    buy_price = sell_price

                traded_quantity = min(buy_quantity, sell_quantity)
                trade_value = traded_quantity * sell_price  # Trade happens at sell price
                wallet_tx_id = str(uuid4()) #unique wallet transaction id

                # Update seller's wallet balance (add money)
                self.update_wallet_balance(seller_id, trade_value)  
                # Deduct money from buyer's wallet
                self.update_wallet_balance(buyer_id, -trade_value)  

                # Add stock to buyer's portfolio
                result = portfolios_collection.update_one(
                    {"user_id": buyer_id, "data.stock_id": cur_stock},
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
                stock_tx_id = str(uuid4())  # Unique transaction ID
                cur_date_time = datetime.now().isoformat()
                stock_transactions_collection.insert_one({
                    "stock_tx_id": stock_tx_id,
                    "parent_stock_tx_id": None,  # If this is a partial order, update later
                    "stock_id": cur_stock,
                    "wallet_tx_id": wallet_tx_id, 
                    "quantity": traded_quantity,
                    "stock_price": sell_price,
                    "order_status": "COMPLETED",  
                    "is_buy": True,  
                    "buyer_id": buyer_id,
                    "seller_id": seller_id,
                    "time_stamp": cur_date_time
                })
                # Initialize transactions of wallet transactions in list
                transactions = [
                    UpdateOne(
                        {"user_id": buyer_id},
                        {
                            "$push": {
                                "transactions": {
                                    "stock_tx_id": stock_tx_id,
                                    "wallet_tx_id": wallet_tx_id,
                                    "is_debit": True,
                                    "amount": trade_value,
                                    "time_stamp": cur_date_time
                                }
                            }
                        },
                        upsert=True
                    ),
                    UpdateOne(
                        {"user_id": seller_id},
                        {
                            "$push": {
                                "transactions": {
                                    "stock_tx_id": stock_tx_id,
                                    "wallet_tx_id": wallet_tx_id,
                                    "is_debit": False,
                                    "amount": trade_value,
                                    "time_stamp": cur_date_time
                                }
                            }
                        },
                        upsert=True
                    )
                ]
                # Execute bulk operation
                wallet_transactions_collection.bulk_write(transactions)

                # Append transaction to executed_trades (for return output)
                executed_trades.append({
                    "stock_tx_id": stock_tx_id,
                    "parent_stock_tx_id": None,  # Parent transaction reference (if applicable)
                    "stock_id": cur_stock,
                    "wallet_tx_id": wallet_tx_id,  # Matching wallet transaction
                    "quantity": traded_quantity,
                    "stock_price": sell_price,
                    "order_status": "COMPLETED",
                    "is_buy": True,
                    "buyer_id": buyer_id,
                    "seller_id": seller_id,
                    "time_stamp": cur_date_time
                })
                logging.info(f"MATCHED ORDER: {buyer_id} bought {traded_quantity} shares of {cur_stock} from {seller_id} at {sell_price}")

                # Adjust remaining quantities
                if buy_quantity > traded_quantity:
                    self.buy_orders[cur_stock][0][2] -= traded_quantity
                else:
                    self.buy_orders[cur_stock].pop(0)  # Remove fully matched buy order

                if sell_quantity > traded_quantity:
                    self.sell_orders[cur_stock][0][2] -= traded_quantity
                else:
                    self.sell_orders[cur_stock].pop(0)  # Remove fully matched sell order
                    if self.sell_orders[cur_stock]:
                        cur_best_stock_prices[cur_stock] = self.sell_orders[cur_stock][0]
                    else:
                        del cur_best_stock_prices[cur_stock]

        return executed_trades
    
    def cancel_user_order(self, user_id, stock_tx_id):
        """
        Cancels an order (either BUY or SELL) for the given user and transaction ID.
        """
        found_item = None
        order_type = None
        stock_id = None

        # 1) Search for the order in BUY orders --  tx_id at index 4
        for stock, orders in self.buy_orders.items():
            for order in orders:
                # order = [user_id, price, quantity, timestamp, transaction_id]
                if order[0] == user_id and order[4] == stock_tx_id:
                    found_item = order
                    order_type = "MARKET"
                    stock_id = stock
                    break
            if found_item:
                break

        # 2) Search for the order in SELL orders, if not found in BUY
        if not found_item:
            for stock, orders in self.sell_orders.items():
                for order in orders:
                    # order = [user_id, price, quantity, timestamp, transaction_id]
                    if order[0] == user_id and order[4] == stock_tx_id:
                        found_item = order
                        order_type = "LIMIT"
                        stock_id = stock
                        break
                if found_item:
                    break

        # 3) If no order found, return failure
        if not found_item:
            logging.warning(f"Order with stock_tx_id={stock_tx_id} not found for user_id={user_id}.")
            return False, 400

        # Extract relevant info from found_item
        if order_type == "MARKET":
            # self.buy_orders[stock_id].append([user_id, price, quantity, datetime.now(), order_id])
            quantity = found_item[2]
            # price is typically None for buy order, but we can set it if needed
        else:  # SELL
            # found_item = [user_id, price, quantity, timestamp, transaction_id]
            price = found_item[1]
            quantity = found_item[2]

        # 4) Remove the order from in-memory order book
        if order_type == "MARKET" and stock_id in self.buy_orders and found_item in self.buy_orders[stock_id]:
            self.buy_orders[stock_id].remove(found_item)
        elif order_type == "LIMIT" and stock_id in self.sell_orders and found_item in self.sell_orders[stock_id]:
            self.sell_orders[stock_id].remove(found_item)

        logging.info(f"Cancelled {order_type} order for user_id={user_id}, stock_id={stock_id}, stock_tx_id={stock_tx_id}")

        # 5) Update MongoDB: Mark transaction as CANCELLED
        stock_transactions_collection.update_one(
            {"stock_tx_id": stock_tx_id, "user_id": user_id},
            {"$set": {"order_status": "CANCELLED", "cancelled_at": datetime.now().isoformat()}}
        )

        # 6) If it's a SELL order, return the stock quantity to the user's portfolio
        if order_type == "LIMIT":
            # 1) Attempt to increment the existing stock entry
            result = portfolios_collection.update_one(
                {"user_id": user_id, "data.stock_id": stock_id},
                {"$inc": {"data.$.quantity_owned": quantity}}
            )

            if result.matched_count == 0:
                if quantity > 0:
                    # Fetch the stock name from stocks_collection
                    stock_doc = stocks_collection.find_one({"stock_id": stock_id}, {"stock_name": 1})
                    stock_name = stock_doc["stock_name"] if stock_doc else "Unknown"

                    portfolios_collection.update_one(
                        {"user_id": user_id},
                        {
                            "$push": {
                                "data": {
                                    "stock_id": stock_id,
                                    "stock_name": stock_name,
                                    "quantity_owned": quantity
                                }
                            }
                        },
                        upsert=True
                    )
                    logging.info(f"Created new stock {stock_id} with quantity={quantity} for user {user_id}")
                    return True, 200
                else:
                    # It's a SELL, but user doesn't own it
                    logging.warning(f"Sell order failed: user {user_id} doesn't own stock {stock_id}")
                    return False, 400

        return True, 200
    
    def find_stock_prices(self):
        global cur_best_stock_prices
        stock_prices = []
        # Get stock name from stocks_collection
        for ticker, orders in self.sell_orders.items():
            # Compute the lowest price among all sell orders for this stock.
            if orders:
                lowest_price = orders[0][1]  # orders[0] first element in the main,
                # and price is the second element in the list of the element: [user_id, price, quantity, timestamp, transaction_id]
            else:
                lowest_price = None

            # Query MongoDB to get the stock name using the stock_id.

            # Create stock_name dictionary---------------------------
            stock_doc = stocks_collection.find_one({"stock_id": ticker})
            stock_name = stock_doc.get("stock_name", "Unknown") if stock_doc else "Unknown"

            stock_prices.append({
                "stock_id": ticker,
                "stock_name": stock_name,
                "current_price": lowest_price
            })
            # Sort lexographically

        return True, stock_prices
