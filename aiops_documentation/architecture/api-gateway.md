# API Gateway Component Documentation

## Overview
Central entry point and security layer

## Configuration
- **Port**: 8090
- **Health Check**: /health

## Features

### API Endpoints
- GET /health - Health check
- POST /auth/login - User authentication
- GET /docs - API documentation
- GET /gateway/metrics - Gateway metrics
- * /api/* - Proxied API requests

### Configuration Options
- **JWT_SECRET**: JWT signing secret
- **RATE_LIMIT**: Requests per minute limit
- **LOG_LEVEL**: Logging verbosity

Generated on: 2025-09-14T16:14:42.323361
