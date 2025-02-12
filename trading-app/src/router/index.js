import { createRouter, createWebHistory } from 'vue-router';
import PlaceOrder from '../components/PlaceOrder.vue';
import ViewTransactions from '../components/ViewTransactions.vue';
import CancelTransaction from '../components/CancelTransaction.vue';

const routes = [
  { path: '/place-order', component: PlaceOrder },
  { path: '/view-transactions', component: ViewTransactions },
  { path: '/cancel-transaction', component: CancelTransaction },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;