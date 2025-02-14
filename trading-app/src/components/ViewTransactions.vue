<template>
    <div>
      <h2>Stock Transactions</h2>
      <ul>
        <li v-for="tx in transactions" :key="tx.stock_tx_id">
          {{ tx.stock_id }} - {{ tx.quantity }} shares at ${{ tx.price }} ({{ tx.order_status }})
        </li>
      </ul>
    </div>
  </template>
  
  <script>
  import axios from 'axios';
  
  export default {
    data() {
      return {
        transactions: [],
      };
    },
    methods: {
      async fetchTransactions() {
        try {
          const response = await axios.get('/api/getStockTransactions', {
            params: { token: "jwt_token" }, 
          });
          this.transactions = response.data.data;
        } catch (error) {
          console.error("Failed to fetch transactions:", error);
        }
      },
    },
  };
  </script>