<template>
    <div>
      <h2>Stock Portfolio</h2>
      <button @click="fetchPortfolio">Fetch Portfolio</button>
      <ul>
        <li v-for="stock in portfolio" :key="stock.stock_id">
          {{ stock.stock_name }} - {{ stock.quantity_owned }} shares
        </li>
      </ul>
      <p v-if="error">{{ error }}</p>
    </div>
  </template>

<script>
import axios from 'axios';
export default {
    data() {
        return {
            portfolio: [],
            error: ""
        };
    },
    methods: {
        async fetchPortfolio() {
            const token = localStorage.getItem("token");
            try {
                const response = await axios.get('getStockPortfolio', {
                    headers: {
                        token: token
                    }
                });
                this.portfolio = response.data.data;
            } catch (error) {
                this.error = "Failed to fetch portfolio";
                console.error('Error:', error);
            }
        }
    }
};
</script>