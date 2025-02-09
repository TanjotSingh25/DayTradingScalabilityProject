from flask import Flask, request, jsonify
import order_book

app = Flask(__name__)


@app.route('/matchOrder', methods=['POST'])
def match_order():
    """
    Accepts JSON input:
    { "order_id": "uuid", "type": "BUY_MARKET", "stock_id": "uuid", "quantity": 50 }
    or
    {}
    """
    data = request.get_json()
    # TODO: Matching logic: update in-memory order book, return matched orders
    return jsonify({"success": True, "data": {"matched_orders": []}})

@app.route('/cancelOrder', methods=['POST'])
def cancel_order():
    """
    Accepts JSON input:
    { "stock_tx_id": "uuid" }
    """
    # TODO: set up a "for-loop" to search for stock id in buy and sell to cancel it
    return {"success": True, "data": None}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5300)
