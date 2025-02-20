<template>
    <div>
      <nav>
        <router-link to="/place-order">Place Order</router-link> |
        <router-link to="/view-transactions">View Transactions</router-link> |
        <router-link to="/cancel-transaction">Cancel Transaction</router-link> |
        <router-link to="/create-stock">Place Order</router-link> |
        <router-link to="/add-stock">View Transactions</router-link> |
        <router-link to="/portfolio">Cancel Transaction</router-link> |
        <router-link to="/add-money">Place Order</router-link> |
        <router-link to="/wallet-balance">View Transactions</router-link>
      </nav>
      <router-view />
    </div>
  </template>