import { createApp } from "vue";
import App from "./App.vue"; // Import the root App component
import router from "./router"; // Import the router configuration

localStorage.clear();

// Create the Vue app
const app = createApp(App);

// Use the router
app.use(router);

// Mount the app to the DOM element with id 'app'
app.mount("#app");
