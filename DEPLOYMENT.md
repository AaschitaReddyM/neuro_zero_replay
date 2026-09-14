# NeuroZero Replay: Production Deployment Guide
**Agentic Computer-Use & Deterministic Replay Engine**

This guide covers deploying the NeuroZero Replay system in production environments.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum (8GB recommended)
- OpenAI API key (for LLM-driven discovery)

## Quick Start

### Local Development

```bash
# Clone repository
git clone https://github.com/AaschitaReddyM/neuro_zero_replay.git
cd neuro_zero_replay

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Start target application
cd target-app && python -m http.server 8080

# In another terminal, generate artifacts
python mock_discovery.py
python mock_discovery_transfer.py
python mock_discovery_account.py

# Run tests
python test_replay.py
python test_error_scenarios.py
python test_integration.py
```

### Docker Deployment

```bash
# Build and start services
docker-compose up -d

# Verify services are running
docker-compose ps

# View logs
docker-compose logs -f target-app
docker-compose logs -f automation-worker

# Execute commands in worker container
docker-compose exec automation-worker python mock_discovery.py
```

## Production Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Load Balancer                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐
│  Worker 1    │ │ Worker 2 │ │  Worker N  │
│  (Scaled)    │ │ (Scaled) │ │  (Scaled)  │
└───────┬──────┘ └────┬─────┘ └─────┬──────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
              ┌────────▼────────┐
              │  Artifact Store  │
              │  (Shared Volume) │
              └────────┬─────────┘
                       │
              ┌────────▼────────┐
              │  Target Apps    │
              │  (Multiple)     │
              └─────────────────┘
```

### Scaling Strategy

**Vertical Scaling**: Increase worker resources for higher throughput
**Horizontal Scaling**: Add more worker instances for parallel execution
**Artifact Isolation**: Separate artifact stores per tenant for multi-tenancy

## Configuration

### Environment Variables

```bash
# Required
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o

# Application
TARGET_APP_URL=http://target-app:8080
MAX_AGENT_STEPS=20
AGENT_TIMEOUT_SECONDS=300

# Safety
ALLOWED_DOMAINS=localhost,127.0.0.1,target-app,your-domain.com
ALLOWED_ACTION_TYPES=navigate,click,type,extract,wait,select
RISKY_ACTION_TYPES=submit,confirm

# Logging
LOG_LEVEL=INFO
LOG_DIR=/app/logs

# Storage
EVIDENCE_DIR=/app/evidence
ARTIFACT_DIR=/app/evidence/artifacts
```

### Production Docker Compose

```yaml
version: '3.8'

services:
  # Multiple target applications
  target-app:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./evidence:/app/evidence
    restart: always

  # Scaled automation workers
  automation-worker:
    build: .
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 4G
    volumes:
      - ./evidence:/app/evidence
      - ./logs:/app/logs
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - TARGET_APP_URL=http://target-app:8080
    depends_on:
      - target-app
    restart: always

  # Metrics collection (optional)
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  # Visualization (optional)
  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
```

## Monitoring

### Metrics Collection

The system automatically collects:
- Execution success rates
- Average execution times
- Error recovery rates
- Fallback strategy efficiency
- Artifact confidence scores

### Viewing Metrics

```bash
# Generate performance report
python -c "from src.artifact.metrics import metrics_collector; print(metrics_collector.generate_performance_report())"

# View artifact marketplace status
python -c "from src.artifact.marketplace import ArtifactMarketplace; m = ArtifactMarketplace(); print(m.generate_marketplace_report())"
```

### Prometheus Integration (Optional)

Configure Prometheus to scrape metrics from your automation workers:

```yaml
# monitoring/prometheus.yml
scrape_configs:
  - job_name: 'automation-workers'
    static_configs:
      - targets: ['automation-worker:8000']
