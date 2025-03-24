FROM python:3.9-slim
WORKDIR /app
COPY . /app
RUN pip install flask pymongo pyjwt requests flask-cors redis
EXPOSE 5200
CMD ["python", "order_service.py"]
