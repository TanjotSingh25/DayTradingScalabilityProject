from flask import Flask, request, jsonify
import order_book

app = Flask(__name__)


@app.route('/matchOrder', methods=['POST'])
def match_order():
    """
    Accepts JSON input:
    { "order_id": "uuid", "type": "BUY_MARKET", "stock_id": "uuid", "quantity": 50 }
    """
    data = request.get_json()
    # TODO: Matching logic: update in-memory order book, return matched orders
    return jsonify({"success": True, "data": {"matched_orders": []}})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200)
