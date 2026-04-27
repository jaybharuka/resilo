FROM python:3.11-slim

WORKDIR /app
COPY agent/docker_agent.py /app/docker_agent.py
RUN pip install --no-cache-dir psutil

ENV RESILO_BACKEND_URL=http://host.docker.internal:8000
ENV RESILO_AGENT_INTERVAL=5

ENTRYPOINT ["python", "/app/docker_agent.py"]
