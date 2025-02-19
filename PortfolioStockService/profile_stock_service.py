# source(s): Assistance provided by ChatGPT (permitted by course instructor)

from flask import Flask, request, jsonify
from flask_restful import Api, Resource
from pymongo import MongoClient, errors
import os
import uuid
import jwt
import requests

# Initialize Flask app
app = Flask(__name__)
api = Api(app)

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Make sure it's defined in docker-compose.yml.")

try:
    client = MongoClient(MONGO_URI)
    db = client["trading_system"]
    stocks_collection = db["stocks"]
    portfolios_collection = db["portfolios"]
    wallets_collection = db["wallets"]

    # Ensure necessary indexes for faster lookups
    stocks_collection.create_index("stock_id", unique=True)
    portfolios_collection.create_index("user_id", unique=True)
    wallets_collection.create_index("user_id", unique=True)

except errors.ConnectionFailure:
    print("Error: Unable to connect to MongoDB. Ensure MongoDB is running in Docker.")
    raise

# -----------------------
# Helper Function for User Identification (JWT Ready)
# -----------------------

JWT_SECRET = "django-insecure-uj@e4q80n@l2ml)rl*-^s84djzyn5ws6vt7@&h!tp*xf)p05t#"
JWT_ALGORITHM = "HS256"

