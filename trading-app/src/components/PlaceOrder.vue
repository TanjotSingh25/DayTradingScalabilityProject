<template>
    <div>
        <h2>Place Stock Order</h2>
        <form @submit.prevent="placeOrder">
            <select
                v-model="order.stock_name"
                required
                style="width: 250px; padding: 10px; margin-bottom: 10px"
            >
                <option disabled value="">Select a stock</option>
                <!-- Dynamically populate options from stored stocks -->
                <option
                    v-for="(stockId, stockName) in stocks"
                    :key="stockId"
                    :value="stockName"
                >
                    {{ stockName }}
                </option>
            </select>
            <br />
            <select
                v-model="order.is_buy"
                style="width: 250px; padding: 10px; margin-bottom: 10px"
            >
                <option :value="true">Market Buy</option>
                <option :value="false">Limit Sell</option>
            </select>
            <br />
            <input
                v-model.number="order.quantity"
                placeholder="Quantity"
                type="number"
                required
                style="width: 250px; padding: 10px; margin-bottom: 10px"
            />

            <input
                v-if="!order.is_buy"
                v-model.number="order.price"
                placeholder="Price"
                type="number"
                style="width: 250px; padding: 10px; font-size: 16px"
            />
            <br />
            <button type="submit" style="padding: 10px 20px; width: 250px">
                Place Order
            </button>
        </form>
        <p v-if="message">{{ message }}</p>
    </div>
</template>

<script>
import axios from "axios";

export default {
    data() {
        return {
            order: {
                stock_name: "", // Change to stock_name
                stock_id: "", // Stock ID will be mapped dynamically
                is_buy: true,
                quantity: 0,
                price: null,
            },
            message: "",
            stocks: JSON.parse(localStorage.getItem("stocks")) || {}, // Retrieve stored stocks from localStorage
        };
    },
    watch: {
        // Watch for stock_name changes to update stock_id
        "order.stock_name"(newStockName) {
            if (newStockName) {
                // Map stock name to stock_id
                this.order.stock_id = this.stocks[newStockName];
            }
        },
    },
    methods: {
        async placeOrder() {
            const token = localStorage.getItem("token");
            if (!token) {
                this.message = "Invalid token.";
                return;
            }

            const orderPayload = {
                stock_id: this.order.stock_id, // Use stock_id for API request
                is_buy: this.order.is_buy,
                order_type: this.order.is_buy ? "MARKET" : "LIMIT",
                quantity: this.order.quantity,
                price: this.order.is_buy ? null : this.order.price,
            };

            try {
                const response = await axios.post(
                    "http://localhost/engine/placeStockOrder",
                    orderPayload,
                    {
                        headers: {
                            token: token,
                        },
                    }
                );
                this.message = "Order placed successfully!";
                console.log("Response:", response.data);
            } catch (error) {
                this.message = "Failed to place order.";
                console.error("Error:", error);
            }
        },
    },
};
</script>
