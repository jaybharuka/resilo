FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py .
COPY llm_service.py .
COPY analytics_service.py .
COPY templates/ templates/
EXPOSE 5000
CMD ["python", "app.py"]
