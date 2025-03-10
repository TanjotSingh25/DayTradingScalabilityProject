from flask import Flask, request, jsonify
import helpers
import os
from pymongo import MongoClient, errors
from flask_cors import CORS
import logging as logger
import requests
import uuid
import datetime
import time
import order_book

app = Flask(__name__)
CORS(app)

# JWT Token Variables
JWT_SECRET = "django-insecure-uj@e4q80n@l2ml)rl*-^s84djzyn5ws6vt7@&h!tp*xf)p05t#"
JWT_ALGORITHM = "HS256"

# Orderbook instance
orderBookInst = order_book.OrderBook()

# --- Database Connections ---

# Attempt to connect to Mongo
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Make sure it's defined in docker-compose.yml.")

for attempt in range(5):
    try:
        # 1.5 minutes
        client = MongoClient(MONGO_URI, maxPoolSize=250, minPoolSize=50, maxIdleTimeMS=90000)
        db = client["trading_system"]
        # MongoDB collections
        wallet_transactions_collection = db["wallets_transaction"]
        portfolios_collection = db["portfolios"]  # this ensures portfolios collection is initialized
        stock_transactions_collection = db["stock_transactions"]  # instantiating new collection for transactions
        logger.info("MongoDB Conn established on Order Service")
        break
    except errors.ConnectionFailure:
        print("Error: Unable to connect to MongoDB. Ensure MongoDB is running in Docker.")
        time.sleep(3)
        raise
else:
    logger.error("Failed to connect to MongoDB after multiple attempts. Exiting...")
    raise RuntimeError("MongoDB connection failed after 5 retries.")


# Endpoint of the Matching Engine Service for order matching
# Do not need to create more endpoints, since i can call wallets_transaction, portfolios, and stock_transactions
# Matching engine only handles: BUY, SELL, CANCEL, GETPRICES (getprices connects to redis, and can query without needing matching engine)
#MATCHING_ENGINE_URL = "http://matching_engine_service:5300/placeOrder"
#MATCHING_ENGINE_CANCELLATION_URL = "http://matching_engine_service:5300/cancelOrder"
#MATCHING_ENGINE_STOCK_PRICES_URL = "http://matching_engine_service:5300/getPrices"

# Place new order -- Market Buy, Limit Sell
# Process order details, communicate with matching engine, store in Orders table, etc.
@app.route('/placeStockOrder', methods=['POST'])
def place_stock_order():
    """
    Accepts JSON input:
    { "token": "jwt_token", "stock_id": "uuid", "is_buy": true, "order_type": "MARKET", "quantity": 50 }
    """
    # Grabs the JSON body
    request_data = request.get_json()
    logger.info(f"Printing Here----------------------------------- {request_data}")
    
    # 1 - Decrypt & validate token
    token = request.headers.get("token", "")
    if not token:
        return jsonify({"success": False, "error": "Missing token header"}), 401

    token_decoded = helpers.decrypt_and_validate_token(token, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success": False, "error": "Invalid token"}), 401
    
    # 2 - Validate the order request
    is_valid, validation_response = helpers.order_service_sanity_check(request_data)
    if not is_valid:
        # 412 Precondition Failed
        return jsonify(validation_response), 401
    # 3 -  verify that the user_name exists via postgreSQL
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "No user_id in token"}), 400

    # Call the matching engine endpoint
    try:
        if request_data["order_type"] == "MARKET":
            result = orderBookInst.add_buy_order(
                user_id, request_data["stock_id"], request_data.get("price"), request_data["quantity"]
                )
        else:
            result = orderBookInst.add_sell_order(
                user_id, request_data["stock_id"], request_data.get("price"), request_data["quantity"]
                )
            executed_trades = orderBookInst.match_orders()
            executed_trades.append(f"Sell order placed for {request_data['stock_id']}.")
            return jsonify({"success": True, "message": executed_trades }), (200 if result["success"] else 400)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "order_status": str(result.get("order_status", "")),  # Ensure string format
        "trade_details": [str(trade) for trade in result.get("trade_details", [])],
        "stock_tx_id": result.get("stock_tx_id", "")}), (200 if result.get("success", False) else 400)

@app.route('/getStockTransactions', methods=['GET'])
def get_stock_transactions():
    """
    Retrieves a list of the user's stock transactions.

    Accepts JSON input:
    {
        "token": "jwt_token"
    }

    Returns:
    {
        "success": true,
        "data": [
            {
                "stock_tx_id": "uuid",
                "parent_stock_tx_id": "uuid" or None,
                "stock_id": "uuid",
                "wallet_tx_id": "uuid" or None,
                "quantity": 50,
                "order_status": "COMPLETED",
                "stock_price": 135,
                "is_buy": true,
                "order_type": "MARKET",
                "timestamp": "2025-01-26T12:00:00Z"
            }
        ]
    }
    """

    # Validate and decrypt the token
    token = request.headers.get("token")
    token_decoded = helpers.decrypt_and_validate_token(token, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success": False, "error": "Invalid token"}), 401

    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "data": None, "message": "No User ID in token"}), 400

    # Query MongoDB for user's transactions from the stock_transactions_collection
    transactions_cursor = stock_transactions_collection.find({"user_id": user_id})

    # Build the response data array
    user_transactions = []
    for doc in transactions_cursor:
        user_transactions.append({
            "stock_tx_id": str(doc.get("stock_tx_id")),
            "parent_stock_tx_id": str(doc.get("parent_stock_tx_id")) if doc.get("parent_stock_tx_id") else None,
            "stock_id": str(doc.get("stock_id")),
            "wallet_tx_id": str(doc.get("wallet_tx_id")) if doc.get("wallet_tx_id") else None,
            "quantity": doc.get("quantity", 0),
            "order_status": doc.get("order_status", ""),
            "stock_price": doc.get("stock_price", 0),
            "is_buy": doc.get("is_buy", False),
            "order_type": doc.get("order_type", ""),
            "timestamp": doc.get("time_stamp") or doc.get("created_at") or ""
        })

    return jsonify({
        "success": True,
        "data": user_transactions
    }), 200


