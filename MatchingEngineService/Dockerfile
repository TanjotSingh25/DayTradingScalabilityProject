FROM python:3.11-slim
WORKDIR /app
COPY MatchingEngineService /app
RUN pip install flask pyjwt
EXPOSE 5300
CMD ["python", "matching_engine_service.py"]
