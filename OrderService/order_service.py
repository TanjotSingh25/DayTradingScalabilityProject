from flask import Flask, request, jsonify

app = Flask(__name__)

# Endpoint of the Matching Engine Service for order matching
MATCHING_ENGINE_URL = "http://matching_engine_service:5300/matchOrder"

@app.route('/placeStockOrder', methods=['POST'])
def place_stock_order():
    """
    Accepts JSON input:
    { "token": "jwt_token", "stock_id": "uuid", "is_buy": true, "order_type": "MARKET", "quantity": 50 }
    """
    data = request.get_json()
    # TODO: Process order details, communicate with matching engine, store in Orders table, etc.
    return jsonify({"success": True, "data": None})

@app.route('/getStockTransactions', methods=['GET'])
def get_stock_transactions():
    """
    Accepts JSON input:
    { "token": "jwt_token" }
    """
    # TODO: Fetch and return stock transaction history
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

@app.route('/cancelStockTransaction', methods=['POST'])
def cancel_stock_transaction():
    """
    Accepts JSON input:
    { "token": "jwt_token", "stock_tx_id": "uuid" }
    """
    data = request.get_json()
    # TODO: Cancel the specified stock order if possible
    return jsonify({"success": True, "data": None})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200)
