from flask import Flask, request, jsonify
import helpers
import os
from pymongo import MongoClient, errors
import logging
import requests

app = Flask(__name__)

MONGO_URI = os.getenv("MONGO_URI")

JWT_SECRET = "django-insecure-uj@e4q80n@l2ml)rl*-^s84djzyn5ws6vt7@&h!tp*xf)p05t#"
JWT_ALGORITHM = "HS256"

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Make sure it's defined in docker-compose.yml.")

try:
    client = MongoClient(MONGO_URI)
    db = client["trading_system"]
    # MongoDB collections
    wallet_transactions_collection = db["wallets"]
    portfolios_collection = db["portfolios"]  # Ensure portfolios collection is initialized
    stock_transactions_collection = db["stock_transactions"]  # New collection for transactions

except errors.ConnectionFailure:
    print("Error: Unable to connect to MongoDB. Ensure MongoDB is running in Docker.")
    raise

# Endpoint of the Matching Engine Service for order matching
MATCHING_ENGINE_URL = "http://matching_engine_service:5300/placeOrder"
MATCHING_ENGINE_CANCELLATION_URL = "http://matching_engine_service:5300/cancelOrder"

#secret_key = os.environ.get("SECRET_KEY")
#print("The Secret key is: ", secret_key, "In file Order_service")

# Place new order -- Market Buy, Limit Sell
# TODO: Process order details, communicate with matching engine, store in Orders table, etc.
@app.route('/placeStockOrder', methods=['POST'])
def place_stock_order():
    """
    Accepts JSON input:
    { "token": "jwt_token", "stock_id": "uuid", "is_buy": true, "order_type": "MARKET", "quantity": 50 }
    """
    # Grab the JSON body
    request_data = request.get_json()
    logging.info(request_data, "Printing Here-----------------------------------")
    print(request_data, "Printing Here-----------------------------------")
    # ------ Sanity check ------
    # 1 - Decrypt & validate token
    token = request.headers.get("Authorization")
    token_decoded = helpers.decrypt_and_validate_token(token, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success: false", token_decoded})
    
    # 2 - Validate the order request
    is_valid, validation_response = helpers.order_service_sanity_check(request_data)
    if not is_valid:
        # 412 Precondition Failed -- Erronouse field(s)
        return jsonify(validation_response), 412

    # 3 -  verify user_name exists via postgreSQL
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "No user_id in token"}), 400

    order_payload = {
        # Generate Order_ID
        "order_id": helpers.generate_order_id(),
        
        # Set information to pass to Matching Engine
        "stock_id": request_data["stock_id"],
        "order_type": request_data["order_type"],
        "quantity": request_data["quantity"],
        "price": request_data.get("price"),
        
        # Place token information in payload
        "user_id": user_id
        }

    # Call the matching engine endpoint
    try:
        response = requests.post(MATCHING_ENGINE_URL, json=order_payload)

        # Check if response is successful (status code 200)
        if response.status_code == 200:
            matching_result = response.json()
            return matching_result, 200
        else:
            matching_result = {"error": f"Matching engine responded with status {response.status_code}"}

    except Exception as e:
        matching_result = {"error": f"Request failed: {str(e)}"}

    # Return the response from matching engine
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
                "price": 135,
                "is_buy": true,
                "order_type": "MARKET",
                "timestamp": "2025-01-26T12:00:00Z"
            }
        ]
    }
    """
    # Grab the JSON body
    request_data = request.get_json()

    # Validate and decrypt token
    token = request.headers.get("Authorization")
    token_decoded = helpers.decrypt_and_validate_token(token, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success: false", token_decoded})

    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "data": None, "message": "No User ID in token"}), 400

    # Query MongoDB for user's transactions (from `stock_transactions_collection`)
    transactions_cursor = stock_transactions_collection.find({"user_id": user_id})

    # Build the response data array
    user_transactions = []
    for doc in transactions_cursor:
        user_transactions.append({
            "stock_tx_id": str(doc.get("stock_tx_id")),  # Unique transaction ID
            "parent_stock_tx_id": str(doc.get("parent_stock_tx_id")) if doc.get("parent_stock_tx_id") else None,
            "stock_id": str(doc.get("stock_id")),  # Associated stock ID
            "wallet_tx_id": str(doc.get("wallet_tx_id")) if doc.get("wallet_tx_id") else None,  # Wallet transaction reference
            "quantity": doc.get("quantity", 0),
            "order_status": doc.get("order_status", ""),  # Use correct field for status
            "price": doc.get("stock_price", 0),  # Ensuring price is retrieved correctly
            "is_buy": doc.get("is_buy", False),
            "order_type": doc.get("order_type", ""),  # Order type (MARKET, LIMIT, etc.)
            "timestamp": doc.get("time_stamp") or doc.get("created_at") or ""
        })

    # Return JSON response
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
    data = request.get_json()

    # Validate and decrypt token
    token = request.headers.get("Authorization")
    token_decoded = helpers.decrypt_and_validate_token(token, JWT_SECRET)
    if "error" in token_decoded:
        return jsonify({"success: false", token_decoded})

    # Ensure stock transaction ID is provided
    stock_tx_id = data.get("stock_tx_id")
    if not stock_tx_id:
        return jsonify({"success": False, "error": "Missing stock transaction ID"}), 400

    # Extract user details from token payload
    user_id = token_decoded.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "Missing user ID in token"}), 400

    # Prepare cancellation payload
    cancellation_payload = {
        "user_id": user_id,
        "stock_tx_id": stock_tx_id
    }

    # Call the Matching Engine `/cancelOrder` endpoint
    try:
        response = requests.post(MATCHING_ENGINE_CANCELLATION_URL, json=cancellation_payload)

        if response.status_code == 200:
            matching_result = response.json()
        else:
            matching_result, code = {"success": False, "error": "Matching Engine error"}, response.status_code
    except Exception as e:
        matching_result, code = {"success": False, "error": str(e)}, 500

    return jsonify(matching_result), code



# @app.route('/getWalletTransactions', methods=['POST'])
# def get_wallet_transactions():
#     """
#     Accepts JSON input:
#     { "token": "user1Token" }

