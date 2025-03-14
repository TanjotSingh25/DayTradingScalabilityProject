package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/gorilla/mux"
)

// JWT Secret Key (Replace with a secure method)
var JWT_SECRET = "django-insecure-uj@e4q80n@l2ml)rl*-^s84djzyn5ws6vt7@&h!tp*xf)p05t#"

// Matching Engine URL
var MATCHING_ENGINE_STOCK_PRICES_URL = "http://matching_engine_service:5300/getPrices"

// StockPriceResponse struct for response handling
type StockPriceResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data"`
	Error   string      `json:"error,omitempty"`
}

// Middleware to validate and decode JWT (Mock Implementation)
func validateToken(r *http.Request) (string, error) {
	token := r.Header.Get("token")
	if token == "" {
		return "", fmt.Errorf("missing token header")
	}
	// In a real scenario, implement proper JWT validation here
	// Example: userID, err := DecodeJWT(token, JWT_SECRET)
	userID := "mockUserID" // Mocking decoded user ID
	return userID, nil
}

// getStockPrices handles the stock price retrieval request
func getStockPrices(w http.ResponseWriter, r *http.Request) {
	// Validate token
	userID, err := validateToken(r)
	if err != nil {
		http.Error(w, `{"success": false, "error": "`+err.Error()+`"}`, http.StatusUnauthorized)
		return
	}

	// Send request to Matching Engine Service
	resp, err := http.Get(MATCHING_ENGINE_STOCK_PRICES_URL + "?user_id=" + userID)
	if err != nil {
		http.Error(w, `{"success": false, "error": "Failed to fetch stock prices"}`, http.StatusInternalServerError)
		return
	}
	defer resp.Body.Close()

	// Decode response from Matching Engine
	var stockPriceResponse StockPriceResponse
	if err := json.NewDecoder(resp.Body).Decode(&stockPriceResponse); err != nil {
		http.Error(w, `{"success": false, "error": "Invalid response format"}`, http.StatusInternalServerError)
		return
	}

	// Send response to client
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	json.NewEncoder(w).Encode(stockPriceResponse)
}

// Sample handler function for placing orders
// func placeOrderHandler(w http.ResponseWriter, r *http.Request) {
// 	w.WriteHeader(http.StatusOK)
// 	fmt.Fprintln(w, `{"success": true, "message": "Order placed successfully"}`)
// }

func main() {
	// Set up router
	r := mux.NewRouter()

	// Defining routes
	r.HandleFunc("/getStockPrices", getStockPrices).Methods("GET")
	// First get stockprices working
	//router.HandleFunc("/placeOrder", placeOrderHandler).Methods("POST")

	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "5300" // Default port
	}
	log.Println("Starting server on port", port)
	log.Fatal(http.ListenAndServe(":"+port, r))
}
