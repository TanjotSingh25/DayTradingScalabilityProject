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
        self.buy_orders = {}  # { "ticker": [[user_id, quantity, timestamp, transaction_id], ...] }
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
            

    def add_buy_order(self, user_id, order_id, stock_id, price, quantity):
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
        # if price is not None:
        #     logging.warning(f"BUY ORDER REJECTED: Limit buy not allowed for {user_id}")
        #     return {"success": False, "error": "Only market buy orders are allowed"}
        
    # Generate unique transaction IDs
        parent_tx_id = str(uuid4())  # Use order_id as the main stock transaction ID
        wallet_tx_id = str(uuid4())  # Generate a unique wallet transaction ID

        stock_transactions_collection.insert_one({
            "stock_tx_id": parent_tx_id,  # Renamed from "tx_id" to match API response
            "parent_stock_tx_id": None,  # Explicitly setting parent_stock_tx_id as null for first transactions
            "stock_id": stock_id,
            "wallet_tx_id": wallet_tx_id,  # Added missing wallet transaction reference
            "user_id": user_id,
            "order_status": "IN_PROGRESS",  # Renamed from "status" to match API response
            "is_buy": True,  # Added missing is_buy field (since it's a market buy order)
            "order_type": "MARKET",  # Ensuring order type is consistent
            "stock_price": None,  # Ensuring stock price is stored
            "quantity": quantity,  # Ensuring quantity is stored
            "time_stamp": datetime.now().isoformat()  # Renamed from "created_at" to match API response
        })

        if stock_id not in self.sell_orders or not self.sell_orders[stock_id]:
            # No sellers available at all -> queue the entire order as unfilled
            # Mark status as INCOMPLETE, and put this buy into a "market buy queue".
            self._queue_market_buy(user_id, parent_tx_id, quantity, stock_id) 
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

        while remaining_qty > 0 and self.sell_orders.get(stock_id):
            # 1. Get best available (lowest price) sell order
            best_sell_order = self.sell_orders[stock_id][0]
            seller_id, sell_price, sell_quantity, sell_time, seller_tx_id = best_sell_order

            # 2. How many shares can we buy from this particular seller?
            trade_qty = min(remaining_qty, sell_quantity)
            trade_value = trade_qty * sell_price

            # 3. Check buyer wallet
            buyer_wallet_balance = self.get_wallet_balance(user_id) #queries mongodb for wallet balance
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
            
           

            # 5. Update order books
            # Reduce the sell order by 'trade_qty'
            if sell_quantity > trade_qty:
                self.sell_orders[stock_id][0][2] -= trade_qty
            else:
                # If fully filled, remove it
                self.sell_orders[stock_id].pop(0)

            # 6. Update buyer's remaining quantity
            remaining_qty -= trade_qty
            
            # Log partial fill with a new transaction record
            partial_tx_id = str(uuid4())
            stock_transactions_collection.insert_one({
                "stock_tx_id": partial_tx_id,
                "parent_stock_tx_id": parent_tx_id if remaining_qty > 0 else None,
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
            
            # Generate a unique wallet transaction ID for seller credit
            seller_wallet_tx_id = str(uuid4())
            
            #    # Log wallet transaction for buyer (debit)
            # wallet_transactions_collection.insert_one({
            #     "wallet_tx_id": wallet_tx_id,
            #     "user_id": user_id,
            #     "stock_tx_id": partial_tx_id,
            #     "is_debit": True,  # Money deducted from buyer
            #     "amount": trade_value,
            #     "time_stamp": datetime.now().isoformat()
            # })
            
            # Log wallet transaction for buyer (debit)
            wallet_transactions_collection.update_one(
                {"user_id": user_id},
                {
                "$push": {
                    "transactions": {
                    "tx_id": partial_tx_id,
                    "tx_id2": wallet_tx_id,
                    "is_debit": True,
                    "amount": trade_value,
                    "time_stamp": datetime.now().isoformat()
                    }
                }
                },
                upsert=True
            )
            #  # Log wallet transaction for seller (credit)
            # wallet_transactions_collection.insert_one({
            #     "wallet_tx_id": seller_wallet_tx_id,
            #     "user_id": seller_id,
            #     "stock_tx_id": partial_tx_id,
            #     "is_debit": False,  # Money credited to seller
            #     "amount": trade_value,
            #     "time_stamp": datetime.now().isoformat()
            # })
            
            wallet_transactions_collection.update_one(
            {"user_id": seller_id},
            {
            "$push": {
                "transactions": {
                "tx_id": partial_tx_id,
                "tx_id2": seller_wallet_tx_id,
                "is_debit": False,
                "amount": trade_value,
                "time_stamp": datetime.now().isoformat()
                }
            }
            },
            upsert=True
        )


            # 7. Record this partial execution
            executed_trades.append({
                "stock_tx_id": partial_tx_id,
                "parent_stock_tx_id": parent_tx_id if remaining_qty > 0 else None,
                "stock_id": stock_id,
                "wallet_tx_id": wallet_tx_id,
                "quantity": trade_qty,
                "stock_price": sell_price,
                "buyer_id": user_id,
                "seller_id": seller_id,
                "time_stamp": datetime.now().isoformat()
            })

            logging.info(f"BUY MARKET TRADE: {user_id} bought {trade_qty} shares of {stock_id} @ {sell_price}")

            # If we've run out of sellers, the loop will break automatically since self.sell_orders[ticker] might be empty

        # End of the while loop
        # Determine the final order status
        filled = quantity - remaining_qty
        if filled == 0:
            # No shares actually bought
            order_status = "INCOMPLETE"
            # Optionally queue the entire order as a market buy
            self._queue_market_buy(user_id, parent_tx_id, remaining_qty, stock_id)
        elif remaining_qty > 0:
            # Some portion was filled, but not all
            order_status = "PARTIALLY_COMPLETED"
            # The leftover can also be queued as a market buy if desired
            self._queue_market_buy(user_id, parent_tx_id, remaining_qty, stock_id)
        else:
            # All shares filled
            order_status = "COMPLETED"
            
        # Update parent transaction record with final status and remaining quantity
        stock_transactions_collection.update_one(
            {"stock_tx_id": parent_tx_id},
            {"$set": {"remaining_quantity": remaining_qty, "status": order_status}}
        )

        return {
            "success": True,
            "message": f"Market buy of {quantity} shares of {stock_id} processed. {filled} filled.",
            "order_status": order_status,
            "trade_details": executed_trades,
            "stock_tx_id": parent_tx_id
    }

    def _queue_market_buy(self, user_id, order_id, quantity, stock_id):
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
        self.buy_orders[stock_id].append([user_id, None, quantity, datetime.now(), order_id])

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

    # def update_user_stock_balance(self, user_id, stock_id, quantity):
    #     """Subtracts stock quantity from the user's holdings after placing a sell order."""
    #     try:
    #         result = portfolios_collection.update_one(
    #             {"user_id": user_id, "data.stock_id": stock_id},
    #             {"$inc": {"data.$.quantity_owned": quantity}}  # Decrease stock quantity
    #         )

    #         if result.matched_count == 0:
                
    #             logging.warning(f"Sell order failed: {user_id} does not own stock {stock_id} or insufficient balance.")
    #             return False  # Stock not found in portfolio

    #         logging.info(f"Updated stock balance for {user_id}: Sold {quantity} of stock {stock_id}")
    #         return True

    #     except Exception as e:
    #         logging.error(f"Error updating stock balance for {user_id}, {stock_id}: {e}")
    #         return False
    
    # def update_user_stock_balance(self, user_id, stock_id, quantity):
    #     """
    #     This method works for both BUY (quantity>0) and SELL (quantity<0).
    #     """
    #     try:
    #         result = portfolios_collection.update_one(
    #             {"user_id": user_id, "data.stock_id": stock_id},
    #             {"$inc": {"data.$.quantity_owned": quantity}}
    #         )

    #         if result.matched_count == 0:
    #             # Fallback: if quantity > 0, user is buying a brand-new stock, so add it:
    #             if quantity > 0:
    #                 portfolios_collection.update_one(
    #                     {"user_id": user_id},
    #                     {"$push": {"data": {"stock_id": stock_id, "quantity_owned": quantity}}},
    #                     upsert=True
    #                 )
    #                 logging.info(f"Created new stock {stock_id} with quantity={quantity} for user {user_id}")
    #                 return True
    #             else:
    #                 # For SELL with matched_count=0, user truly doesn't own it
    #                 logging.warning(f"Sell order failed: user {user_id} doesn't own stock {stock_id}")
    #                 return False

    #         logging.info(f"Updated stock balance for user {user_id}: {quantity} shares of {stock_id}")
    #         return True

    #     except Exception as e:
    #         logging.error(f"Error updating stock balance for {user_id}, {stock_id}: {e}")
    #         return False

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
                    portfolios_collection.update_one(
                        {"user_id": user_id},
                        {"$push": {"data": {"stock_id": stock_id, "quantity_owned": quantity}}},
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


    def add_sell_order(self, user_id, order_id, stock_id, price, quantity):
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
        try:
            stock_transactions_collection.insert_one({
                "stock_tx_id": str(uuid4()),
                "parent_stock_tx_id": None,
                "stock_id": stock_id,
                "wallet_tx_id": str(uuid4()),  # No wallet transaction for a limit order yet
                "user_id": user_id,
                "order_status": "IN_PROGRESS",
                "is_buy": False,
                "order_type": "LIMIT",
                "stock_price": price,
                "quantity": quantity,
                "time_stamp": datetime.now().isoformat()
            })
        except errors.DuplicateKeyError:
            logging.error(f"DUPLICATE KEY ERROR: stock_tx_id={order_id} already exists. Retrying...")
            return {"success": False, "error": "Duplicate stock transaction ID. Try again."}

        # Add the sell order to in-memory order book
        if stock_id not in self.sell_orders:
            self.sell_orders[stock_id] = []

        self.sell_orders[stock_id].append([user_id, price, quantity, datetime.now(), order_id])

        # Ensure orders are sorted (Lowest price first, FIFO for equal prices)
        self.sell_orders[stock_id].sort(key=lambda x: (x[1], x[3]))

        logging.info(f"SELL ORDER: {user_id} listed {quantity} shares of {stock_id} at {price}")
        return {"success": True, "message": "Sell order placed successfully"}

    def match_orders(self):
        """ Matches buy and sell orders using FIFO logic. Market orders execute immediately. """
        executed_trades = []

        for cur_stock in list(self.sell_orders.keys()):  # Start with sell orders
            while self.sell_orders.get(cur_stock) and self.buy_orders.get(cur_stock):
                buyer_id, buy_price, buy_quantity, buy_time, buy_order_id = self.buy_orders[cur_stock][0]
                seller_id, sell_price, sell_quantity, sell_time, sell_order_id = self.sell_orders[cur_stock][0]

                # MARKET ORDER: Buy at best available sell price
                if buy_price is None:
                    buy_price = sell_price  # Execute at best available sell price

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
                stock_transactions_collection.insert_one({
                    "stock_tx_id": stock_tx_id,
                    "parent_stock_tx_id": None,  # If this is a partial order, update later
                    "stock_id": cur_stock,
                    "wallet_tx_id": wallet_tx_id, 
                    "quantity": traded_quantity,
                    "stock_price": sell_price,  # Aligning with API response field name
                    "order_status": "COMPLETED",  # Using API terminology
                    "is_buy": True,  # Flagging if it's a buy transaction
                    "buyer_id": buyer_id,
                    "seller_id": seller_id,
                    "time_stamp": datetime.now().isoformat()
                })
                
                
                # # Log transaction in `wallet_transactions_collection` for buyer (money deducted)
                # wallet_transactions_collection.insert_one({
                #     "wallet_tx_id": wallet_tx_id,  # Unique wallet transaction ID
                #     "user_id": buyer_id,
                #     "stock_tx_id": stock_tx_id,  # Reference to stock transaction
                #     "is_debit": True,  # Buyer is paying money
                #     "amount": trade_value,
                #     "time_stamp": datetime.now().isoformat()
                # })
                
                wallet_transactions_collection.update_one(
                {"user_id": buyer_id},
                {
                "$push": {
                    "transactions": {
                    "tx_id": stock_tx_id,       # The "stock" transaction ID
                    "tx_id2": wallet_tx_id,     # The buyer’s unique wallet transaction ID
                    "is_debit": True,           # Buyer is paying money
                    "amount": trade_value,
                    "time_stamp": datetime.now().isoformat()
                    }
                }
                },
                upsert=True
               )
                
                # # Generate a separate wallet transaction ID for seller (money credited)
                # seller_wallet_tx_id = str(uuid4())
                
                #  # Log transaction in `wallet_transactions_collection` for seller (money credited)
                # wallet_transactions_collection.insert_one({
                #     "wallet_tx_id": seller_wallet_tx_id,  # New unique ID for seller's credit transaction
                #     "user_id": seller_id,
                #     "stock_tx_id": stock_tx_id,  # Reference to stock transaction
                #     "is_debit": False,  # Seller is receiving money
                #     "amount": trade_value,
                #     "time_stamp": datetime.now().isoformat()
                # })
                
                # 2) Seller transaction (money credited)
                seller_wallet_tx_id = str(uuid4())

                wallet_transactions_collection.update_one(
                    {"user_id": seller_id},
                    {
                    "$push": {
                        "transactions": {
                        "tx_id": stock_tx_id,
                        "tx_id2": seller_wallet_tx_id,
                        "is_debit": False,       # Seller is receiving money
                        "amount": trade_value,
                        "time_stamp": datetime.now().isoformat()
                        }
                    }
                    },
                    upsert=True
                )

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
                    "time_stamp": datetime.now().isoformat()
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
                # order = [user_id, quantity, timestamp, transaction_id]
                if order[0] == user_id and order[3] == stock_tx_id:
                    found_item = order
                    order_type = "BUY"
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
                        order_type = "SELL"
                        stock_id = stock
                        break
                if found_item:
                    break

        # 3) If no order found, return failure
        if not found_item:
            logging.warning(f"Order with stock_tx_id={stock_tx_id} not found for user_id={user_id}.")
            return False, "Order not found."

        # Extract relevant info from found_item
        if order_type == "BUY":
            # found_item = [user_id, quantity, timestamp, transaction_id]
            quantity = found_item[1]
            # price is typically None for buy order, but we can set it if needed
        else:  # SELL
            # found_item = [user_id, price, quantity, timestamp, transaction_id]
            price = found_item[1]
            quantity = found_item[2]

        # 4) Remove the order from in-memory order book
        if order_type == "BUY" and stock_id in self.buy_orders and found_item in self.buy_orders[stock_id]:
            self.buy_orders[stock_id].remove(found_item)
        elif order_type == "SELL" and stock_id in self.sell_orders and found_item in self.sell_orders[stock_id]:
            self.sell_orders[stock_id].remove(found_item)

        logging.info(f"Cancelled {order_type} order for user_id={user_id}, stock_id={stock_id}, stock_tx_id={stock_tx_id}")

        # 5) Update MongoDB: Mark transaction as CANCELLED
        stock_transactions_collection.update_one(
            {"stock_tx_id": stock_tx_id, "user_id": user_id},
            {"$set": {"order_status": "CANCELLED", "cancelled_at": datetime.now().isoformat()}}
        )

        # 6) If it's a SELL order, return the stock quantity to the user's portfolio
        if order_type == "SELL":
            result = portfolios_collection.update_one(
                {"user_id": user_id, "data.stock_id": stock_id},
                {"$inc": {"data.$.quantity_owned": quantity}}
            )

            if result.matched_count == 0:
                logging.warning(f"Stock {stock_id} not found in user {user_id}'s portfolio. Unable to return quantity.")

        return True, "Cancellation successful"
    
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
orderBookInst = OrderBook()
