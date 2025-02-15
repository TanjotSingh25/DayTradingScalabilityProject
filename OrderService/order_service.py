from flask import Flask, request, jsonify
import helpers
import os

app = Flask(__name__)

# Endpoint of the Matching Engine Service for order matching
MATCHING_ENGINE_URL = "http://matching_engine_service:5300/placeOrder"
MATCHING_ENGINE_CANCELLATION_URL = "http://matching_engine_service:5300/cancelOrder"

secret_key = os.environ.get("SECRET_KEY")
print("The Secret key is: ", secret_key, "In file Order_service")

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
    # Sanity check
    # 1 - Validate the order request
    is_valid, validation_response = helpers.order_service_sanity_check(request_data)
    if not is_valid:
        # 412 Precondition Failed -- Erronouse field(s)
        return jsonify(validation_response), 412

    # 2 - Decrypt & validate token
    token = request_data.get("token")
    success, token_payload = helpers.decrypt_and_validate_token(token, secret_key)
    if not success:
        return jsonify({"success": False, "error": token_payload["error"]}), 401
    # 3 -  verify user_name exists via postgreSQL
    user_id = token_payload.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "No user_id in token"}), 400

    order_payload = {
        # Generate Order_ID
        "order_id": helpers.generate_order_id(),
        
        # Set information to pass to Matching Engine
        "stock_id": data["stock_id"],
        "order_type": data["order_type"],
        "quantity": data["quantity"],
        "price": data["price"],
        
        # Set the Type 'Buy Market' or 'Sell Limit'
        "type": "MARKET" if data["is_buy"] else "LIMIT",
        
        # Place token information in payload
        "user_id": token_values.get("user_id"),
        "user_name": token_values.get("user_name")
        }

    # Call the matching engine endpoint
    try:
        response = request.post(MATCHING_ENGINE_URL, json=order_payload)
        if response.status_code == 200:
            matching_result = response.json()
        else:
            matching_result = {"success": False, "error": "Matching engine error"}
    except Exception as e:
        matching_result = {"success": False, "error": str(e)}

    # Return the response from matching engine
    return jsonify({"success": True, "data": matching_result}), 200

@app.route('/getStockTransactions', methods=['GET'])
def get_stock_transactions():
    """
    Accepts JSON input:
    {
        "token": "jwt_token"
    }

    Returns a list of the user's stock transactions, e.g.:
    {
        "success": true,
        "data": [
        {
            "stock_tx_id": "uuid",
            "stock_id": "uuid",
            "quantity": 50,
            "order_status": "COMPLETED",
            "price": 135,
            "timestamp": "2025-01-26T12:00:00Z"
        }
                ]
    }
    """
    # Grab the JSON body
    request_data = request.get_json()
    # Sanity check
    # Validate and decrypt token
    token = request_data.get("token")
    success, token_payload = helpers.decrypt_and_validate_token(token, secret_key)
    if not success:
        return jsonify({"success": False, "error": token_payload["error"]}), 401

    user_id = token_payload.get("user_id")
    if not user_id:
        return jsonify({"success": False, "data": None, "message": "No User ID in token"}), 400

    # 3) Query MongoDB for user's transactions
    transactions_cursor = db["stock_transactions"].find({"user_id": user_id})

    # 4) Build the response data array
    user_transactions = []
    for doc in transactions_cursor:
        user_transactions.append({
            "stock_tx_id": str(doc.get("tx_id")),      # Might be an ObjectId or a string
            "parent_stock_tx_id": str(doc.get("parent_tx_id")) if doc.get("parent_tx_id") else None,
            "stock_id": str(doc.get("stock_id")),
            "quantity": doc.get("quantity", 0),
            "order_status": doc.get("status", ""),
            "price": doc.get("price", 0),
            "is_buy": doc.get("is_buy", False),
            "order_type": doc.get("order_type", ""),
            # Use doc.get("timestamp") or doc.get("created_at"), depending on your schema
            "timestamp": doc.get("timestamp") or doc.get("created_at") or ""
        })

    # 5) Return JSON response
    return jsonify({
        "success": True,
        "data": user_transactions
    })

# Cancel exisitng buy or sell order
@app.route('/cancelStockTransaction', methods=['POST'])
def cancel_stock_transaction():
    """
    Accepts JSON input:
    { "token": "jwt_token", "stock_tx_id": "uuid" }
    """
    data = request.get_json()
    # Token Check - Decrypt and validate JWT token, if token is invalid, returns false message
    # Validate and decrypt token
    token = data.get("token")
    success, token_payload = helpers.decrypt_and_validate_token(token, secret_key)
    if not success:
        return jsonify({"success": False, "error": token_payload["error"]}), 401

    # Sanity Check
    if not data.get("stock_tx_id"):
        return jsonify({"success": False, "error": "Did not send stock transaction ID"}), 200
    
    cancelation_payload = {
        "stock_tx_id": token_payload.get("stock_tx_id"),
        "user_id": token_payload.get("user_id"),
        "user_name": token_payload.get("user_name")
    }
    # Call the matching engine endpoint to cancel a transaction
    try:
        response = request.post(MATCHING_ENGINE_CANCELLATION_URL, json={cancelation_payload})
        if response.status_code == 200:
            matching_result = response.json()
        else:
            matching_result, code = {"success": False, "error": "Matching engine error"}, 400
    except Exception as e:
        matching_result, code = {"success": False, "error": str(e)}, 400
    
    return jsonify(matching_result), code
    #return jsonify({"success": True, "data": None})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200)
