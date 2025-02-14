FROM python:3.11-slim
WORKDIR /app
<<<<<<< HEAD
COPY . /app
RUN pip install flask pymongo 
=======
COPY MatchingEngineService /app
RUN pip install flask
>>>>>>> frontend
EXPOSE 5300
CMD ["python", "matching_engine_service.py"]
