import time
from datetime import datetime
import logging
from pymongo import MongoClient, errors
import os
from dotenv import load_dotenv
from uuid import uuid4


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='matching_engine.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')


# MongoDB connection with retry mechanism
max_retries = 5
retry_delay = 3  # seconds between retries

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Make sure it's defined in docker-compose.yml.")

for attempt in range(max_retries):
    try:
        client = MongoClient(MONGO_URI)
        db = client["trading_system"]
        wallets_collection = db["wallets"]
        portfolios_collection = db["portfolios"]  # Ensure portfolios collection is initialized
        stock_transactions_collection = db["stock_transactions"]  # New collection for transactions
        wallet_transactions_collection = db["wallets_transaction"]
        stocks_collection = db["stocks"]
        # Ensure necessary indexes for faster lookups
        stock_transactions_collection.create_index("stock_tx_id", unique=True)
        wallet_transactions_collection.create_index("user_id", unique = True)

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
        self.buy_orders = {}  # self.buy_orders[stock_id].append([user_id, price, quantity, datetime.now(), order_id])
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
            # Ensure a wallet document exists with a default balance of 0.
            wallets_collection.update_one(
                {"user_id": user_id},
                {"$setOnInsert": {"balance": 0}},
                upsert=True
            )
            # Now increment the balance.
            wallets_collection.update_one(
                {"user_id": user_id},
                {"$inc": {"balance": amount}}
            )
            logging.info(f"Updated wallet balance for {user_id} by {amount}")
        except Exception as e:
            logging.error(f"Error updating wallet balance for {user_id}: {e}")
            

    def add_buy_order(self, user_id, stock_id, price, quantity):
        """
        Handles a MARKET BUY order in a loop, allowing partial fills.
        1. Creates a parent transaction with wallet_tx_id=None.
        2. Executes partial trades, each with its own wallet_tx_id.
        3. If the entire order completes, sets a final wallet_tx_id and average fill price on the parent.
        """

        parent_tx_id = str(uuid4())

        # 1) Insert parent transaction with wallet_tx_id=None
        stock_transactions_collection.insert_one({
            "stock_tx_id": parent_tx_id,
            "parent_stock_tx_id": None,
            "stock_id": stock_id,
            "wallet_tx_id": None,           # Initially null
            "user_id": user_id,
            "order_status": "IN_PROGRESS",
            "is_buy": True,
            "order_type": "MARKET",
            "stock_price": price,
            "quantity": quantity,
            "time_stamp": datetime.now().isoformat()
        })

        # 2) If no sell orders, queue entire order as unfilled
        if stock_id not in self.sell_orders or not self.sell_orders[stock_id]:
            self._queue_market_buy(user_id, None, quantity, parent_tx_id, stock_id)
            stock_transactions_collection.update_one(
                {"stock_tx_id": parent_tx_id},
                {"$set": {"order_status": "INCOMPLETE"}}
            )
            return {
                "success": True,
                "message": "No sellers available. Order queued as market buy.",
                "order_status": "INCOMPLETE",
                "trade_details": [],
                "stock_tx_id": parent_tx_id
            }

        remaining_qty = quantity
        executed_trades = []
        order_status = "INCOMPLETE"

        # 3) Partial fill loop
        while remaining_qty > 0 and self.sell_orders.get(stock_id):
            # Generate a wallet_tx_id for this partial fill
            wallet_tx_id = str(uuid4())

            # Find first valid seller (skip self-trade)
            valid_sell_index = None
            for idx, order in enumerate(self.sell_orders[stock_id]):
                s_id, s_price, s_qty, s_time, s_tx_id = order
                if s_id != user_id:
                    valid_sell_index = idx
                    break

            if valid_sell_index is None:
                # No valid seller found
                break

            seller_id, sell_price, sell_quantity, sell_time, seller_tx_id = \
                self.sell_orders[stock_id][valid_sell_index]

            # Determine trade_qty
            trade_qty = min(remaining_qty, sell_quantity)
            trade_value = trade_qty * sell_price

            # Check buyer wallet
            buyer_balance = self.get_wallet_balance(user_id)
            if buyer_balance < trade_value:
                max_can_buy = buyer_balance // sell_price
                if max_can_buy == 0:
                    # Can't afford any shares from this seller
                    order_status = "PARTIALLY_COMPLETED" if executed_trades else "INCOMPLETE"
                    break
                else:
                    trade_qty = max_can_buy
                    trade_value = trade_qty * sell_price

            # 4) Execute trade: update wallet balances
            self.update_wallet_balance(seller_id, trade_value)
            self.update_wallet_balance(user_id, -trade_value)

            # Update portfolio
            self.update_user_stock_balance(user_id, stock_id, trade_qty)

            # Reduce or remove sell order
            if sell_quantity > trade_qty:
                self.sell_orders[stock_id][valid_sell_index][2] -= trade_qty
            else:
                self.sell_orders[stock_id].pop(valid_sell_index)

            remaining_qty -= trade_qty

            # 5) Insert partial fill transaction
            partial_tx_id = str(uuid4())
            stock_transactions_collection.insert_one({
                "stock_tx_id": partial_tx_id,
                "parent_stock_tx_id": parent_tx_id,
                "stock_id": stock_id,
                "wallet_tx_id": wallet_tx_id,
                "quantity": trade_qty,
                "stock_price": sell_price,
                "order_status": "COMPLETED",
                "is_buy": True,
                "user_id": user_id,
                "seller_id": seller_id,
                "time_stamp": datetime.now().isoformat()
            })

            # Log buyer & seller wallet transactions
            wallet_transactions_collection.update_one(
                {"user_id": user_id},
                {"$push": {
                    "transactions": {
                        "stock_tx_id": parent_tx_id,
                        "wallet_tx_id": wallet_tx_id,
                        "is_debit": True,
                        "amount": trade_value,
                        "time_stamp": datetime.now().isoformat()
                    }}},
                upsert=True
            )
            wallet_transactions_collection.update_one(
                {"user_id": seller_id},
                {"$push": {
                    "transactions": {
                        "stock_tx_id": parent_tx_id,
                        "wallet_tx_id": wallet_tx_id,
                        "is_debit": False,
                        "amount": trade_value,
                        "time_stamp": datetime.now().isoformat()
                    }}},
                upsert=True
            )

            # Track this partial fill
            executed_trades.append({
                "stock_tx_id": partial_tx_id,
                "parent_stock_tx_id": parent_tx_id,
                "stock_id": stock_id,
                "wallet_tx_id": wallet_tx_id,
                "quantity": trade_qty,
                "stock_price": sell_price,
                "buyer_id": user_id,
                "seller_id": seller_id,
                "time_stamp": datetime.now().isoformat()
            })

        # 6) Determine final state and update the parent transaction
        filled = quantity - remaining_qty
        if filled == 0:
            order_status = "INCOMPLETE"
            stock_transactions_collection.update_one(
                {"stock_tx_id": parent_tx_id},
                {"$set": {"order_status": order_status}}
            )
            # Optional: re-queue leftover
            self._queue_market_buy(user_id, None, remaining_qty, parent_tx_id, stock_id)

        elif remaining_qty > 0:
            order_status = "PARTIALLY_COMPLETED"
            stock_transactions_collection.update_one(
                {"stock_tx_id": parent_tx_id},
                {"$set": {"order_status": order_status}}
            )
            # Optionally queue leftover
            self._queue_market_buy(user_id, None, remaining_qty, parent_tx_id, stock_id)

        else:
            # All shares filled -> COMPLETED
            order_status = "COMPLETED"
            # Compute average fill price
            total_cost = sum(t["quantity"] * t["stock_price"] for t in executed_trades)
            total_shares = sum(t["quantity"] for t in executed_trades)
            avg_fill_price = int(total_cost / total_shares) if total_shares else 0

            # Generate final wallet_tx_id for the entire completed order
            final_wallet_tx_id = str(uuid4())

            stock_transactions_collection.update_one(
                {"stock_tx_id": parent_tx_id},
                {"$set": {
                    "order_status": order_status,
                    "remaining_quantity": 0,
                    "stock_price": avg_fill_price,
                    "wallet_tx_id": final_wallet_tx_id
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
        """
        Helper method to queue leftover market buys if desired.
        For example, you might store them in self.buy_orders[stock_id]
        with price=None.
        """
        if quantity <= 0:
            return

        # If you want to store leftover as a 'market' entry in the buy book:
        if stock_id not in self.buy_orders:
            self.buy_orders[stock_id] = []

        # store price as None to represent a market buy
        self.buy_orders[stock_id].append([user_id, price, quantity, datetime.now(), order_id])

        # We don't necessarily need to deduct funds here, because
        # no trade is happening yet. The user will pay once a seller appears.

        logging.info(f"Queued leftover market buy for {user_id}: {quantity} shares of {stock_id}")

    # gets the stock info from the portflio collectoion in the db mongo
    def get_user_stock_balance(self, user_id, stock_id):
        """Fetches the user's stock balance for a given stock_id from MongoDB portfolios collection."""
        try:
            user_portfolio = portfolios_collection.find_one(
                {"user_id": user_id, "data.stock_id": stock_id},
                {"data.$": 1}  # Use positional operator to get the specific stock entry
            )

            if user_portfolio and "data" in user_portfolio and len(user_portfolio["data"]) > 0:
                return user_portfolio["data"][0]["quantity_owned"]  # Extract stock quantity
            
            return 0  # User does not own this stock

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
                    # It's a SELL, but user doesn't own it
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
                    # Remove this stock from the 'data' array
                    portfolios_collection.update_one(
                        {"user_id": user_id},
                        {"$pull": {"data": {"stock_id": stock_id}}}
                    )
                    logging.info(f"Removed stock {stock_id} from user {user_id}'s portfolio (qty=0).")

            logging.info(f"Updated stock balance for user {user_id}: {quantity} shares of {stock_id}")
            return True

        except Exception as e:
            logging.error(f"Error updating stock balance for {user_id}, {stock_id}: {e}")
            return False


    def add_sell_order(self, user_id, stock_id, price, quantity):
        """ Adds a sell order only if the user has enough stock balance. """

        # Get the user's stock balance (returns an integer)
        stock_balance = self.get_user_stock_balance(user_id, stock_id)

        # Ensure user has enough stock
        if stock_balance <= 0:
            logging.warning(f"SELL ORDER FAILED: {user_id} does not own stock {stock_id}.")
            return {"success": False, "error": "User does not own this stock."}

        # Amount you want to sell is more than the amount you want to sell
        if quantity > stock_balance:
            logging.warning(f"SELL ORDER FAILED: {user_id} tried to sell {quantity} of {stock_id}, but only has {stock_balance}.")
            return {"success": False, "error": "Insufficient stock balance."}

        # Deduct stock from user's portfolio
        result = self.update_user_stock_balance(user_id, stock_id, -quantity)

        if result == False:  # Ensure the update succeeded
            logging.error(f"SELL ORDER ERROR: Failed to update portfolio for {user_id}.")
            return {"success": False, "error": "Portfolio update failed."}

        # Insert order into stock_transactions_collection
        st_tx_id = str(uuid4())
        try:
            stock_transactions_collection.insert_one({
                "stock_tx_id": st_tx_id,
                "parent_stock_tx_id": None,
                "stock_id": stock_id,
                "wallet_tx_id": None,  # No wallet transaction for a limit order yet
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

        logging.info(f"SELL ORDER: {user_id} listed {quantity} shares of {stock_id} at {price}")
        return {"success": True, "message": "Sell order placed successfully"}

    def match_order(self, parent_tx_id, user_id, stock_id, desired_quantity, sell_orders):
        """
        Example match_order method that:
        1. Retrieves a parent transaction with wallet_tx_id=None.
        2. Processes partial fills against provided sell_orders.
        3. Only assigns wallet_tx_id when the order is fully completed.
        :param parent_tx_id: The parent transaction ID for the buy order.
        :param user_id: The ID of the buyer.
        :param stock_id: Which stock is being bought.
        :param desired_quantity: How many shares the buyer wants.
        :param sell_orders: A list of [seller_id, price, quantity, timestamp, sell_tx_id].
        """
        executed_trades = []
        remaining_qty = desired_quantity

        # 1) Query your DB for the parent transaction (just for completeness; you might already have it).
        parent_record = stock_transactions_collection.find_one({"stock_tx_id": parent_tx_id})
        if not parent_record:
            return {"success": False, "error": f"No parent transaction found for {parent_tx_id}"}

        # 2) Iterate over sell orders until we've filled the entire quantity or run out.
        for idx, sell_order in enumerate(sell_orders):
            if remaining_qty <= 0:
                break

            seller_id, sell_price, sell_quantity, sell_time, seller_tx_id = sell_order
            if seller_id == user_id:
                # Skip self-trade (if that’s your logic)
                continue

            # Determine how many shares we can fill
            trade_qty = min(remaining_qty, sell_quantity)
            trade_value = trade_qty * sell_price

            # (A) Check buyer’s wallet (stubbed out here)
            buyer_balance = self.get_wallet_balance(user_id)
            if buyer_balance < trade_value:
                # Buyer cannot afford the entire trade_qty => partial or none
                possible_qty = buyer_balance // sell_price
                if possible_qty == 0:
                    # Can’t buy any shares; break or continue depending on your logic
                    break
                else:
                    trade_qty = possible_qty
                    trade_value = trade_qty * sell_price

            # (B) Update buyer/seller wallets
            self.update_wallet_balance(seller_id, trade_value)
            self.update_wallet_balance(user_id, -trade_value)

            # (C) Adjust the sell order’s available quantity
            sell_orders[idx][2] -= trade_qty  # reduce the seller’s quantity
            remaining_qty -= trade_qty

            # (D) Log a partial (child) transaction (with its own wallet_tx_id)
            child_stock_tx_id = str(uuid4())
            partial_wallet_tx_id = str(uuid4())
            stock_transactions_collection.insert_one({
                "stock_tx_id": child_stock_tx_id,
                "parent_stock_tx_id": parent_tx_id,
                "stock_id": stock_id,
                "wallet_tx_id": partial_wallet_tx_id,
                "quantity": trade_qty,
                "stock_price": sell_price,
                "order_status": "COMPLETED",
                "is_buy": True,
                "buyer_id": user_id,
                "seller_id": seller_id,
                "time_stamp": datetime.now().isoformat()
            })

            # (E) Keep track of executed trades
            executed_trades.append({
                "stock_tx_id": child_stock_tx_id,
                "wallet_tx_id": partial_wallet_tx_id,
                "quantity": trade_qty,
                "stock_price": sell_price,
                "buyer_id": user_id,
                "seller_id": seller_id
            })

        # 3) After iterating, decide if the order is COMPLETED or PARTIALLY_COMPLETED/INCOMPLETE
        filled_qty = desired_quantity - remaining_qty
        if filled_qty == 0:
            # No shares were filled
            final_status = "INCOMPLETE"
        elif remaining_qty > 0:
            # Some shares filled
            final_status = "PARTIALLY_COMPLETED"
        else:
            # Everything filled
            final_status = "COMPLETED"

        # 4) If the entire order is COMPLETED, generate a final wallet_tx_id and update the parent
        update_fields = {
            "order_status": final_status,
            "remaining_quantity": remaining_qty
        }

        if final_status == "COMPLETED":
            # Only now do we generate a wallet_tx_id for the *parent* transaction
            final_wallet_tx_id = str(uuid4())
            update_fields["wallet_tx_id"] = final_wallet_tx_id

        stock_transactions_collection.update_one(
            {"stock_tx_id": parent_tx_id},
            {"$set": update_fields}
        )

        return {
            "success": True,
            "order_status": final_status,
            "trade_details": executed_trades,
            "stock_tx_id": parent_tx_id
        }
    
    def cancel_user_order(self, user_id, stock_tx_id):
        """
        Cancels an order (either BUY or SELL) for the given user and transaction ID.
        If it's found in the buy orders: [user_id, quantity, timestamp, transaction_id]
        If it's found in the sell orders: [user_id, price, quantity, timestamp, transaction_id]
        """
        found_item = None
        order_type = None
        stock_id = None

        # 1) Search for the order in BUY orders
        #    (where transaction_id is at index 3)
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
        #    (where transaction_id is at index 4)
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
            return False, "Order not found."

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
                    # It's a SELL, but user doesn't own it
                    logging.warning(f"Sell order failed: user {user_id} doesn't own stock {stock_id}")
                    return False

        return True
    
    def find_stock_prices(self):
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
            stock_doc = stocks_collection.find_one({"stock_id": ticker})
            stock_name = stock_doc.get("stock_name", "Unknown") if stock_doc else "Unknown"

            stock_prices.append({
                "stock_id": ticker,
                "stock_name": stock_name,
                "current_price": lowest_price
            })

        return True, stock_prices

# Instantiate a shared order book
#orderBookInst = OrderBook()
