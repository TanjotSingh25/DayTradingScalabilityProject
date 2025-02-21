<template>
    <div>
        <h2>Create Stock</h2>
        <form @submit.prevent="createStock">
            <input v-model="stockName" placeholder="Stock Name" required />
            <button type="submit">Create Stock</button>
        </form>
        <p v-if="message">{{ message }}</p>
    </div>
</template>

<script>
import axios from "axios";
export default {
    data() {
        return {
            stockName: "",
            message: "",
        };
    },
    methods: {
        async createStock() {
            const token = localStorage.getItem("token");
            if (!token) {
                this.message = "Invalid token.";
                return;
            }
            try {
                const response = await axios.post(
                    "http://localhost/setup/createStock",
                    {
                        stock_name: this.stockName,
                    },
                    {
                        headers: {
                            token: token,
                        },
                    }
                );
                const stockId = response.data.data.stock_id;
                this.message =
                    "Stock created successfully. Stock ID: " + stockId;

                // Get existing stocks from localStorage, or initialize it as an empty object
                const stocks = JSON.parse(localStorage.getItem("stocks")) || {};

                // Map the stock name to its ID
                stocks[this.stockName] = stockId;

                // Store the updated mapping back to localStorage
                localStorage.setItem("stocks", JSON.stringify(stocks));

                console.log("Response:", response.data);
            } catch (error) {
                this.message = "Failed to create stock.";
                console.error("Error:", error);
            }
        },
    },
};
</script>
