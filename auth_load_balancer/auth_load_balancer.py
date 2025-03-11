from flask import Flask, request, jsonify
import hashlib
import requests
import os

app = Flask(__name__)

# Define the authentication services
AUTH_SERVICES = {
    0: "http://auth_service1:8000",
    1: "http://auth_service2:8000",
    2: "http://auth_service3:8000",
    3: "http://auth_service4:8000",
    4: "http://auth_service5:8000",
    5: "http://auth_service6:8000",
    6: "http://auth_service7:8000",
    7: "http://auth_service8:8000",
    8: "http://auth_service9:8000",
    9: "http://auth_service10:8000",
}

def get_auth_service(username):
    """Hash username and determine which auth service to use."""
    hash_value = int(hashlib.md5(username.encode()).hexdigest(), 16)
    return AUTH_SERVICES[hash_value % len(AUTH_SERVICES)]  

@app.route('/<path:path>', methods=['POST', 'GET', 'PUT', 'DELETE'])
def route_request(path):
    try:
        # Read JSON data from request
        data = request.get_json(silent=True) or {}

        # Extract username from request body
        user_name = data.get("user_name")
        if not user_name:
            return jsonify({"success": False, "data": {"error": "Username is required"}}), 400

        # Determine the correct authentication service
        auth_service_url = f"{get_auth_service(user_name)}/{path}"

        # Forward request to the selected auth service
        response = requests.request(
            method=request.method,
            url=auth_service_url,
            json=data,
            headers={key: value for key, value in request.headers if key != 'Host'}
        )

        return (response.content, response.status_code, response.headers.items())
    
    except Exception as e:
        return jsonify({"success": False, "data": {"error": str(e)}}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
