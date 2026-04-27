# AIOps Platform API Documentation

## Authentication

### JWT Authentication
```bash
# Login to get JWT token
curl -X POST http://localhost:8090/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "<your-admin-password>"}'

# Use token in subsequent requests
curl -H "Authorization: Bearer <token>" \
  http://localhost:8090/api/v1/monitoring/metrics
```

### API Key Authentication
```bash
curl -H "X-API-Key: <api-key>" \
  http://localhost:8090/api/v1/monitoring/metrics
```

## API Endpoints

### Authentication Endpoints

#### POST /auth/login
Authenticate user and receive JWT token.

**Request:**
```json
{
  "username": "admin",
  "password": "<your-admin-password>"
}
```

**Response:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "user_id": "admin-001",
    "username": "admin",
    "roles": ["admin"]
  }
}
```

### Monitoring Endpoints

#### GET /api/v1/monitoring/metrics
Get current system performance metrics.

**Headers:**
- `Authorization: Bearer <token>` OR
- `X-API-Key: <api-key>`

**Response:**
```json
{
  "cpu_usage": 45.2,
  "memory_usage": 67.8,
  "disk_usage": 23.1,
  "timestamp": "2025-09-14T10:30:00Z"
}
```

#### GET /api/v1/monitoring/health
Health check for all system components.

**Response:**
```json
{
  "status": "healthy",
  "components": {
    "api_gateway": "healthy",
    "orchestrator": "healthy",
    "performance_monitor": "healthy",
    "analytics_engine": "healthy",
    "config_manager": "healthy"
  },
  "timestamp": "2025-09-14T10:30:00Z"
}
```

### Analytics Endpoints

#### GET /api/v1/analytics/reports
Get available analytics reports.

**Response:**
```json
{
  "reports": [
    {
      "id": 1,
      "name": "System Performance",
      "status": "completed",
      "created_at": "2025-09-14T09:00:00Z"
    },
    {
      "id": 2,
      "name": "Security Analysis",
      "status": "running",
      "created_at": "2025-09-14T10:00:00Z"
    }
  ]
}
```

#### POST /api/v1/analytics/reports
Create a new analytics report.

**Request:**
```json
{
  "name": "Custom Performance Report",
  "type": "performance",
  "parameters": {
    "start_date": "2025-09-01",
    "end_date": "2025-09-14",
    "metrics": ["cpu", "memory", "response_time"]
  }
}
```

### Configuration Endpoints

#### GET /api/v1/config/{key}
Get configuration value.

**Response:**
```json
{
  "key": "database.host",
  "value": "localhost",
  "environment": "development",
  "last_updated": "2025-09-14T08:00:00Z"
}
```

#### PUT /api/v1/config/{key}
Update configuration value.

**Request:**
```json
{
  "value": "new-value",
  "environment": "development"
}
```

### Auto-Scaling Endpoints

#### POST /api/v1/automation/scale
Trigger scaling operation.

**Request:**
```json
{
  "service": "analytics-engine",
  "target_instances": 5,
  "reason": "High CPU usage detected"
}
```

**Response:**
```json
{
  "message": "Scaling operation initiated",
  "service": "analytics-engine",
  "current_instances": 2,
  "target_instances": 5,
  "estimated_completion": "2025-09-14T10:35:00Z"
}
```

## Error Responses

### Authentication Errors
```json
{
  "error": "Authentication required",
  "code": 401
}
```

### Authorization Errors
```json
{
  "error": "Insufficient permissions",
  "code": 403
}
```

### Rate Limiting
```json
{
  "error": "Rate limit exceeded",
  "reset_time": "2025-09-14T10:31:00Z",
  "code": 429
}
```

### Server Errors
```json
{
  "error": "Internal server error",
  "request_id": "req-123456",
  "timestamp": "2025-09-14T10:30:00Z",
  "code": 500
}
```

## Rate Limiting

- **Default**: 1000 requests per minute per user
- **Auto-scaling**: 10 requests per minute
- **Headers**: Rate limit information in response headers
  - `X-RateLimit-Limit`: Maximum requests allowed
  - `X-RateLimit-Remaining`: Remaining requests in current window
  - `X-RateLimit-Reset`: Unix timestamp when limit resets

## Pagination

For endpoints returning lists, use pagination parameters:

```bash
curl "http://localhost:8090/api/v1/analytics/reports?page=1&limit=10"
```

**Response includes pagination metadata:**
```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "limit": 10,
    "total": 42,
    "total_pages": 5
  }
}
```

Generated on: {datetime.now().isoformat()}
