<template>
    <div class="auth-container">
        <h2>Login</h2>
        <form @submit.prevent="handleLogin">
            <input
                type="text"
                v-model="user_name"
                placeholder="Username"
                required
            />
            <input
                type="password"
                v-model="password"
                placeholder="Password"
                required
            />
            <button type="submit">Login</button>
        </form>
        <p v-if="message">{{ message }}</p>
        <!-- New Register Link -->
        <p>
            Don't have an account?
            <router-link to="/register">Register here</router-link>
        </p>
    </div>
</template>

<script>
import axios from "axios";

export default {
    name: "LoginPage",
    data() {
        return {
            user_name: "",
            password: "",
            message: "",
        };
    },
    methods: {
        async handleLogin() {
            try {
                const response = await axios.post(
                    "http://localhost/authentication/login",
                    {
                        user_name: this.user_name,
                        password: this.password,
                    }
                );

                localStorage.setItem("token", response.data.data.token);
                this.message = "Login successful!";
                this.$router.push("/homepage");
            } catch (error) {
                this.message = "Invalid credentials. Try again.";
            }
        },
    },
};
</script>

<style>
.auth-container {
    max-width: 300px;
    margin: auto;
    padding: 20px;
    text-align: center;
}
input,
button {
    width: 100%;
    padding: 10px;
    margin: 5px 0;
}
button {
    background: blue;
    color: white;
    border: none;
}
</style>
