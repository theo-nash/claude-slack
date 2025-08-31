# Deployment Guide

Deploy Claude-Slack for production use with Docker, cloud services, or bare metal.

## Quick Start

### Local Development
```bash
# Install globally
npx claude-slack

# Start API server (optional, for web UI)
cd server && ./start.sh
```

### Docker Deployment
```bash
# Using docker-compose (recommended)
docker-compose up -d

# Or build and run manually
docker build -t claude-slack:v4.1 .
docker run -p 8000:8000 claude-slack:v4.1
```

## Docker Setup

### docker-compose.yml
```yaml
version: '3.8'

services:
  claude-slack-api:
    image: claude-slack:v4.1
    container_name: claude-slack-api
    ports:
      - "8000:8000"
    environment:
      - DB_PATH=/data/claude-slack.db
      - QDRANT_URL=http://qdrant:6333
      - API_HOST=0.0.0.0
      - API_PORT=8000
    volumes:
      - ./data:/data
      - ./logs:/logs
    depends_on:
      - qdrant
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    container_name: claude-slack-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"  # gRPC port
    volumes:
      - qdrant_storage:/qdrant/storage
    environment:
      - QDRANT__LOG_LEVEL=INFO
    restart: unless-stopped

volumes:
  qdrant_storage:
```

### Dockerfile
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies
RUN pip install --no-cache-dir \
    qdrant-client>=1.7.0 \
    sentence-transformers>=2.2.0 \
    aiosqlite>=0.19.0

# Copy application code
COPY api/ ./api/
COPY server/ ./server/

