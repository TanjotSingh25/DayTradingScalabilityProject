<template>
    <div>
        <h2>Stock Transactions</h2>
        <ul>
            <li v-for="tx in transactions" :key="tx.stock_tx_id">
                <p>Transaction ID: {{ tx.stock_tx_id }}</p>
                <p>Stock ID: {{ tx.stock_id }}</p>
                <p>Quantity: {{ tx.quantity }}</p>
                <p>Price: {{ tx.price }}</p>
                <p>Status: {{ tx.order_status }}</p>
                <p>Timestamp: {{ tx.timestamp }}</p>
                <button @click="CancelTransaction(tx.stock_tx_id)">
                    Cancel
                </button>
            </li>
        </ul>
        <p v-if="loading">Loading</p>
        <p v-if="error">{{ error }}</p>
    </div>
</template>

<script>
import axios from "axios";
// import CancelTransaction from './CancelTransaction.vue';

export default {
    data() {
        return {
            transactions: [],
            loading: true,
            error: "",
        };
    },
    async mounted() {
        await this.fetchTransactions();
    },
    methods: {
        async fetchTransactions() {
            const token = localStorage.getItem("token");
            if (!token) {
                this.message = "Invalid token."
                return;
            }
            try {
                const response = await axios.get("/api/getStockTransactions", {
                    params: { token: token }
                });
                this.transactions = response.data.data;
            } catch (error) {
                console.error("Failed to fetch transactions:", error);
            } finally {
                this.loading = false;
            }
        }
    }
};
</script>
