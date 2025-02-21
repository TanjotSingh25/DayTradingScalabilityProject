from flask import Flask, request, jsonify
import helpers
import os
from pymongo import MongoClient, errors
from flask_cors import CORS
import logging as logger
import requests
import uuid
import datetime

app = Flask(__name__)
CORS(app)

MONGO_URI = os.getenv("MONGO_URI")

JWT_SECRET = "django-insecure-uj@e4q80n@l2ml)rl*-^s84djzyn5ws6vt7@&h!tp*xf)p05t#"
JWT_ALGORITHM = "HS256"

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Make sure it's defined in docker-compose.yml.")

try:
    client = MongoClient(MONGO_URI)
    db = client["trading_system"]
    # MongoDB collections
    wallet_transactions_collection = db["wallets_transaction"]
    portfolios_collection = db["portfolios"]  # this ensures portfolios collection is initialized
    stock_transactions_collection = db["stock_transactions"]  # instantiating new collection for transactions

except errors.ConnectionFailure:
    print("Error: Unable to connect to MongoDB. Ensure MongoDB is running in Docker.")
    raise

# Endpoint of the Matching Engine Service for order matching
MATCHING_ENGINE_URL = "http://matching_engine_service:5300/placeOrder"
MATCHING_ENGINE_CANCELLATION_URL = "http://matching_engine_service:5300/cancelOrder"
MATCHING_ENGINE_STOCK_PRICES_URL = "http://matching_engine_service:5300/getPrices"

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
    logger.info(request_data, "Printing Here-----------------------------------")
    
    # 1 - Decrypt & validate token
    token = request.headers.get("token")
    token_decoded = helpers.decrypt_and_validate_token(token, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success: false", token_decoded})
    
    # 2 - Validate the order request
    is_valid, validation_response = helpers.order_service_sanity_check(request_data)
    if not is_valid:
        # 412 Precondition Failed
        return jsonify(validation_response), 401

    # 3 -  verify that the user_name exists via postgreSQL
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "No user_id in token"}), 400

    order_payload = {
        # generates Order_ID
        "order_id": str(uuid.uuid4()),
        
        # set the information to pass to Matching Engine
        "stock_id": request_data["stock_id"],
        "order_type": request_data["order_type"],
        "quantity": request_data["quantity"],
        "price": request_data.get("price"),
        
        # Place token information in payload
        "user_id": user_id
        }

    logger.warning(order_payload["order_id"])

    # Call the matching engine endpoint
    try:
        response = requests.post(MATCHING_ENGINE_URL, json=order_payload)

        # Check if the response is successful (status code 200)
        if response.status_code == 200:
            matching_result = response.json()
            return matching_result, 200
        else:
            matching_result = {"error": f"Matching engine responded with status {response.status_code}"}

    except Exception as e:
        matching_result = {"error": f"Request failed: {str(e)}"}

    return jsonify(matching_result), 200

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
        return jsonify({"success: false", token_decoded})

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
        return jsonify({"success: false", token_decoded}), 401

    stock_tx_id = data.get("stock_tx_id")
    if not stock_tx_id:
        return jsonify({"success": False, "error": "Missing stock transaction ID"}), 400

    # Extracts the user details from token payload
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Missing user ID in token"}), 400

    # Prepares the cancellation payload for the Matching Engine
    cancellation_payload = {
        "user_id": user_id,
        "stock_tx_id": stock_tx_id
    }

    # Call the Matching Engine /cancelOrder endpoint
    try:
        response = requests.post(MATCHING_ENGINE_CANCELLATION_URL, json=cancellation_payload)
        if response.status_code == 200:
            matching_result = response.json()
            code = 200
        else:
            matching_result = {"success": False, "error": "Matching Engine error"}
            code = response.status_code
    except Exception as e:
        matching_result = {"success": False, "error": str(e)}
        code = 500

    return jsonify(matching_result), code

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
        error_msg = token_decoded.get("error")
        return jsonify({"success": False, "error": error_msg}), 401

    # Extracts the user details from token payload
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Missing user ID in token"}), 400

    # Call the Matching Engine /cancelOrder endpoint
    try:
        response = requests.get(MATCHING_ENGINE_STOCK_PRICES_URL, json={'user_id': user_id})
        if response.status_code == 200:
            matching_result = response.json()
            code = 200
        else:
            matching_result = {"success": False, "error": "Matching Engine error"}
            code = response.status_code
    except Exception as e:
        matching_result = {"success": False, "error": str(e)}
        code = 500

    return jsonify(matching_result), code

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200)