#     Returns user's wallet transactions in the expected format:
#     {
#         "success": true,
#         "data": [
#             {
#                 "wallet_tx_id": "<googleWalletTxId>",
#                 "stock_tx_id": "<googleStockTxId>",
#                 "is_debit": true,
#                 "amount": 1350,
#                 "time_stamp": "<timestamp>"
#             }
#         ]
#     }
#     """

#     # Get request JSON data
#     data = request.get_json()
    
#     # Extract token from request
#     token = data.get("token")
#     if not token:
#         return jsonify({"success": False, "error": "Missing token"}), 400

#     # Validate and decrypt token
#     success, token_payload = helpers.decrypt_and_validate_token(token, secret_key)
#     if not success:
#         return jsonify({"success": False, "error": token_payload["error"]}), 401

#     # Extract user_id from decrypted token
#     user_id = token_payload.get("user_id")
#     if not user_id:
#         return jsonify({"success": False, "error": "Invalid token: Missing user ID"}), 400

#     # Query MongoDB for wallet transactions
#     transactions_cursor = wallet_transactions_collection.find({"user_id": user_id})

#     # Build response data
#     wallet_transactions = []
#     for doc in transactions_cursor:
#         wallet_transactions.append({
#             "wallet_tx_id": str(doc.get("wallet_tx_id")),
#             "stock_tx_id": str(doc.get("stock_tx_id")) if doc.get("stock_tx_id") else None,
#             "is_debit": doc.get("is_debit", False),
#             "amount": doc.get("amount", 0),
#             "time_stamp": doc.get("time_stamp") or doc.get("created_at") or datetime.now().isoformat()
#         })

#     return jsonify({
#         "success": True,
#         "data": wallet_transactions
#     }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200)