@app.route('/cancelStockTransaction', methods=['POST'])
def cancel_stock_transaction():
    """
    Accepts JSON input:
    { "token": "jwt_token", "stock_tx_id": "uuid" }

    Calls the Matching Engine to cancel the stock order.
    """
    # Parse JSON body
    data = request.get_json() or {}

    # Extract token from Authorization header
    token_header = request.headers.get("token", "")
    if not token_header:
        return jsonify({"success": False, "error": "Missing token header"}), 401

    # Validate and decrypt token using JWT_SECRET
    token_decoded = helpers.decrypt_and_validate_token(token_header, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success": False, "error": "Invalid token"}), 401

    stock_tx_id = data.get("stock_tx_id", "")
    if not stock_tx_id:
        return jsonify({"success": False, "error": "Missing stock transaction ID"}), 400

    # Extracts the user details from token payload
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Missing user ID in token"}), 400

    # Call the Matching Engine /cancelOrder endpoint
    try:
        result, ret_code = orderBookInst.cancel_user_order(user_id, stock_tx_id)
        if ret_code == 200:
            matching_result = {"success" : True, "data": "Order Cancelled Successfully"}
        else:
            matching_result = {"success": False, "error": "Matching Engine error"}
    except Exception as e:
        matching_result = {"success": False, "error": str(e)}
        ret_code = 500

    return jsonify(matching_result), ret_code

@app.route('/getStockPrices', methods=['GET'])
def get_stock_prices():
    """
    Endpoint: GET /getStockPrices
    Description: Retrieves the prices for stocks.

    Expected Request:
    Headers: Token
    """
    token_header = request.headers.get("token")
    if not token_header:
        return jsonify({"success": False, "error": "Missing token header"}), 401

    # Validate and decrypt token using JWT_SECRET
    token_decoded = helpers.decrypt_and_validate_token(token_header, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success": False, "error": token_decoded.get("error")}), 401

    # Extracts the user details from token payload
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Missing user ID in token"}), 400

    # Call the Matching Engine /cancelOrder endpoint
    try:
        result, stock_prices = orderBookInst.find_stock_prices()
        return jsonify({"success": result, "data": stock_prices}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/getWalletTransactions', methods=['GET'])
def get_wallet_transactions():
    """
    Accepts JSON input via headers:
    "token": "user1Token"

    Returns user's wallet transactions in the expected format:
    {
        "success": true,
        "data": [
            {
                "wallet_tx_id": "<walletTxId>",
                "stock_tx_id": "<stockTxId>",
                "is_debit": true,
                "amount": 1350,
                "time_stamp": "<timestamp>"
            }
        ]
    }
    """

    # Validate token
    token = request.headers.get("token")
    token_decoded = helpers.decrypt_and_validate_token(token, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success": False, "data": token_decoded}), 401

    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "data": None, "message": "No User ID in token"}), 400

    # Fetch the user's single wallet document
    doc = wallet_transactions_collection.find_one({"user_id": user_id})

    # If no doc for this user, return empty array
    if not doc:
        return jsonify({"success": True, "data": []}), 200

    #    Builds response data from the "transactions" array
    #    Each transaction object in doc["transactions"] has keys like
    #      "tx_id", " tx_id2", "is_debit", "amount", "time_stamp"
    wallet_transactions = []
    for tx in doc.get("transactions", []):
        # "tx_id2" corresponds to the old "wallet_tx_id"
        wallet_transactions.append({
            "wallet_tx_id": tx.get("wallet_tx_id"),       # The unique wallet transaction ID
            "stock_tx_id": tx.get("stock_tx_id"),         # The "stock" transaction ID
            "is_debit": tx.get("is_debit", False),
            "amount": tx.get("amount", 0),
            "time_stamp": tx.get("time_stamp") or datetime.now().isoformat()
        })

    return jsonify({"success": True, "data": wallet_transactions}), 200

@app.route('/setWallet', methods=['POST'])
def set_wallet():
    """
    Sets or updates a user's wallet balance.
    JSON expected: { "user_id": "uuid", "balance": 5000 }
    """
    #logging.info(orderBookInst.sell_orders)
    #logging.info(orderBookInst.buy_orders)
    token_header = request.headers.get("token")
    if not token_header:
        return jsonify({"success": False, "error": "Missing token header"}), 401

    # Validate and decrypt token using JWT_SECRET
    token_decoded = helpers.decrypt_and_validate_token(token_header, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success": False, "error": token_decoded.get("error")}), 401

    # Extract user details from token payload
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Missing user ID in token"}), 400

    # Parse JSON body
    data = request.get_json() or {}

    # Validate required fields from request data
    balance = data.get("balance")
    try:
        if balance <= 0:
            return jsonify({"success": False, "error": "Balance must be a positive integer"}), 400
    except Exception as Err:
        return jsonify({"success": False, "error": "Invalid balance value"}), 400

    ret = orderBookInst.set_wallet_balance(user_id, balance)
    return jsonify({"success": ret, "message": f"Wallet balance for {user_id} set to {balance} is {ret}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200, debug=False)