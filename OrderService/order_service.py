from flask import Flask, request, jsonify

app = Flask(__name__)

# 0.0.0.0 means listen on every host -- Inventory service URL and port
# INVENTORY_SERVICE_URL = "http://0.0.0.0:5100/check_item"
MATCHING_ENGINE_SERVICE_URL = "http://matching_engine_service:5100/"

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    # Example endpoint, can be replaced or expanded with real logic
    data = request.get_json()
    # TODO: Interact with INVENTORY_SERVICE_URL or validate data
    return jsonify({"success": True, "data_received": data})

def is_authorized(username, token):
    pass

def has_money(username, amount_required):
    pass

def buy_sanity_check(stock_ticker, buy_price):
    pass

def sell_sanity_check(stock_ticker, quantity):
    pass

def buy(stock_ticker, quantity, buy_price):
    pass

def sell(stock_ticker, quantity, sell_price):
    pass

def cancel(order_id):
    pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
