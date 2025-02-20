<template>
    <div>
      <h2>Cancel Stock Transaction</h2>
      <form @submit.prevent="cancelTransaction">
        <input v-model="transaction.stock_tx_id" placeholder="Transaction ID" required />
        <button type="submit">Cancel Transaction</button>
      </form>
      <p v-if="message">{{ message }}</p>
    </div>
  </template>
  
  <script>
  import axios from 'axios';
  
  export default {
    data() {
      return {
        transaction: {
          stock_tx_id: "",
        },
        message: "",
      };
    },
    methods: {
      async cancelTransaction() {
        const token = localStorage.getItem("token");
        if (!token) {
          this.message = "Invalid token";
          return;
      }
        try {
          const response = await axios.post('/api/cancelStockTransaction', this.transaction);
          this.message = "Transaction canceled successfully!";
          console.log('Response:',response.data);
        } catch (error) {
          this.message = "Failed to cancel transaction.";
          console.error('Error:',error);
        }
      },
    },
  };
  </script>