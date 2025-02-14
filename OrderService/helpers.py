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

    # Check quantity is an integer
    if not isinstance(message.get("quantity"), int):
        return False, {"error": "Quantity must be an integer."}

    # Check for valid quantity and price based on order type
    if message["is_buy"]:  # Buy Market
        if message["order_type"] != "MARKET":
            return False, {"error": f"Invalid Order Buy Order Type - Must be MARKET", "status": "fail"}
        # Check if it a positive integer
        elif message["quantity"] <= 0:
            return False, {"error": f"Invalid Market Buy Order Quantity", "status": "fail"}
        # Check If Buy market order is placed, if so the price must be null
        elif message["price"] != "null":
            return False, {"error": f"Invalid Market Buy Order Price - Must be null", "status": "fail"}
    else:  # Sell Limit
        if message["order_type"] != "LIMIT" and message["quantity"] <= 0 and message["price"] <= 0:
            return False, {"error": f"Invalid Sell Limit Order", "status": "fail"}

    return True, "Passed"

def decrypt_and_validate_token(encrypted_message, secret_key):
    # Decrypts the message first using the secret key, and then validates the token. 
    # 1 -- Decrpyt using Secret Key
    decrypted_token = decrypt_message(decrypt_message, secret_key)

    # 2 -- Validate token
    ret_val, token_attributes = validate_token(decrypted_token)
    # 3 - Return if token is valid or not, and user_id and user_name in the encoded in the token
    return ret_val, decrypt_and_validate_token

def decrypt_message(encrypted_message, secret_key):
    """
    Placeholder function to decrypt the message using the secret key.
    Replace this logic with your actual decryption implementation.
    """
    # For demonstration, assume the message is not encrypted # return data: {token:"decrypted_token", user_id, etc}
    token = auth_header_value.split(' ')[1]
    # Decode using token, and return message
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
    return encrypted_message

def validate_token(token):
    """
    Verifies the provided JWT token (placeholder).
    Checks if the token is well-formed and not expired.
    Return payload inside token as well
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