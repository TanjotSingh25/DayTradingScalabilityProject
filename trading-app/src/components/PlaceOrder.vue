<template>
    <div>
      <h2>Place Stock Order</h2>
      <form @submit.prevent="placeOrder">
        <input v-model="order.stock_id" placeholder="Stock ID" required />
        <select v-model="order.is_buy">
          <option :value="true">Market Buy</option>
          <option :value="false">Limit Sell</option>
        </select>
        <input v-model.number="order.quantity" placeholder="Quantity" type="number" required />
        <input v-if="!order.is_buy" v-model.number="order.price" placeholder="Price" type="number" />
        <button type="submit">Place Order</button>
      </form>
      <p v-if="message">{{ message }}</p>
    </div>
  </template>
  
  <script>
  import axios from 'axios';
  
  export default {
    data() {
      return {
        order: {
          stock_id: "",
          is_buy: true,
          quantity: 0,
          price: null
        },
        message: "",
      };
    },
    methods: {
      async placeOrder() {
        const token = localStorage.getItem("token");
        if (!token) {
          this.message = "Invalid token.";
          return;
        }

        const orderPayload = {
          stock_id: this.order.stock_id,
          is_buy: this.order.is_buy ? "MARKET" : "LIMIT",
          quantity: this.order.quantity,
          price: this.order.is_buy? null : this.order.price
        };

        try {
          const response = await axios.post('/api/placeStockOrder', orderPayload);
          this.message = "Order placed successfully!";
          console.log('Response:',response.data);
        } catch (error) {
          this.message = "Failed to place order.";
          console.error('Error:',error);
        }
      },
    },
  };
  </script>