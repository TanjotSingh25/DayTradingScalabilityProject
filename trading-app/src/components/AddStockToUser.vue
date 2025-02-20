<template>
    <div>
      <h2>Add Stock to Portfolio</h2>
      <form @submit.prevent="addStock">
        <input v-model="stockId" placeholder="Stock ID" required />
        <input v-model.number="quantity" placeholder="Quantity" type="number" required />
        <button type="submit">Add Stock</button>
      </form>
      <p v-if="message">{{ message }}</p>
    </div>
</template>

<script>
import axios from 'axios';

export default {
    data() {
        return {
            stockId: "",
            quantity: 1,
            message: ""
        };
    },
    methods: {
        async addStock() {
            try {
                const response = await axios.post('/addStockToUser', {
                    stock_id: this.stockId,
                    quantity: this.quantity
                }, {
                    headers: {
                        token: "jwt_token"
                    }
                });
                this.message = "Stock added successfully.";
                console.log('Response:', response.data);
            } catch (error) {
                this.message = "Failed to add stock to portfolio.";
                console.error('Error:', error);
            }
        }
    }
};
</script>