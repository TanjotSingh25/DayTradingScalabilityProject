<template>
    <div>
      <h2>Deposit</h2>
      <form @submit.prevent="addMoney">
        <input v-model.number="amount" placeholder="Amount" type="number" required />
        <button type="submit">Add Money</button>
      </form>
      <p v-if="message">{{ message }}</p>
    </div>
  </template>
  
  <script>
  import axios from 'axios';
  
  export default {
    data() {
      return {
        amount: 0,
        message: "",
      };
    },
    methods: {
      async addMoney() {
        const token = localStorage.getItem("token");
        if (!token) {
                this.message = "Invalid token.";
                return;
            }
        try {
          const response = await axios.post('http://localhost/setup/addMoneyToWallet', {
            amount: this.amount,
          }, {
            headers: {
              token: token
            },
          });
          this.message = "Money added to wallet successfully!";
          console.log('Response:', response.data);
        } catch (error) {
          this.message = "Failed to add money to wallet.";
          console.error('Error:', error);
        }
      },
    },
  };
  </script>