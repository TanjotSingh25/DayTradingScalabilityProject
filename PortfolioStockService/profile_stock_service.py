# source(s): Assistance provided by ChatGPT (permitted by course instructor)

from flask import Flask, request, jsonify
from flask_restful import Api, Resource
from pymongo import MongoClient, errors
from flask_cors import CORS
import os
import uuid
import jwt
import json
import redis

# Initialize Flask app
app = Flask(__name__)
CORS(app)
api = Api(app)

MONGO_URI = os.getenv("MONGO_URI")
REDIS_HOST = os.getenv("REDIS_HOST", "redis_wallet_cache")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Make sure it's defined in docker-compose.yml.")

try:
    # 1.5 minutes
    client = MongoClient(MONGO_URI, maxPoolSize=150, minPoolSize=50, maxIdleTimeMS=90000)
    db = client["trading_system"]
    stocks_collection = db["stocks"]
    portfolios_collection = db["portfolios"]

    # Ensure necessary indexes for faster lookups
    stocks_collection.create_index("stock_id", unique=True)
    stocks_collection.create_index("stock_name", unique=True)  # Prevent duplicate stock names
    portfolios_collection.create_index("user_id", unique=True)

except errors.ConnectionFailure:
    print("Error: Unable to connect to MongoDB. Ensure MongoDB is running in Docker.")
    raise

# Initialize Redis connection with connection pooling
try:
    pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=0, max_connections=100)
    redis_client = redis.StrictRedis(connection_pool=pool, decode_responses=True)
except Exception as e:
    print(f"Error connecting to Redis: {e}")
    raise

# -----------------------
# Helper Functions
# -----------------------

JWT_SECRET = "django-insecure-uj@e4q80n@l2ml)rl*-^s84djzyn5ws6vt7@&h!tp*xf)p05t#"
JWT_ALGORITHM = "HS256"

def get_user_id():
    """
    Extracts user_id from the Authorization JWT token.
    Accepts token from either the "token" header or "Authorization: Bearer <token>" header.
    """
    token = request.headers.get("token")

    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        return {"error": "Missing token header"}

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"user_id": payload.get("user_id")}
    except jwt.ExpiredSignatureError:
        return {"error": "Token has expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}

def get_request_data():
    """
    Extracts JSON data from the request, working with or without the Content-Type header.
    """
    data = request.get_json(silent=True, force=True)

    if data is None and request.data:
        try:
            data = json.loads(request.data)
        except json.JSONDecodeError:
            data = None

    return data

def initialize_user_if_not_exists(user_id):
    """
    Initializes user documents (portfolio and wallet) with default values if they don't exist.
    """
    portfolios_collection.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"user_id": user_id, "data": []}},
        upsert=True
    )

# -----------------------
# Stock Management APIs
# -----------------------

class CreateStock(Resource):
    def post(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401

            data = get_request_data()
            if not data or "stock_name" not in data:
                return {"success": False, "data": {"error": "Missing stock_name"}}, 400

            stock_name = data["stock_name"].strip()
            
            # Check if stock with the same name already exists
            if stocks_collection.find_one({"stock_name": stock_name}):
                return {"success": False, "data": {"error": "A stock with this name already exists."}}, 400

            stock_id = str(uuid.uuid4())
            stock = {"stock_id": stock_id, "stock_name": stock_name}
            stocks_collection.insert_one(stock)

            return {"success": True, "data": {"stock_id": stock_id}}, 201

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500

class AddStockToUser(Resource):
    def post(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401

            user_id = user_data["user_id"]
            initialize_user_if_not_exists(user_id)

            data = get_request_data()
            stock_id = data.get("stock_id")
            quantity = data.get("quantity", 1)

            if not stock_id:
                return {"success": False, "data": {"error": "Missing stock_id"}}, 400

            if quantity <= 0:
                return {"success": False, "data": {"error": "Quantity must be greater than zero"}}, 400

            stock = stocks_collection.find_one({"stock_id": stock_id})
            if not stock:
                return {"success": False, "data": {"error": "Stock not found"}}, 404

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
    def get(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401

            user_id = user_data["user_id"]
            initialize_user_if_not_exists(user_id)

            portfolio = portfolios_collection.find_one({"user_id": user_id}, {"data": 1})
            return {"success": True, "data": portfolio.get("data", [])}, 200

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500

# -----------------------
# Wallet Management APIs
# -----------------------

class AddMoneyToWallet(Resource):
    def post(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401

            user_id = user_data["user_id"]
            data = get_request_data()
            amount = data.get("amount")

            if not isinstance(amount, (int, float)) or amount <= 0:
                return {"success": False, "data": {"error": "Amount must be a valid number greater than zero"}}, 400

            # Update balance in Redis
            redis_client.incrbyfloat(f"wallet_balance:{user_id}", amount)

            return {"success": True, "data": None}, 200

        except Exception as e:
            return {"success": False, "data": {"error": str(e)}}, 500

class GetWalletBalance(Resource):
    def get(self):
        try:
            user_data = get_user_id()
            if "error" in user_data:
                return {"success": False, "data": {"error": user_data["error"]}}, 401

            user_id = user_data["user_id"]
            
            # Fetch balance from Redis
            balance = redis_client.get(f"wallet_balance:{user_id}")
            balance = int(float(balance)) if balance else 0
            
            return {"success": True, "data": {"balance": balance}}, 200

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

# -----------------------
# Health Check Route
# -----------------------
@app.route("/", methods=["GET"])
def health_check():
    return {"success": True, "message": "Portfolio & Stock Service is running"}

# Run Flask server
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)