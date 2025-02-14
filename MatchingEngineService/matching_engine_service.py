from flask import Flask, request, jsonify
from order_book import orderBookInst  # Correct import

app = Flask(__name__)

@app.route('/setWallet', methods=['POST'])
def set_wallet():
    """
    Sets or updates a user's wallet balance.
    JSON expected: { "user_id": "uuid", "balance": 5000 }
    """ 
    data = request.get_json()
    user_id = data.get("user_id")
    balance = data.get("balance")

    if not user_id or balance is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    orderBookInst.update_wallet_balance(user_id, balance)
    return jsonify({"success": True, "message": f"Wallet balance for {user_id} set to {balance}."})

@app.route('/placeOrder', methods=['POST'])
def place_order():
    """
    Accepts JSON input:
    { "stock_tx_id": "uuid" }
    1 - Save remaining quanity and price
    2 - Remove limit sell from ticker
    3 - Add remaining stock quantity back to user profile
    4 - Update stock transaction log to display cancelled
    """
    data = request.get_json()
    order_id = data.get("order_id")
    user_id = data.get("user_id")
    order_type = data.get("type")
    ticker = data.get("ticker")
    quantity = data.get("quantity")
    price = data.get("price")

    # if not user_id or not order_type or not ticker or quantity is None or price is None:
    #     return jsonify({"success": False, "error": "Missing required fields"}), 400

    if order_type == "BUY":
        result = orderBookInst.add_buy_order(user_id, order_id, ticker, price, quantity)
        return jsonify(result), (200 if result["success"] else 400)
    elif order_type == "SELL":
        orderBookInst.add_sell_order(user_id, order_id, ticker, price, quantity)
        return jsonify({"success": True, "message": f"Sell order placed for {ticker}."})
    else:
        return jsonify({"success": False, "error": "Invalid order type"}), 400
    
    return jsonify(result), (200 if result["success"] else 400)

@app.route('/matchOrders', methods=['POST'])
def match_orders():
    """ Matches and executes orders from the order book. """
    executed_trades = orderBookInst.match_orders()
    
    return jsonify({"success": True, "executed_trades": executed_trades})

@app.route('/cancelOrder', methods=['POST'])
def cancel_order():

    # False = Trade already executed/Trade does no exist
    # True = Trade cancelled
    data = request.get_json()
    result, reason = orderBookInst.cancel_user_order(data['user_id'], data['stock_tx_id'])
    
    return result, reason

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5300)
    
    
    
    
# @app.route('/registerStock', methods=['POST'])
# def instantiate_stock():
#     """
#     Handles stock registration from User Profile Service.
#     Accepts JSON input:
#     { "stock_id": "uuid", "ticker": "AAPL", "quantity": 1000, "price": 150 }
#     """
#     data = request.get_json()
#     stock_id = data.get("stock_id")
#     ticker = data.get("ticker")
#     quantity = data.get("quantity")
#     price = data.get("price")
#     if not stock_id or not ticker or quantity is None or price is None:
#         return jsonify({"success": False, "error": "Missing required fields"}), 400
    
#     stocks[stock_id] = {"ticker": ticker, "quantity": quantity, "price": price}
    
#     # Store stock in order book
#     order_book.orderBookInst.add_sell_order(ticker, price, quantity)
    
#     return jsonify({"success": True, "message": f"Stock {ticker} registered and added to order book."})