def get_user_id():
    """
    Extracts user_id from the Authorization JWT token.
    - Validates and decodes JWT from the request headers.
    - If valid, extracts `user_id` from the payload.
    - Returns an error message if token is missing or invalid.
    """

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return {"error": "Missing or invalid Authorization header"}

    token = auth_header.split(" ")[1]  # Extract token

    try:
        # Decode the JWT token
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"user_id": payload.get("user_id")}
    except jwt.ExpiredSignatureError:
        return {"error": "Token has expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}




# -----------------------
# Stock Management APIs
# -----------------------

class CreateStock(Resource):
    """
    Endpoint: POST /createStock
    Description: Creates a new stock entry in the database.

    Expected Request:
    Headers:
      Content-Type: application/json
      Authorization: Bearer <JWT_TOKEN> (future authentication)
    Body:
      {
        "stock_name": "Apple"
      }
    """
    def post(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401  # Unauthorized
            user_id = user_data["user_id"]

            data = request.get_json()
            stock_name = data.get("stock_name")

            if not stock_name:
                return {"success": False, "data": {"error": "Missing stock_name"}}, 400

            stock_id = str(uuid.uuid4())  # Simulating stock ID for now
            stock = {"stock_id": stock_id, "stock_name": stock_name}

            stocks_collection.insert_one(stock)

            return {"success": True, "data": {"stock_id": stock_id}}, 201

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500


class AddStockToUser(Resource):
    """
    Endpoint: POST /addStockToUser
    Description: Adds a stock to the user's portfolio.

    Expected Request:
    Headers:
      Content-Type: application/json
      Authorization: Bearer <JWT_TOKEN> (future authentication)
    Body:
      {
        "stock_id": "123456",
        "quantity": 10
      }
    """
    def post(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401  # Unauthorized
            user_id = user_data["user_id"]
            data = request.get_json()
            stock_id = data.get("stock_id")
            quantity = data.get("quantity", 1)

            if not user_id:
                return {"success": False, "data": {"error": "Missing user_id"}}, 400

            if not stock_id:
                return {"success": False, "data": {"error": "Missing stock_id"}}, 400

            if quantity <= 0:
                return {"success": False, "data": {"error": "Quantity must be greater than zero"}}, 400

            # Find the stock details
            stock = stocks_collection.find_one({"stock_id": stock_id})
            if not stock:
                return {"success": False, "data": {"error": "Stock not found"}}, 404

            # Update portfolio: If stock exists, increment quantity. Otherwise, add it.
            result = portfolios_collection.update_one(
                {"user_id": user_id, "data.stock_id": stock_id},
                {"$inc": {"data.$.quantity_owned": quantity}},
                upsert=False
            )

            if result.matched_count == 0:
                portfolios_collection.update_one(
                    {"user_id": user_id},
                    {"$push": {"data": {"stock_id": stock_id, "stock_name": stock["stock_name"], "quantity_owned": quantity}}},
                    upsert=True
                )

            return {"success": True, "data": None}, 200

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500


class GetStockPortfolio(Resource):
    """
    Endpoint: GET /getStockPortfolio
    Description: Retrieves the user's stock portfolio.

    Expected Request:
    Headers:
      Authorization: Bearer <JWT_TOKEN> (future authentication)
    """
    def get(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401  # Unauthorized
            user_id = user_data["user_id"]
            portfolio = portfolios_collection.find_one({"user_id": user_id}, {"data": 1})

            # If user has no portfolio, return empty list instead of error
            if not portfolio or "data" not in portfolio:
                return {"success": True, "data": []}, 200

            return {"success": True, "data": portfolio["data"]}, 200

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500
        
class GetStockPrices(Resource):
    """
    Endpoint: GET /getStockPrices
    Description: Retrieves the prices for stocks.

    Expected Request:
    Headers:
      Authorization: Bearer <JWT_TOKEN> (future authentication)
    """
    def get(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data":{"error":user_data["error"]}},401
            user_id = user_data["user_id"]
            portfolio = portfolios_collection.find_one({"user_id":user_id})
            if not portfolio or "data" not in portfolio:
                return {"success": True, "data": []}, 200
            
            stock_prices = []
            for stock_item in portfolio["data"]:
                stock_id = stock_item["stock_id"]
                stock = stocks_collection.find_one({"stock_id": stock_id})
                if stock:
                    price = stock.get("price",None)
                    stock_prices.append({
                        "stock_id":stock_id,
                        "stock_name": stock_item["stock_name"],
                        "price": price,
                        "quantity_owned": stock_item["quantity_owned"]
                    })
                else:
                    stock_prices.append({
                        "stock_id": stock_id,
                        "error": "Stock details not found"
                    })
            return {"success":True,"data":stock_prices}, 200
        except Exception as e:
            return {"success":False,"data":{"error":str(e)}}, 500

# -----------------------
# Wallet Management APIs
# -----------------------

class AddMoneyToWallet(Resource):
    """
    Endpoint: POST /addMoneyToWallet
    Description: Adds money to the user's wallet balance.

    Expected Request:
    Headers:
      Content-Type: application/json
      Authorization: Bearer <JWT_TOKEN> (future authentication)
    Body:
      {
        "amount": 1000
      }
    """
    def post(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401  # Unauthorized
            user_id = user_data["user_id"]
            data = request.get_json()
            amount = data.get("amount")

            if not user_id:
                return {"success": False, "data": {"error": "Missing user_id"}}, 400

            if amount is None or amount <= 0:
                return {"success": False, "data": {"error": "Amount must be greater than zero"}}, 400

            wallets_collection.update_one(
                {"user_id": user_id},
                {"$inc": {"balance": amount}},  # Only update balance
                upsert=True
            )

            return {"success": True, "data": None}, 200

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500


class GetWalletBalance(Resource):
    """
    Endpoint: GET /getWalletBalance
    Description: Retrieves the user's wallet balance.

    Expected Request:
    Headers:
      Authorization: Bearer <JWT_TOKEN> (future authentication)
    """
    def get(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401  # Unauthorized

            user_id = user_data["user_id"]
            balance = 0  # Initialize balance to 0

            wallet = wallets_collection.find_one({"user_id": user_id}, {"balance": 1})
            if wallet and "balance" in wallet:
                balance = wallet["balance"]

            return {"success": True, "data": {"balance": balance}}, 200

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500


class GetWalletTransactions(Resource):
    """
    Endpoint: GET /getWalletTransactions
    Description: Retrieves all wallet transactions for the user.

    Expected Request:
    Headers:
      Authorization: Bearer <JWT_TOKEN> (future authentication)
    """
    def get(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401  # Unauthorized
            user_id = user_data["user_id"]
            wallet = wallets_collection.find_one({"user_id": user_id}, {"transactions": 1})
            if not wallet or "transactions" not in wallet:
                return {"success": False, "data": {"error": "No transactions found"}}, 404

            return {"success": True, "data": wallet["transactions"]}, 200

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500


# -----------------------
# API Route Mapping
# -----------------------
api.add_resource(CreateStock, "/createStock")
api.add_resource(AddStockToUser, "/addStockToUser")
api.add_resource(GetStockPortfolio, "/getStockPortfolio")
api.add_resource(AddMoneyToWallet, "/addMoneyToWallet")
api.add_resource(GetWalletBalance, "/getWalletBalance")
api.add_resource(GetWalletTransactions, "/getWalletTransactions")

# -----------------------
# Health Check Route
# -----------------------
@app.route("/", methods=["GET"])
def health_check():
    return {"success": True, "message": "Portfolio & Stock Service is running"}

# Run Flask server
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
