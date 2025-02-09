from flask import Flask, request, jsonify
import helpers
import os

app = Flask(__name__)

# Endpoint of the Matching Engine Service for order matching
MATCHING_ENGINE_URL = "http://matching_engine_service:5300/matchOrder"
MATCHING_ENGINE_CANCELLATION_URL = "http://matching_engine_service:5300/cancelOrder"

secret_key = os.environ.get("SECRET_KEY")
print("The Secret key is: ", secret_key, "In file Order_service")

# Place new order -- Market Buy, Limit Sell
# TODO: Process order details, communicate with matching engine, store in Orders table, etc.
@app.route('/placeStockOrder', methods=['POST'])
def place_stock_order():
    """
    Request body format for placeStockOrder:
        • BuyMarket:
            {“stock_id”:1,”is_buy”:true,”order_type”:”MARKET”,”quantity”:10,”price”:null}
        • Sell Limit: 
            {“stock_id”:1,”is_buy”:false,”order_type”:”LIMIT”,”quantity”:10,”price”:80}
        • When market order is being placed price should be passed as null.
        • If the API is fed any other values for the above keys, it should return an appropriate
        response in error message
    Accepts JSON input:
    { "token": "jwt_token", "stock_id": "uuid", "is_buy": true, "order_type": "MARKET", "quantity": 50 }
    """
    # Read Order
    data = request.get_json()
    # Sanity Check -- Token and Data

    # 1 -- Decrypt and validate JWT token, if token is invalid, returns false message
    if not helpers.decrypt_and_validate_token(data.get["token"], secret_key):
        # If false, then invalid token -- 401 (Unauthorized) HTTP Code.
        return jsonify({"success": "false", "data": "null" , "message": "The given JWT Token is Invalid"}), 401

    # 2 -- Validate json data payload request
    failed_sanity, return_message = helpers.order_service_sanity_check(data)
    if failed_sanity:
        # 412 Precondition Failed -- Erronouse field(s)
        return jsonify(return_message), 412

    order_payload = {}
    # Filter by Order Type -- Market Buy or Limit Sell Order
    if data["is_buy"] == True:
        # Sanity Check -- Has enough Money -- If account doesn't have zero
        order_payload["type"] = "MARKET"
    else:
        # Sanity Check -- Has enough stocks to sell
        order_payload["type"] = "LIMIT"
        # Price for limit sell
        order_payload["quantity"] = data["quantity"]
        print("Limit Sell")

    # Prepare final order payload message for matching engine
    # 1 - Generate Order ID
    order_payload["order_id"] = helpers.generate_order_id()
    # 2 - Set stock sticker ID
    order_payload["stock_id"] = data["stock_id"]
    # 3 - Set stock purchase/sell price

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

# Gets and Return User Stock History
@app.route('/getStockTransactions', methods=['GET'])
def get_stock_transactions():
    """
    Accepts JSON input:
    { "token": "jwt_token" }
    """
    # TODO: Fetch and return stock transaction history
    # Fetch using user id, return user_id: data[]

    # Example
    return jsonify({
        "success": True,
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
    })

# Cancel exisitng buy or sell order
@app.route('/cancelStockTransaction', methods=['POST'])
def cancel_stock_transaction():
    """
    Accepts JSON input:
    { "token": "jwt_token", "stock_tx_id": "uuid" }
    """
    code = 200
    # Token Check - Decrypt and validate JWT token, if token is invalid, returns false message
    if not helpers.decrypt_and_validate_token(data.get["token"], secret_key):
        # If false, then invalid token -- 401 (Unauthorized) HTTP Code.
        return jsonify({"success": "false", "data": "null" , "message": "The given JWT Token is Invalid"}), 401

    # Sanity Check
    if not data.get("stock_tx_id"):
        return jsonify({"success": False, "error": "Did not send stock transaction ID"}), 200
        
    data = request.get_json()
    # Call the matching engine endpoint to cancel a transaction
    try:
        response = request.post(MATCHING_ENGINE_URL, json= {"stock_tx_id": data["stock_tx_id"]})
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
