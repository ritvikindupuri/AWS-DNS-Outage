# AWS DNS Outage Prevention and Resilience System

## Introduction

This project provides a comprehensive system for preventing DNS-related outages and ensuring multi-region resilience for AWS infrastructure. It is designed to proactively monitor critical AWS service endpoints, detect DNS resolution failures, and automate failover procedures to maintain high availability. The system includes a real-time web dashboard for at-a-glance monitoring and detailed analysis of service health.

## Key Features

### DNS Outage Prevention
- **Real-Time DNS Monitoring**: Continuously checks the DNS resolution of critical AWS service endpoints (DynamoDB, RDS, Lambda, EC2, ELB, S3) across multiple regions.
- **Cascade Failure Prevention**: Identifies and mitigates the risk of cascade failures by monitoring service dependencies and analyzing the potential impact of a DNS failure.
- **Automated Response**: Triggers automated responses to DNS failures, including scaling actions, failover procedures, and notifications.

### Multi-Region Resilience
- **Automated Failover**: Automatically switches traffic between primary and secondary regions in the event of an outage.
- **Health Checks**: Performs comprehensive health checks on all services in each region to determine the optimal failover target.
- **DNS and CDN Updates**: Updates Route 53 DNS records and CloudFront distributions to redirect traffic to the healthy region.

### Live Monitoring and Visualization
- **Web Dashboard**: A real-time, responsive web dashboard provides a comprehensive view of system health, including multi-region status, service health matrix, and detailed endpoint information.
- **CloudWatch Dashboards**: Creates detailed CloudWatch dashboards in the AWS Console for at-a-glance monitoring of DNS health, cascade risk, and service dependencies.
- **Custom Metrics and Alarms**: Publishes custom CloudWatch metrics for DNS success rate, response time, and overall system health, and configures alarms to trigger on critical thresholds.

## Architecture

The system is designed for high availability and multi-region resilience. The following diagram illustrates the architecture:

```
<img src="./assets/Screenshot 2025-10-25 180609.png" width="800" alt="[Describe the image content here]">
<p align="center">*Figure Y: [Add your caption here].*</p>
```

## System Components

### Core Logic
- **`outage_prevention_system.py`**: The core of the DNS monitoring and outage prevention system. It performs health checks, analyzes DNS resolution, assesses cascade failure risk, and triggers automated responses.
- **`multi_region_failover.py`**: Implements the logic for automatic multi-region failover. It continuously monitors the health of primary and secondary regions and manages the failover process.

### Deployment and Configuration
- **`deployment_script.py`**: A comprehensive script that automates the deployment of the entire system, including IAM roles, Lambda functions, EventBridge rules, and CloudWatch dashboards.
- **`deploy_outage_prevention.py`**: The main entry point for deploying the system. It checks for prerequisites, installs dependencies, and executes the deployment script.
- **`cloudformation.yaml`** and **`resilience_architecture.yaml`**: CloudFormation templates that define the core AWS infrastructure, including VPC, subnets, security groups, and ECS cluster.

### Monitoring and Visualization
- **`web_dashboard.py`**: A Flask-based web application that provides the real-time monitoring dashboard.
- **`dashboard.html`**: The HTML template for the web dashboard.
- **`live_dashboard.py`**: Creates and manages the CloudWatch dashboards in the AWS Console.
- **`enhanced_dns_monitor.py`** and **`simple_dns_monitor.py`**: Terminal-based monitoring scripts for DNS health checks.
- **`launch_dashboard.py`**: A simple script to launch the web dashboard.

## Getting Started

### Prerequisites
- Python 3.7+
- AWS CLI
- Configured AWS credentials

### Deployment
1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```
2. **Run the deployment script:**
   ```bash
   python deploy_outage_prevention.py
   ```
   This will guide you through the deployment process, which includes installing dependencies and provisioning the necessary AWS resources.

### Accessing the Dashboard
Once the deployment is complete, you can access the web dashboard by running:
```bash
python launch_dashboard.py
```
This will start the web server and open the dashboard in your default browser at `http://localhost:5000`.

## Configuration

The system can be configured through environment variables and by modifying the Python scripts.

### Environment Variables
- `AWS_REGION`: The primary AWS region.
- `ENVIRONMENT`: The deployment environment (e.g., `production`, `staging`).

### Custom Thresholds
The failover thresholds can be customized in `multi_region_failover.py`:
- `health_threshold`: The minimum health score for a region to be considered healthy.
- `response_time_threshold`: The maximum response time for health checks.
- `consecutive_failures_threshold`: The number of consecutive failures before triggering a failover.

## Testing

The system includes functionality for simulating outage scenarios and performing load testing.

### Simulate Failover
You can test the failover mechanism by calling the `perform_failover` method in `multi_region_failover.py`:
```python
from multi_region_failover import MultiRegionFailoverManager
manager = MultiRegionFailoverManager()
manager.perform_failover('us-east-1', 'us-west-2', 'Testing')
```

### Load Testing
You can use tools like `ab` (Apache Bench) to generate traffic and test the system's scaling capabilities:
```bash
ab -n 10000 -c 100 http://your-load-balancer-dns/
```

## Contributing

Contributions are welcome. Please follow these steps:
1. Fork the repository.
2. Create a new feature branch.
3. Add tests for your new functionality.
4. Submit a pull request.
