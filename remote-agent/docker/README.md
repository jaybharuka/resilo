# Resilo Docker Agent

Build image:

```bash
docker build -t resilo/agent:latest -f agent/Dockerfile .
```

Run with existing org and agent key:

```bash
docker run --rm \
  -e RESILO_BACKEND_URL=http://host.docker.internal:8000 \
  -e RESILO_ORG_ID=<org-id> \
  -e RESILO_AGENT_KEY=<agent-key> \
  resilo/agent:latest
```

Auto-register using admin token:

```bash
docker run --rm \
  -e RESILO_BACKEND_URL=http://host.docker.internal:8000 \
  -e RESILO_REGISTER_TOKEN=<admin-jwt> \
  -e RESILO_AGENT_LABEL=docker-agent-01 \
  resilo/agent:latest
```
