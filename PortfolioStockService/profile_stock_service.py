# source(s): Assistance provided by ChatGPT (permitted by course instructor)

from flask import Flask, request, jsonify
from flask_restful import Api, Resource
from pymongo import MongoClient, errors
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
api = Api(app)

# MongoDB connection
try:
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
    db = client["trading_system"]
    stocks_collection = db["stocks"]
    portfolios_collection = db["portfolios"]
    wallets_collection = db["wallets"]
except errors.ConnectionFailure:
    print("Error: Unable to connect to MongoDB. Ensure MongoDB is running.")

# -----------------------
# Helper Function for User Identification (JWT Ready)
# -----------------------

def get_user_id():
    """
    Placeholder function for now.
    - Currently: Extracts user_id from request body or query params
    - Later: Will extract from JWT token in the Authorization header
    """
    data = request.get_json(silent=True) or {}
    return data.get("user_id") or request.args.get("user_id")  # Support both body & query


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
            data = request.get_json()
            stock_name = data.get("stock_name")

            if not stock_name:
                return {"success": False, "data": {"error": "Missing stock_name"}}, 400

            stock_id = str(hash(stock_name))  # Simulating stock ID for now
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
            user_id = get_user_id()
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
            user_id = get_user_id()
            portfolio = portfolios_collection.find_one({"user_id": user_id}, {"data": 1})

            # If user has no portfolio, return empty list instead of error
            if not portfolio or "data" not in portfolio:
                return {"success": True, "data": []}, 200

            return {"success": True, "data": portfolio["data"]}, 200

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500

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
            user_id = get_user_id()
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
            user_id = get_user_id()
            wallet = wallets_collection.find_one({"user_id": user_id}, {"balance": 1})
            if not wallet:
                return {"success": False, "data": {"error": "User wallet not found"}}, 404

            return {"success": True, "data": {"balance": wallet["balance"]}}, 200

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
            user_id = get_user_id()
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
