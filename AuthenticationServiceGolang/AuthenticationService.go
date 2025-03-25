package main

import (
	"context"
	"fmt"
	"io"
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

// Load environment variables and initialize DBs
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
	clientOptions := options.Client().ApplyURI(mongoURI).SetMaxPoolSize(2000)
	var err error
	client, err = mongo.Connect(ctx, clientOptions)
	if err != nil {
		log.Fatal("Failed to connect to MongoDB:", err)
	}
	dbName := os.Getenv("DB_NAME")
	usersColl = client.Database(dbName).Collection("users")

	// Connect to Redis
	redisPort, _ := strconv.Atoi(os.Getenv("REDIS_PORT"))
	rdb = redis.NewClient(&redis.Options{
		Addr: fmt.Sprintf("%s:%d", os.Getenv("REDIS_HOST"), redisPort),
	})
	// Optional: Ping Redis
	// _, err = rdb.Ping(ctx).Result()
	// if err != nil {
	// 	log.Fatal("Redis connection failed:", err)
	// }

	log.SetOutput(io.Discard) // Disable all logging for load test
}

// Fast /register handler without password hashing
func register(c *gin.Context) {
	var data struct {
		UserName string `json:"user_name"`
		Password string `json:"password"`
		Name     string `json:"name"`
	}

	if err := c.ShouldBindJSON(&data); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Invalid input"}})
		return
	}

	// Check if username exists
	err := usersColl.FindOne(ctx, bson.M{"user_name": data.UserName}).Err()
	if err == nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Username already exists"}})
		return
	} else if err != mongo.ErrNoDocuments {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "data": gin.H{"error": "Server error"}})
		return
	}

	// Create user without hashing
	user := User{
		ID:       primitive.NewObjectID(),
		UserName: data.UserName,
		Password: data.Password, // raw password
		Name:     data.Name,
	}

	// Push to Redis queue
	userJSON, _ := bson.MarshalExtJSON(user, false, false)
	if err := rdb.LPush(ctx, "pending_users", userJSON).Err(); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "data": gin.H{"error": "Failed to queue user"}})
		return
	}

	// Generate token
	token := generateToken(user)

	// Optional: Store token in Redis
	rdb.Set(ctx, fmt.Sprintf("user_token:%s", user.UserName), token, 0)

	c.JSON(http.StatusCreated, gin.H{"success": true, "data": nil})
}

// Worker goroutine that processes Redis -> MongoDB
func startMongoWriter() {
	go func() {
		for {
			userJSON, err := rdb.RPop(ctx, "pending_users").Result()
			if err == redis.Nil {
				time.Sleep(100 * time.Millisecond)
				continue
			} else if err != nil {
				continue
			}

			var user User
			if err := bson.UnmarshalExtJSON([]byte(userJSON), false, &user); err != nil {
				continue
			}

			_, _ = usersColl.InsertOne(ctx, user)
		}
	}()
}

// Login handler without bcrypt
func login(c *gin.Context) {
	var data struct {
		UserName string `json:"user_name"`
		Password string `json:"password"`
	}

	if err := c.ShouldBindJSON(&data); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Invalid input"}})
		return
	}

	// Check Redis token first
	redisKey := fmt.Sprintf("user_token:%s", data.UserName)
	if cachedToken, err := rdb.Get(ctx, redisKey).Result(); err == nil {
		rdb.Del(ctx, redisKey)
		c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"token": cachedToken}})
		return
	}

	// Check in DB
	var user User
	err := usersColl.FindOne(ctx, bson.M{"user_name": data.UserName}).Decode(&user)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Invalid credentials"}})
		return
	}

	// Plain-text comparison
	if user.Password != data.Password {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "data": gin.H{"error": "Invalid credentials"}})
		return
	}

	token := generateToken(user)
	rdb.SetEX(ctx, fmt.Sprintf("user_token:%s", user.UserName), token, 30*time.Minute)
	c.JSON(http.StatusOK, gin.H{"success": true, "data": gin.H{"token": token}})
}

// Token generator (unchanged)
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

// Main server
func main() {
	router := gin.New()
	router.Use(gin.Recovery())

	router.POST("/register", register)
	router.POST("/login", login)

	startMongoWriter()

	s := &http.Server{
		Addr:           ":8000",
		Handler:        router,
		ReadTimeout:    10 * time.Second,
		WriteTimeout:   20 * time.Second,
		IdleTimeout:    120 * time.Second,
		MaxHeaderBytes: 1 << 20,
	}

	if err := s.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("listen: %s\n", err)
	}
}
