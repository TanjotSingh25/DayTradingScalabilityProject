# source(s): Assistance provided by ChatGPT (permitted by course instructor)

# Use Python 3.9 as the base image
FROM python:3.9

# Set the working directory inside the container
WORKDIR /app

# Copy only requirements.txt first (for better caching)
COPY PortfolioStockService/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files into /app/
COPY . /app

# Expose Flask port
EXPOSE 5000

# Run Flask app
CMD ["python", "/app/profile_stock_service.py"]
