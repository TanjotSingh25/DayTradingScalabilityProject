CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    birth_date DATE,
    money_spent NUMERIC(12, 2) DEFAULT 0,
    anniversary DATE
);

CREATE TABLE employees (
    employee_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    birth_date DATE
);

CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    price NUMERIC(12, 2) NOT NULL
);

CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL,
    product_id INT NOT NULL,
    employee_id INT,
    order_total NUMERIC(12, 2) NOT NULL,
    order_date DATE DEFAULT CURRENT_DATE,

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_orders_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_orders_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id)
        ON DELETE SET NULL
);
