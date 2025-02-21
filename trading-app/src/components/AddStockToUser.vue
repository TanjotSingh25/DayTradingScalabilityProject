<template>
    <div>
        <h2>Add Stock to Portfolio</h2>
        <form @submit.prevent="addStock">
            <select
                v-model="selectedStock"
                required
                style="width: 100%; padding: 10px; font-size: 16px"
            >
                <option disabled value="">Select a stock</option>
                <option
                    v-for="(stockId, stockName) in stocks"
                    :key="stockId"
                    :value="stockName"
                >
                    {{ stockName }}
                </option>
            </select>
            <input
                v-model.number="quantity"
                placeholder="Quantity"
                type="number"
                required
            />
            <button type="submit">Add Stock</button>
        </form>
        <p v-if="message">{{ message }}</p>
    </div>
</template>

<script>
import axios from "axios";

export default {
    data() {
        return {
            selectedStock: "", // The stock the user selects
            quantity: 1,
            message: "",
            stocks: {}, // Holds the stock name to stock ID mapping
        };
    },
    created() {
        // Retrieve the stored stocks from localStorage when the component is created
        const storedStocks = JSON.parse(localStorage.getItem("stocks"));
        if (storedStocks) {
            this.stocks = storedStocks;
        }
    },
    methods: {
        async addStock() {
            if (!this.selectedStock) {
                this.message = "Please select a stock.";
                return;
            }

            // Get the stockId corresponding to the selected stockName
            const stockId = this.stocks[this.selectedStock];
            const token = localStorage.getItem("token");
            if (!token) {
                this.message = "Invalid token.";
                return;
            }

            try {
                const response = await axios.post(
                    "http://localhost/setup/addStockToUser",
                    {
                        stock_id: stockId,
                        quantity: this.quantity,
                    },
                    {
                        headers: {
                            token: token,
                        },
                    }
                );
                this.message = "Stock added successfully.";
                console.log("Response:", response.data);
            } catch (error) {
                this.message = "Failed to add stock to portfolio.";
                console.error("Error:", error);
            }
        },
    },
};
</script>
