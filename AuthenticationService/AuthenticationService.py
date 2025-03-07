from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, Index, exists
from sqlalchemy.orm import scoped_session, sessionmaker
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token
from flask_migrate import Migrate
import os
from dotenv import load_dotenv
from flask_cors import CORS
from datetime import timedelta
import redis
import json

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
migrate = Migrate(app,db)

# Configure connection pooling separately
engine = create_engine(
    app.config['SQLALCHEMY_DATABASE_URI'],
    pool_size=1000,      
    max_overflow=1000,   
    pool_timeout=60,   
    pool_recycle=900  
)

# Set up scoped session
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# Connect to Redis
REDIS_HOST = os.getenv("REDIS_HOST", "redis")  # Use "redis" inside Docker
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(150), nullable=False)

    __table_args__ = (
        Index("idx_users_user_name", "user_name", postgresql_using="hash"),
    )

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    user_name = data.get('user_name')
    password = data.get('password')
    name = data.get('name')

    if db.session.query(exists().where(Users.user_name == user_name)).scalar():
        return jsonify({"success": False, "data": {"error": "Username already exists"}}), 400
    
    try:
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = Users(user_name=user_name, password=hashed_password, name=name)
        db.session.add(user)
        db.session.commit()

        # Generate and store token in Redis (Write-Through Caching)
        access_token = create_access_token(identity=str(user.id), additional_claims={
            "token_type": "access",
            "user_id": user.id,
            "user_name": user.user_name
        })
        redis_client.setex(f"user_token:{user.user_name}", timedelta(minutes=30), access_token)

        return jsonify({"success": True, "data": None}), 201
    except Exception as e:
        return jsonify({"success": False, "data": {"error": str(e)}}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user_name = data.get('user_name')
    password = data.get('password')
    
    cached_token = redis_client.get(f"user_token:{user_name}")
    if cached_token:
        # redis_client.delete(f"user_token:{user.id}")  # Delete token from cache after reading
        return jsonify({"success": True, "data": {"token": cached_token}})
    
    user = Users.query.with_entities(Users.id, Users.password, Users.user_name).filter_by(user_name=user_name).first()
    
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify({"success": False, "data": {"error": "Invalid credentials"}}), 400

    # If not in cache, generate a new token
    access_token = create_access_token(identity=str(user.id), additional_claims={
        "token_type": "access",
        "user_id": user.id,
        "user_name": user.user_name
    })
    
    # Store in Redis
    redis_client.setex(f"user_token:{user.id}", timedelta(minutes=30), access_token)

    return jsonify({"success": True, "data": {"token": access_token}})

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
