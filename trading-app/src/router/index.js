import { createRouter, createWebHistory } from 'vue-router';
import LoginPage from "@/components/LoginPage.vue";
import RegisterPage from "@/components/RegisterPage.vue";
import HomePage from "@/components/HomePage.vue";
import PlaceOrder from '../components/PlaceOrder.vue';
import ViewTransactions from '../components/ViewTransactions.vue';
import CancelTransaction from '../components/CancelTransaction.vue';
import CreateStock from '@/components/CreateStock.vue';
import AddMoneyToWallet from '@/components/AddMoneyToWallet.vue';
import AddStockToUser from '@/components/AddStockToUser.vue';
import GetWalletBalance from '@/components/GetWalletBalance.vue';
import StockPortfolio from '@/components/StockPortfolio.vue';

const routes = [
  { path: "/", component: LoginPage },
  { path: "/register", component: RegisterPage },
  { path: "/homepage", component: HomePage},
  { path: '/place-order', component: PlaceOrder },
  { path: '/view-transactions', component: ViewTransactions },
  { path: '/cancel-transaction', component: CancelTransaction },
  { path: '/create-stock', component: CreateStock },
  { path: '/add-money', component: AddMoneyToWallet},
  { path: '/add-stock', component: AddStockToUser},
  { path: '/wallet-balance', component: GetWalletBalance },
  { path: '/portfolio', component: StockPortfolio}
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to,from,next) => {
  const isAuthenticated = !!localStorage.getItem("token");
  if (to.meta.requiresAuth && !isAuthenticated) {
    next("/");
  } else {
    next();
  }
});

export default router;