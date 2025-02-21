import re
import jwt
import time

# SECRET_KEY = env("SECRET_KEY")

def order_service_sanity_check(message):
    """
    Validates the request payload for placing a stock order.
    Ensures required fields are present, correct data types, and
    appropriate logic for buy (MARKET) vs. sell (LIMIT).
    """

    required_fields = ["stock_id", "is_buy", "order_type", "quantity"]
    # Check if the required fields exist actually
    for field in required_fields:
        if field not in message:
            return False, {"error": f"Missing required field: {field}", "success": False}

    # Check if there are any unexpected fields, if yes then throw an error
    extra_fields = [field for field in message if field not in required_fields and field not in ["price"]]
    if extra_fields:
        return False, {"error": f"Unexpected fields present: {', '.join(extra_fields)}", "success": False}

    # 1) checks if is buy is a boolean or not 
    if message.get("is_buy") not in [True, False]:
        return False, {"error": "Invalid 'is_buy' value; must be True or False", "success": False}

    # 2) quantity needs to be a positive integer
    if not isinstance(message.get("quantity"), int) or message["quantity"] <= 0:
        return False, {"error": "Quantity must be a positive integer", "success": False}

    # 3) Distinguish between Buy (MARKET) and Sell (LIMIT)
    #    a) Buy ==> order_type must be "MARKET"; price must be "null"
    #    b) Sell ==> order_type must be "LIMIT"; price must be an integer > 0
    if message["is_buy"]:
        # BUY must be the MARKET order
        if message["order_type"] != "MARKET":
            return False, {"error": "Invalid Buy Order Type (must be 'MARKET')", "success": False}

    else:
        # SELL must be the limit order
        if message["order_type"] != "LIMIT":
            return False, {"error": "Invalid Sell Order Type (must be 'LIMIT')", "success": False}

        # Price must be a valid number > 0
        if "price" not in message or not isinstance(message["price"], (int, float)) or message["price"] <= 0:
            return False, {"error": "Invalid Sell Limit price (must be > 0)", "success": False}

    # If everything passes:
    return True, {"success": True}


def decrypt_and_validate_token(encrypted_message, secret_key):
    """
    1. Decrypt the JWT token using secret_key.
    2. Validate the token's payload (exp, etc.).
    Returns (bool, dict) => (True/False, token_attributes or error).
    """

    if not encrypted_message:
        return {"error": "Missing or invalid token header"}

    token = encrypted_message

    try:
        # Decodes the JWT token
        decoded_message = jwt.decode(token, secret_key, algorithms=["HS256"])
        return {"user_id": decoded_message.get("user_id")}
    except jwt.ExpiredSignatureError:
        return {"error": "Token has expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}

def build_response(success=True, data=None):
    """
    Returns a consistent JSON structure for responses.
    """
    return {
        "success": success,
        "data": data
    }