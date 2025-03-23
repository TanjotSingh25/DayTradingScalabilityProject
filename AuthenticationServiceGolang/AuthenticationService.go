package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/go-redis/redis/v8"
	"github.com/golang-jwt/jwt/v5"
	"github.com/joho/godotenv"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"golang.org/x/crypto/bcrypt"
)

var (
	client    *mongo.Client
	usersColl *mongo.Collection
	rdb       *redis.Client
	secretKey string
	ctx       = context.Background()
)

// User model
type User struct {
	ID       primitive.ObjectID `bson:"_id,omitempty"`
	UserName string             `bson:"user_name"`
	Password string             `bson:"password"`
	Name     string             `bson:"name"`
}

// JWT Claims
type Claims struct {
	TokenType string `json:"token_type"`
	UserID    string `json:"user_id"`
	UserName  string `json:"user_name"`
	jwt.RegisteredClaims
}

// Load environment variables
func init() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using system environment variables")
	}

	secretKey = os.Getenv("SECRET_KEY")
	if secretKey == "" {
		log.Fatal("SECRET_KEY must be set")
	}

	// Connect to MongoDB
	mongoURI := os.Getenv("MONGO_URI")
	clientOptions := options.Client().ApplyURI(mongoURI)
	var err error
	client, err = mongo.Connect(ctx, clientOptions)
	if err != nil {
		log.Fatal("Failed to connect to MongoDB:", err)
	}

	// Select database and collection
	dbName := os.Getenv("DB_NAME")
	usersColl = client.Database(dbName).Collection("users")

	// Connect to Redis
	redisPort, _ := strconv.Atoi(os.Getenv("REDIS_PORT"))
	rdb = redis.NewClient(&redis.Options{
		Addr: fmt.Sprintf("%s:%d", os.Getenv("REDIS_HOST"), redisPort),
	})

	pong, err := rdb.Ping(ctx).Result()
	if err != nil {
		log.Fatal("Redis connection failed:", err)
	}
	fmt.Println("Redis connected:", pong)

}

func register(c *gin.Context) {
	startTime := time.Now()

	var data struct {
		UserName string `json:"user_name"`
		Password string `json:"password"`
		Name     string `json:"name"`
	}

	if err := c.ShouldBindJSON(&data); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Invalid input"}})
		return
	}

	// Check if user exists
	existsStart := time.Now()
	var existingUser User
	err := usersColl.FindOne(ctx, bson.M{"user_name": data.UserName}).Decode(&existingUser)
	fmt.Println("MongoDB FindOne Time:", time.Since(existsStart))

	if err == nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Username already exists"}})
		return
	}

	// Hash password
	bcryptStart := time.Now()
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(data.Password), 10)
	fmt.Println("Bcrypt Hashing Time:", time.Since(bcryptStart))

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "data": gin.H{"error": "Server error"}})
		return
	}

	// Insert user into MongoDB
	dbStart := time.Now()
	user := User{ID: primitive.NewObjectID(), UserName: data.UserName, Password: string(hashedPassword), Name: data.Name}
	_, err = usersColl.InsertOne(ctx, user)
	fmt.Println("MongoDB Insert Time:", time.Since(dbStart))

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "data": gin.H{"error": "Could not create user"}})
		return
	}

	// Generate JWT token
	jwtStart := time.Now()
	token := generateToken(user)
	fmt.Println("JWT Token Generation Time:", time.Since(jwtStart))

	// Store token in Redis
	redisStart := time.Now()
	rdb.Set(ctx, fmt.Sprintf("user_token:%s", user.UserName), token, 0) // No expiry
	fmt.Println("Redis Set Time (without expiry):", time.Since(redisStart))


	fmt.Println("Total Register API Time:", time.Since(startTime))

	c.JSON(http.StatusCreated, gin.H{"success": true, "data": nil})

}

func login(c *gin.Context) {
	var data struct {
		UserName string `json:"user_name"`
		Password string `json:"password"`
	}

	if err := c.ShouldBindJSON(&data); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Invalid input"}})
		return
	}

	// Check Redis cache first
	if cachedToken, err := rdb.Get(ctx, fmt.Sprintf("user_token:%s", data.UserName)).Result(); err == nil {
		c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"token": cachedToken}})
		return
	}

	// Check MongoDB for user
	var user User
	err := usersColl.FindOne(ctx, bson.M{"user_name": data.UserName}).Decode(&user)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Invalid credentials"}})
		return
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(data.Password)); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Invalid credentials"}})
		return
	}

	token := generateToken(user)
	rdb.SetEX(ctx, fmt.Sprintf("user_token:%s", user.UserName), token, 30*time.Minute)

	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"token": token}})
}

func generateToken(user User) string {
	claims := Claims{
		TokenType: "access",
		UserID:    user.ID.Hex(),
		UserName:  user.UserName,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(30 * time.Minute)),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, _ := token.SignedString([]byte(secretKey))
	return tokenString
}

func main() {
	router := gin.Default()
	router.POST("/register", register)
	router.POST("/login", login)

	router.Run(":8000")
}