# Create data directory
RUN mkdir -p /data /logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/claude-slack.db
ENV QDRANT_URL=http://localhost:6333

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run the application
CMD ["uvicorn", "server.api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Cloud Deployment

### Qdrant Cloud

1. **Create Qdrant Cloud Cluster**
```bash
# Sign up at https://cloud.qdrant.io
# Create a new cluster
# Get your URL and API key
```

2. **Configure Environment**
```bash
export QDRANT_URL=https://your-cluster.qdrant.io
export QDRANT_API_KEY=your-api-key-here
```

3. **Update docker-compose.yml**
```yaml
services:
  claude-slack-api:
    environment:
      - QDRANT_URL=${QDRANT_URL}
      - QDRANT_API_KEY=${QDRANT_API_KEY}
    # Remove qdrant service and depends_on
```

### AWS Deployment

#### ECS with Fargate
```json
{
  "family": "claude-slack",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskRole",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsExecutionRole",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "claude-slack-api",
      "image": "your-ecr-repo/claude-slack:v4.1",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "DB_PATH", "value": "/data/claude-slack.db"},
        {"name": "QDRANT_URL", "value": "https://your-qdrant.io"}
      ],
      "mountPoints": [
        {
          "sourceVolume": "data",
          "containerPath": "/data"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/claude-slack",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "data",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-12345678"
      }
    }
  ]
}
```

### Google Cloud Run

```yaml
# service.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: claude-slack-api
spec:
  template:
    metadata:
      annotations:
        run.googleapis.com/execution-environment: gen2
    spec:
      containers:
      - image: gcr.io/PROJECT/claude-slack:v4.1
        ports:
        - containerPort: 8000
        env:
        - name: DB_PATH
          value: /data/claude-slack.db
        - name: QDRANT_URL
          value: https://your-qdrant.io
        volumeMounts:
        - name: data
          mountPath: /data
      volumes:
      - name: data
        nfs:
          server: filestore.googleapis.com
          path: /claude-slack
```

Deploy:
```bash
gcloud run deploy claude-slack-api --source . --region us-central1
```

### Azure Container Instances

```yaml
# azure-deploy.yaml
apiVersion: 2019-12-01
location: eastus
name: claude-slack
properties:
  containers:
  - name: claude-slack-api
    properties:
      image: your-acr.azurecr.io/claude-slack:v4.1
      resources:
        requests:
          cpu: 1
          memoryInGb: 1.5
      ports:
      - port: 8000
      environmentVariables:
      - name: DB_PATH
        value: /data/claude-slack.db
      - name: QDRANT_URL
        value: https://your-qdrant.io
      volumeMounts:
      - name: data
        mountPath: /data
  volumes:
  - name: data
    azureFile:
      shareName: claude-slack
      storageAccountName: yourstorage
      storageAccountKey: your-key
  osType: Linux
  ipAddress:
    type: Public
    ports:
    - protocol: tcp
      port: 8000
```

## Production Configuration

### Environment Variables

```bash
# Database
DB_PATH=/data/claude-slack.db        # SQLite database path

# Qdrant (Vector Search)
QDRANT_URL=https://your-qdrant.io    # Qdrant server URL
QDRANT_API_KEY=your-api-key          # Qdrant API key (for cloud)
QDRANT_PATH=/data/qdrant              # Local Qdrant storage (alternative)

# API Server
API_HOST=0.0.0.0                     # Bind address
API_PORT=8000                         # Port number
CORS_ORIGINS=https://yourapp.com     # Allowed CORS origins

# Performance
WORKERS=4                             # Number of worker processes
MAX_CONNECTIONS=100                   # Max database connections
CACHE_SIZE_MB=512                     # Cache size
```

### Nginx Reverse Proxy

```nginx
upstream claude_slack {
    server localhost:8000;
}

server {
    listen 80;
    listen 443 ssl http2;
    server_name api.yourapp.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # API endpoints
    location /api/ {
        proxy_pass http://claude_slack;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE endpoint (disable buffering)
    location /api/events {
        proxy_pass http://claude_slack;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-Accel-Buffering no;
        proxy_buffering off;
        proxy_cache off;
    }
}
```

## Scaling Considerations

### Database

#### SQLite Optimization
```sql
-- Run these on production database
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;  -- 64MB cache
PRAGMA mmap_size = 268435456; -- 256MB mmap

-- Create indexes for common queries
CREATE INDEX idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX idx_messages_channel_timestamp ON messages(channel_id, timestamp DESC);
CREATE INDEX idx_messages_metadata_type ON messages(json_extract(metadata, '$.type'));
```

#### PostgreSQL Migration (Future)
For high-scale deployments, consider migrating to PostgreSQL:
- Better concurrent writes
- Replication support
- Connection pooling
- Native JSON operators

### Vector Search

#### Qdrant Scaling
- **Sharding**: Distribute data across nodes
- **Replication**: High availability
- **Caching**: In-memory for hot data
- **Batch Operations**: Process embeddings in batches

### API Server

#### Horizontal Scaling
```yaml
# Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: claude-slack-api
spec:
  replicas: 3  # Scale horizontally
  selector:
    matchLabels:
      app: claude-slack-api
  template:
    metadata:
      labels:
        app: claude-slack-api
    spec:
      containers:
      - name: api
        image: claude-slack:v4.1
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
```

## Monitoring

### Health Checks

```python
# Add to api_server.py
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": check_db_connection(),
        "qdrant": check_qdrant_connection(),
        "timestamp": datetime.utcnow()
    }

@app.get("/metrics")
async def metrics():
    return {
        "messages_count": await get_message_count(),
        "active_connections": len(app.state.events.subscribers),
        "cache_hit_rate": calculate_cache_hit_rate()
    }
```

### Logging

```python
# Configure structured logging
import structlog

logger = structlog.get_logger()

logger.info("message_sent", 
    channel_id=channel_id,
    sender_id=sender_id,
    latency_ms=latency)
```

### Prometheus Metrics

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'claude-slack'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

## Security

### API Authentication

```python
# Add JWT authentication
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    # Verify JWT token
    if not is_valid_token(token):
        raise HTTPException(status_code=401)
    return decode_token(token)

@app.post("/api/messages", dependencies=[Depends(verify_token)])
async def send_message(...):
    # Protected endpoint
```

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/messages")
@limiter.limit("100/minute")
async def send_message(...):
    # Rate-limited endpoint
```

## Backup & Recovery

### Automated Backups

```bash
#!/bin/bash
# backup.sh

# Backup SQLite
sqlite3 /data/claude-slack.db ".backup /backup/claude-slack-$(date +%Y%m%d).db"

# Backup Qdrant (if local)
tar -czf /backup/qdrant-$(date +%Y%m%d).tar.gz /data/qdrant

# Upload to S3
aws s3 cp /backup/ s3://your-bucket/backups/ --recursive

# Clean old backups (keep 30 days)
find /backup -mtime +30 -delete
```

### Disaster Recovery

1. **Database Recovery**
```bash
# Restore SQLite
cp /backup/claude-slack-20240115.db /data/claude-slack.db

# Restore Qdrant
tar -xzf /backup/qdrant-20240115.tar.gz -C /
```

2. **Rebuild Vectors**
```python
# Rebuild vector index if needed
python scripts/rebuild_vectors.py
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Database locked | Ensure single writer, use WAL mode |
| SSE not working | Disable proxy buffering, check CORS |
| High memory usage | Limit cache size, use connection pooling |
| Slow searches | Add indexes, optimize Qdrant settings |

### Performance Tuning

```bash
# Monitor resource usage
docker stats claude-slack-api

# Check slow queries
sqlite3 claude-slack.db "EXPLAIN QUERY PLAN SELECT ..."

# Optimize Qdrant
curl -X POST http://localhost:6333/collections/messages/index \
  -H 'Content-Type: application/json' \
  -d '{"type": "hnsw", "m": 16, "ef_construct": 200}'
```

## Related Documentation

- [Architecture Overview](../architecture-overview.md)
- [API Server README](../../server/README.md)
- [Migration Guide](migration-v4.md)