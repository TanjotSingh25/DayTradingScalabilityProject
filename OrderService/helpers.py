import uuid
import re
import jwt
import time

# SECRET_KEY = env("SECRET_KEY")

def generate_order_id():
    """
    Creates a unique identifier for a new order.
    """
    return str(uuid.uuid4())

def order_service_sanity_check(message):
    """
    Validates the request payload for placing a stock order.
    Ensures required fields are present, correct data types, and
    appropriate logic for buy (MARKET) vs. sell (LIMIT).
    """

    required_fields = ["token", "stock_id", "is_buy", "order_type", "quantity"]
    # Check if required fields exist
    for field in required_fields:
        if field not in message:
            return False, {"error": f"Missing required field: {field}", "status": "fail"}

    # Check if there are any unexpected fields
    extra_fields = [field for field in message if field not in required_fields and field not in ["price"]]
    if extra_fields:
        return False, {"error": f"Unexpected fields present: {', '.join(extra_fields)}", "status": "fail"}

    # 1) 'is_buy' must be a boolean
    if message.get("is_buy") not in [True, False]:
        return False, {"error": "Invalid 'is_buy' value; must be True or False", "status": "fail"}

    # 2) 'quantity' must be a positive integer
    if not isinstance(message.get("quantity"), int) or message["quantity"] <= 0:
        return False, {"error": "Quantity must be a positive integer", "status": "fail"}

    # 3) Distinguish between Buy (MARKET) and Sell (LIMIT)
    #    a) Buy => order_type must be "MARKET"; price must be "null"
    #    b) Sell => order_type must be "LIMIT"; price must be an integer/float > 0
    if message["is_buy"]:
        # BUY must be MARKET
        if message["order_type"] != "MARKET":
            return False, {"error": "Invalid Buy Order Type (must be 'MARKET')", "status": "fail"}

        # Price must be "null" if it's a market buy
        # (Using a string check here because user wants "null" in the request)
        if message.get("price") != "null":
            return False, {"error": "Market Buy price must be 'null'", "status": "fail"}

    else:
        # SELL must be LIMIT
        if message["order_type"] != "LIMIT":
            return False, {"error": "Invalid Sell Order Type (must be 'LIMIT')", "status": "fail"}

        # Price must be a valid number > 0
        # Using isinstance check in case 'price' is included
        if "price" not in message or not isinstance(message["price"], (int, float)) or message["price"] <= 0:
            return False, {"error": "Invalid Sell Limit price (must be > 0)", "status": "fail"}

    # If everything passes:
    return True, {"status": "pass"}


def decrypt_and_validate_token(encrypted_message, secret_key):
    """
    1. Decrypt the JWT token using secret_key.
    2. Validate the token's payload (exp, etc.).
    Returns (bool, dict) => (True/False, token_attributes or error).
    """

    # 1) Decrypt
    decrypted_token = decrypt_message(encrypted_message, secret_key)
    if not decrypted_token:
        return False, {"error": "Decryption failed or token is invalid"}

    # 2) Validate
    ret_val, token_payload = validate_token(decrypted_token)
    if not ret_val:
        return False, {"error": "Token validation failed"}
    return True, token_payload

def decrypt_message(encrypted_message, secret_key):
    """
    Decrypt token message to verify
    """
    try:
        # 'encrypted_message' is actually a JWT in this placeholder
        payload = jwt.decode(encrypted_message, secret_key, algorithms=['HS256'])
        return payload  # Return the decoded payload
    except jwt.ExpiredSignatureError:
        print("Token expired.")
    except jwt.InvalidTokenError as err:
        print(f"Invalid token: {err}")
    return None

def validate_token(token_payload):
    """
    Checks the token payload is well-formed, not expired, etc.
    Return (bool, dict) => (True if valid, plus the token payload).
    If invalid, return (False, None).
    """
    # Example: token_payload might have {"user_id": "...", "user_name": "...", "exp": 1699999999}
    # Check if 'exp' is present and not expired
    exp = token_payload.get("exp")
    if exp and time.time() > exp:
        return False, None  # expired

    # Additional checks as needed (e.g., iss, aud)
    return True, token_payload


def build_response(success=True, data=None):
    """
    Returns a consistent JSON structure for responses.
    """
    return {
        "success": success,
        "data": data
    }