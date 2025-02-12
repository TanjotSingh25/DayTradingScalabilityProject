<template>
    <div>
      <h2>Place Stock Order</h2>
      <form @submit.prevent="placeOrder">
        <input v-model="order.stock_id" placeholder="Stock ID" required />
        <select v-model="order.is_buy">
          <option :value="true">Buy</option>
          <option :value="false">Sell</option>
        </select>
        <select v-model="order.order_type">
            <option value="MARKET">Market</option>
            <option value="LIMIT">Limit</option>
        </select>
        <input v-model.number="order.quantity" placeholder="Quantity" type="number" required />
        <input v-if="order.order_type === 'LIMIT'" v-model.number="order.price" placeholder="Price" type="number" />
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
          token: "jwt_token",
          stock_id: "",
          is_buy: true,
          order_type: "MARKET",
          quantity: 0,
          price: null
        },
        message: "",
      };
    },
    methods: {
      async placeOrder() {
        try {
          const response = await axios.post('/api/placeStockOrder', this.order);
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