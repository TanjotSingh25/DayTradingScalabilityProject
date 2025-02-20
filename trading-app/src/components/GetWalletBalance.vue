<template>
    <div>
      <h2>Wallet Balance</h2>
      <button @click="fetchBalance">Fetch Balance</button>
      <p>Balance: {{ balance }}</p>
      <p v-if="error">{{ error }}</p>
    </div>
  </template>
  
  <script>
  import axios from 'axios';
  
  export default {
    data() {
      return {
        balance: 0,
        error: "",
      };
    },
    methods: {
      async fetchBalance() {
        const token = localStorage.getItem("token");
        try {
          const response = await axios.get('http://localhost/setup/getWalletBalance', {
            headers: {
              token: token
            },
          });
          this.balance = response.data.data.balance;
        } catch (error) {
          this.error = "Failed to fetch wallet balance.";
          console.error('Error:', error);
        }
      },
    },
  };
  </script>