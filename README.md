Please run these steps before running a jmeter script

(Within main directory with all the service folders)

Step 1: docker-compose down -v

Step 2: docker-compose up --build

Step 3: Wait for all services to be up and running

Step 4: Run Jmeter test file (specifications: localhost, port 80)


To launch frontend, cd into the trading-app directory

npm install

npm run serve

Click on frontend link

Passed Jmeter Tests Screenshot:
![image](https://github.com/user-attachments/assets/b6254300-bfe0-41dc-bfc4-2fc263f06633)


