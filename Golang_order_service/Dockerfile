# Use a lightweight Golang image for building
FROM golang:1.19 as builder

# Set the working directory inside the container
WORKDIR /app

# Copy go.mod and go.sum first (dependency caching)
COPY go.mod go.sum ./

# Download Go dependencies
RUN go mod tidy

# Copy the rest of the application source code
COPY . .

# Build the Go application, ensuring it's named correctly
RUN go build -o golang_order_service golangOrderService.go

# Use a minimal runtime image for the final container
FROM gcr.io/distroless/base-debian11

# Set the working directory inside the runtime container
WORKDIR /app

# Copy the built binary from the builder stage
COPY --from=builder /app/golang_order_service .

# Expose the port (Make sure your app listens on this port)
EXPOSE 5300

# Run the compiled Go application
CMD ["/app/golang_order_service"]