```

## Security

### Production Security Checklist

- [ ] Use secrets management for API keys (AWS Secrets Manager, HashiCorp Vault)
- [ ] Enable TLS/SSL for all communications
- [ ] Implement network segmentation between services
- [ ] Use read-only filesystems where possible
- [ ] Implement rate limiting for API endpoints
- [ ] Regular security updates for dependencies
- [ ] Audit logging for all automation executions
- [ ] Data encryption at rest and in transit

### Docker Security

```bash
# Run as non-root user
USER automation

# Read-only root filesystem
READ_ONLY_ROOT_FILESYSTEM=true

# Drop capabilities
CAP_DROP=ALL
CAP_ADD=NET_BIND_SERVICE
```

## Multi-Tenant Deployment

### Tenant Isolation Strategies

**Artifact Namespaces**: Separate artifact directories per tenant
```
/evidence/
  /tenant1/
    /artifacts/
  /tenant2/
    /artifacts/
```

**Environment Variables**: Tenant-specific configuration
```bash
TENANT_ID=tenant1
ARTIFACT_DIR=/app/evidence/tenant1/artifacts
```

**Database Integration**: Store tenant metadata and routing rules
```python
# Tenant routing logic
tenant_config = get_tenant_config(tenant_id)
artifact_dir = f"/app/evidence/{tenant_id}/artifacts"
```

## Troubleshooting

### Common Issues

**Worker fails to start**: Check if target app is accessible
```bash
docker-compose exec automation-worker curl http://target-app:8080
```

**Artifact not found**: Verify artifact paths and permissions
```bash
docker-compose exec automation-worker ls -la /app/evidence/artifacts/
```

**Memory issues**: Increase worker memory limits
```yaml
deploy:
  resources:
    limits:
      memory: 8G
```

**Browser execution failures**: Ensure Playwright browsers are installed
```bash
docker-compose exec automation-worker playwright install --with-deps chromium
```

## Performance Optimization

### Caching Strategy

- Cache LLM responses for similar goals
- Cache artifact validation results
- Cache accessibility tree snapshots

### Execution Optimization

- Parallel execution of independent artifacts
- Connection pooling for browser instances
- Async I/O for all network operations

### Resource Management

- Browser instance pooling and reuse
- Graceful shutdown with in-flight completion
- Memory limits and monitoring

## Backup and Recovery

### Artifact Backup

```bash
# Backup artifacts
tar -czf artifacts-backup-$(date +%Y%m%d).tar.gz evidence/artifacts/

# Restore artifacts
tar -xzf artifacts-backup-20240912.tar.gz
```

### Database Backup (if using external storage)

```bash
# Backup tenant metadata
pg_dump automation_db > backup.sql

# Restore tenant metadata
psql automation_db < backup.sql
```

## Upgrade Strategy

### Rolling Updates

```bash
# Update one worker at a time
docker-compose up -d --no-deps --build automation-worker

# Verify health before proceeding
docker-compose ps automation-worker
```

### Artifact Versioning

- Maintain backward compatibility for artifact schemas
- Support multiple artifact versions simultaneously
- Gradual migration from old to new versions

## Support and Maintenance

### Log Analysis

```bash
# View recent errors
docker-compose logs --tail=100 automation-worker | grep ERROR

# Monitor execution times
docker-compose logs -f automation-worker | grep "execution_time"
```

### Health Checks

```bash
# System health check
curl http://localhost:8080/health

# Worker health check
docker-compose exec automation-worker python -c "import sys; sys.exit(0)"
```

### Maintenance Windows

- Schedule maintenance during low-traffic periods
- Use blue-green deployment for zero-downtime updates
- Communicate maintenance windows to stakeholders

## Cost Optimization

### Resource Rightsizing

- Monitor actual resource usage
- Right-size worker instances based on metrics
- Use spot instances for non-critical workloads

### Cost Monitoring

- Track API usage and costs
- Monitor infrastructure costs
- Implement cost alerts and budgets

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Playwright Documentation](https://playwright.dev/)
- [Prometheus Monitoring](https://prometheus.io/)
- [Security Best Practices](https://snyk.io/blog/10-docker-image-security-best-practices/)