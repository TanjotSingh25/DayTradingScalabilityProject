import uuid
import re

# SECRET_KEY = env("SECRET_KEY")

def generate_order_id():
    """
    Creates a unique identifier for a new order.
    """
    return str(uuid.uuid4())

def order_service_sanity_check(message):
    # Sanity check for message to have the prerequisites to place order
    required_fields = ["token", "stock_id", "is_buy", "order_type", "quantity"]
    
    # Check if request is sound
    for field in required_fields:
        if field not in message:
            return False, {"error": f"Missing required field: {field}", "status": "fail"}

    # Check if there are any unexpected fields
    extra_fields = [field for field in message if field not in required_fields]
    if extra_fields:
        return False, {"error": f"Unexpected fields present: {', '.join(extra_fields)}", "status": "fail"}

    # Ensure 'is_buy' is a boolean and the required fields exist
    if message.get("is_buy") not in [True, False]:
        return False, {"error": f"Invalid is_buy type", "status": "fail"}

    # Check for valid quantity and price based on order type
    if message["is_buy"]:  # Buy Market
        if message["order_type"] != "MARKET" and message["quantity"] <= 0 and message["price"] is not None:
            return False, {"error": f"Invalid Market Buy Order", "status": "fail"}
    else:  # Sell Limit
        if message["order_type"] != "LIMIT" and message["quantity"] <= 0 and message["price"] <= 0:
            return False, {"error": f"Invalid Sell Limit Order", "status": "fail"}

    return True, "Passed"

def decrypt_and_validate_token(encrypted_message, secret_key):
    # Decrypts the message first using the secret key, and then validates the token. 
    return validate_token(decrypt_message(encrypted_message, secret_key))

def decrypt_message(encrypted_message, secret_key):
    """
    Placeholder function to decrypt the message using the secret key.
    Replace this logic with your actual decryption implementation.
    """
    # For demonstration, assume the message is not encrypted
    return encrypted_message

def validate_token(token):
    """
    Verifies the provided JWT token (placeholder).
    Checks if the token is well-formed and not expired.
    """
    # TODO: Integrate with actual JWT validation logic
    return True

def build_response(success=True, data=None):
    """
    Returns a consistent JSON structure for responses.
    """
    return {
        "success": success,
        "data": data
    }