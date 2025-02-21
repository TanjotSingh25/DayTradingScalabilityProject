<template>
    <div>
        <h2>Stock Portfolio</h2>
        <button @click="fetchPortfolio">Fetch Portfolio</button>
        <ul v-if="portfolio.length > 0">
            <li v-for="stock in portfolio" :key="stock.stock_id">
                {{ stock.stock_name }} - {{ stock.quantity_owned }} shares
            </li>
        </ul>
        <p v-else>[]</p>
        <p v-if="error">{{ error }}</p>
    </div>
</template>

<script>
import axios from "axios";
export default {
    data() {
        return {
            portfolio: [],
            error: "",
        };
    },
    methods: {
        async fetchPortfolio() {
            const token = localStorage.getItem("token");
            if (!token) {
                this.message = "Invalid token.";
                return;
            }
            try {
                const response = await axios.get(
                    "http://localhost/setup/getStockPortfolio",
                    {
                        headers: {
                            token: token,
                        },
                    }
                );
                this.portfolio = response.data.data;
            } catch (error) {
                this.error = "Failed to fetch portfolio";
                console.error("Error:", error);
            }
        },
    },
};
</script>
