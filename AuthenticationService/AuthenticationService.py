from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token
import os
from dotenv import load_dotenv
from flask_cors import CORS
from datetime import timedelta

load_dotenv()

app = Flask(__name__)
CORS(app)

# Load JWT Secret and Expiry
app.config['JWT_SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=30)

# Database URI from .env
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Configure connection pooling separately
engine = create_engine(
    app.config['SQLALCHEMY_DATABASE_URI'],
    pool_size=20,      # Increase default pool size from 5 to 20
    max_overflow=40,   # Allow up to 40 extra connections
    pool_timeout=30,   # Wait 30 sec before raising timeout
    pool_recycle=1800  # Recycle connections after 30 minutes
)

# Set up scoped session
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(150), nullable=False)

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    user_name = data.get('user_name')
    password = data.get('password')
    name = data.get('name')

    if Users.query.filter_by(user_name=user_name).first():
        return jsonify({"success": False, "data": {"error": "Username already exists"}}), 400
    
    try:
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = Users(user_name=user_name, password=hashed_password, name=name)
        db.session.add(user)
        db.session.commit()
        return jsonify({"success": True, "data": None}), 201
    except Exception as e:
        return jsonify({"success": False, "data": {"error": str(e)}}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user_name = data.get('user_name')
    password = data.get('password')
    
    user = Users.query.filter_by(user_name=user_name).first()
    if user and bcrypt.check_password_hash(user.password, password):
        access_token = create_access_token(identity=str(user.id), additional_claims={
            "token_type": "access",
            "user_id": user.id,
            "user_name": user.user_name
        })
        return jsonify({"success": True, "data": {"token": access_token}})
    
    return jsonify({"success": False, "data": {"error": "Invalid credentials"}}), 400

@app.route('/delete/<string:user_name>', methods=['DELETE'])
def delete(user_name):
    try:
        user = Users.query.filter_by(user_name=user_name).first()
        if not user:
            return jsonify({"success": False, "data": {"error": "User not found"}}), 404
        
        db.session.delete(user)
        db.session.commit()
        return jsonify({"success": True, "data": None}), 200
    except Exception as e:
        return jsonify({"success": False, "data": {"error": str(e)}}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=8000)
