<template>
    <div class="auth-container">
      <h2>Register</h2>
      <form @submit.prevent="handleRegister">
        <input type="text" v-model="user_name" placeholder="Username" required />
        <input type="password" v-model="password" placeholder="Password" required />
        <input type="text" v-model="name" placeholder="Full Name" required />
        <button type="submit">Register</button>
      </form>
      <p v-if="message">{{ message }}</p>
    </div>
  </template>
  
  <script>
  import axios from "axios";
  export default {
    name: "RegisterPage",
    data() {
      return {
        user_name: "",
        password: "",
        name: "",
        message: "",
      };
    },
    methods: {
      async handleRegister() {
        try {
          const response = await axios.post("http://localhost/api/v1/auth/register/", {
            user_name: this.user_name,
            password: this.password,
            name: this.name,
          });
          if (response.data.success) {
            this.message = "Registration successful. Redirect to login page.";
            this.$router.push("/");
          } 
        } catch (error) {
          console.error("API Error:", error);
          if (error.response) {
            if (error.response.status === 400 && error.response.data.message === "Username already exists") {
              this.message = "Username already exists";
            } else {
                this.message = error.response.data?.message || `Error: ${error.response.status}`;
            }
          } else if (error.request) {
            this.message = "Error: Cannot reach backend";
          } else {
            this.message = "Error: Request setup failed";
          }
        }
      },
    },
  };
  </script>
  