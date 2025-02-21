from flask import Flask, request, jsonify
#from order_book import orderBookInst  # Correct import
import order_book
import logging
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

orderBookInst = order_book.OrderBook()
@app.route('/setWallet', methods=['POST'])
def set_wallet():
    """
    Sets or updates a user's wallet balance.
    JSON expected: { "user_id": "uuid", "balance": 5000 }
    """
    logging.info(orderBookInst.sell_orders)
    logging.info(orderBookInst.buy_orders)
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
    #order_id = data.get("order_id")
    user_id = data.get("user_id")
    order_type = data.get("order_type")
    quantity = data.get("quantity")
    price = data.get("price")

    # Ensure stock_id is safely extracted
    stock_id = data.get("stock_id", "")

    # if not user_id or not order_type or not ticker or quantity is None or price is None:
    #     return jsonify({"success": False, "error": "Missing required fields"}), 400
    logging.info(orderBookInst.sell_orders)
    logging.info(orderBookInst.buy_orders)
    try:
        if order_type == "MARKET":
            result = orderBookInst.add_buy_order(user_id, stock_id, price, quantity)
            return jsonify(result), (200 if result["success"] else 400)
        elif order_type == "LIMIT":
            result = orderBookInst.add_sell_order(user_id, stock_id, price, quantity)
            executed_trades = orderBookInst.match_orders()
            executed_trades.append(f"Sell order placed for {stock_id}.")
            return jsonify({"success": True, "message": executed_trades }), (200 if result["success"] else 400)
    except Exception as e:
        # Log the detailed error so you can debug it
        logging.exception("Error processing order:")
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": False, "error": "Invalid order type"}), 400

@app.route('/matchOrders', methods=['POST'])
def match_orders():
    """ Matches and executes orders from the order book. """
    logging.info(orderBookInst.sell_orders)
    logging.info(orderBookInst.buy_orders)
    executed_trades = orderBookInst.match_orders()
    
    return jsonify({"success": True, "executed_trades": executed_trades})

@app.route('/cancelOrder', methods=['POST'])
def cancel_order():
    logging.info(orderBookInst.sell_orders)
    logging.info(orderBookInst.buy_orders)
    # False = Trade already executed/Trade does no exist
    # True = Trade cancelled
    data = request.get_json()
    result = orderBookInst.cancel_user_order(data['user_id'], data['stock_tx_id'])
    
    code = 400
    return_message = "Order does not Exist"
    if result:
        code = 200
        return_message = None

    return {"success" : result, "data": return_message}, code

@app.route('/getPrices', methods=['GET'])
def getPrices():
    # Calls orderbookInst to get current prices of each LIMIT SELL Ticker
    logging.info(orderBookInst.sell_orders)
    logging.info(orderBookInst.buy_orders)
    data = request.get_json()
    result, stock_prices = orderBookInst.find_stock_prices()

    return {"success" : result, "data": stock_prices}, 200

if __name__ == '__main__':
    
    app.run(host='0.0.0.0', port=5300)
