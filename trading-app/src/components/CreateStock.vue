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
import axios from 'axios';
export default {
    data() {
        return {
            stockName: "",
            message: ""
        };
    },
    methods: {
        async createStock() {
            const token = localStorage.getItem("token");
            try {
                const response = await axios.post('/createStock', {
                    stock_name: this.stockName,
                }, {
                    headers: {
                        token: token
                    }
                });
                this.message = "Stock created successfully.";
                console.log('Response:', response.data);
            } catch (error) {
                this.message = "Failed to created stock.";
                console.error('Error:',error);
            }
        }
    }
};
</script>