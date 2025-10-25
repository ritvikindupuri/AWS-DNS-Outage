"""
DNS Management Failure Prevention System
Specifically designed to prevent DNS resolution failures like the AWS DynamoDB outage
Monitors DNS records, detects inconsistencies, and prevents cascade failures
"""

import boto3
import json
import time
import logging
import socket
import dns.resolver
import dns.exception
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import threading
from dataclasses import dataclass
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DNSRecord:
    """DNS record data structure"""
    name: str
    record_type: str
    values: List[str]
    ttl: int
    timestamp: datetime
    region: str
    service: str

@dataclass
class DNSHealthCheck:
    """DNS health check result"""
    endpoint: str
    region: str
    service: str
    resolution_success: bool
    resolved_ips: List[str]
    response_time: float
    timestamp: datetime
    error_message: Optional[str]

@dataclass
class CascadeRisk:
    """Service cascade failure risk assessment"""
    service: str
    region: str
    dependency_services: List[str]
    risk_score: float
    potential_impact: str
    mitigation_actions: List[str]

@dataclass
class OutageAlert:
    """DNS-specific outage alert"""
    alert_id: str
    severity: str
    alert_type: str  # 'dns_failure', 'cascade_risk', 'endpoint_unreachable'
    service: str
    region: str
    affected_endpoints: List[str]
    message: str
    timestamp: datetime
    predicted_impact: str
    recommended_actions: List[str]

class DNSOutagePreventionSystem:
    """
    DNS Management Failure Prevention System
    Specifically prevents DNS resolution failures that cause cascade outages
    Monitors DNS records, detects inconsistencies, prevents endpoint removal
    """
    
    def __init__(self, regions: List[str] = None):
        self.regions = regions or ['us-east-1', 'us-west-2', 'eu-west-1']
        self.clients = self._initialize_clients()
        self.dns_records_history = []
        self.dns_health_checks = []
        self.cascade_risks = []
        self.alerts = []
        self.ml_model = IsolationForest(contamination=0.05, random_state=42)
        self.scaler = StandardScaler()
        self.is_monitoring = False
        
        # Critical AWS service endpoints to monitor
        self.critical_endpoints = {
            'dynamodb': [
                'dynamodb.{region}.amazonaws.com',
                'streams.dynamodb.{region}.amazonaws.com'
            ],
            'rds': [
                'rds.{region}.amazonaws.com'
            ],
            'ec2': [
                'ec2.{region}.amazonaws.com'
            ],
            'elbv2': [
                'elasticloadbalancing.{region}.amazonaws.com'
            ],
            'lambda': [
                'lambda.{region}.amazonaws.com'
            ],
            's3': [
                's3.{region}.amazonaws.com',
                's3-{region}.amazonaws.com'
            ]
        }
        
        # Service dependency mapping for cascade analysis
        self.service_dependencies = {
            'dynamodb': ['lambda', 'ecs', 'ec2', 'rds'],
            'rds': ['lambda', 'ecs', 'ec2'],
            'lambda': ['dynamodb', 'rds', 's3'],
            'ecs': ['dynamodb', 'rds', 'elbv2'],
            'ec2': ['dynamodb', 'rds'],
            'elbv2': ['ec2', 'ecs']
        }
        
    def _initialize_clients(self) -> Dict[str, Dict[str, Any]]:
        """Initialize AWS clients for all regions"""
        clients = {}
        
        for region in self.regions:
            clients[region] = {
                'cloudwatch': boto3.client('cloudwatch', region_name=region),
                'ec2': boto3.client('ec2', region_name=region),
                'elbv2': boto3.client('elbv2', region_name=region),
                'rds': boto3.client('rds', region_name=region),
                'ecs': boto3.client('ecs', region_name=region),
                'lambda': boto3.client('lambda', region_name=region),
                'health': boto3.client('health', region_name='us-east-1'),  # Health API only in us-east-1
                'support': boto3.client('support', region_name='us-east-1')  # Support API only in us-east-1
            }
            
        return clients
    
    def perform_dns_health_checks(self, region: str) -> List[DNSHealthCheck]:
        """Perform comprehensive DNS health checks for critical AWS endpoints"""
        health_checks = []
        
        try:
            for service, endpoint_templates in self.critical_endpoints.items():
                for template in endpoint_templates:
                    endpoint = template.format(region=region)
                    
                    health_check = self._check_dns_endpoint(endpoint, region, service)
                    health_checks.append(health_check)
                    
                    # Also check if endpoint is reachable via HTTP/HTTPS
                    connectivity_check = self._check_endpoint_connectivity(endpoint, region, service)
                    if connectivity_check:
                        health_checks.append(connectivity_check)
            
            # Store health check results
            self.dns_health_checks.extend(health_checks)
            
            # Keep only last 1000 checks to prevent memory issues
            if len(self.dns_health_checks) > 1000:
                self.dns_health_checks = self.dns_health_checks[-1000:]
                
        except Exception as e:
            logger.error(f"Error performing DNS health checks for region {region}: {str(e)}")
            
        return health_checks
    
    def _check_dns_endpoint(self, endpoint: str, region: str, service: str) -> DNSHealthCheck:
        """Check DNS resolution for a specific endpoint"""
        start_time = time.time()
        
        try:
            # Perform DNS resolution
            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 10
            
            answers = resolver.resolve(endpoint, 'A')
            resolved_ips = [str(answer) for answer in answers]
            
            response_time = time.time() - start_time
            
            return DNSHealthCheck(
                endpoint=endpoint,
                region=region,
                service=service,
                resolution_success=True,
                resolved_ips=resolved_ips,
                response_time=response_time,
                timestamp=datetime.utcnow(),
                error_message=None
            )
            
        except dns.exception.DNSException as e:
            response_time = time.time() - start_time
            
            return DNSHealthCheck(
                endpoint=endpoint,
                region=region,
                service=service,
                resolution_success=False,
                resolved_ips=[],
                response_time=response_time,
                timestamp=datetime.utcnow(),
                error_message=str(e)
            )
        except Exception as e:
            response_time = time.time() - start_time
            
            return DNSHealthCheck(
                endpoint=endpoint,
                region=region,
                service=service,
                resolution_success=False,
                resolved_ips=[],
                response_time=response_time,
                timestamp=datetime.utcnow(),
                error_message=f"Unexpected error: {str(e)}"
            )
    
    def _check_endpoint_connectivity(self, endpoint: str, region: str, service: str) -> Optional[DNSHealthCheck]:
        """Check if endpoint is reachable via TCP connection"""
        try:
            # Try to establish TCP connection on port 443 (HTTPS)
            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            
            result = sock.connect_ex((endpoint, 443))
            sock.close()
            
            response_time = time.time() - start_time
            
            if result == 0:
                return DNSHealthCheck(
                    endpoint=f"{endpoint}:443",
                    region=region,
                    service=service,
                    resolution_success=True,
                    resolved_ips=[],
                    response_time=response_time,
                    timestamp=datetime.utcnow(),
                    error_message=None
                )
            else:
                return DNSHealthCheck(
                    endpoint=f"{endpoint}:443",
                    region=region,
                    service=service,
                    resolution_success=False,
                    resolved_ips=[],
                    response_time=response_time,
                    timestamp=datetime.utcnow(),
                    error_message=f"Connection failed: {result}"
                )
                
        except Exception as e:
            return DNSHealthCheck(
                endpoint=f"{endpoint}:443",
                region=region,
                service=service,
                resolution_success=False,
                resolved_ips=[],
                response_time=float('inf'),
                timestamp=datetime.utcnow(),
                error_message=str(e)
            )
    
    def _get_ec2_metrics(self, cw_client, region: str) -> List[HealthMetric]:
        """Get EC2 health metrics"""
        metrics = []
        
        try:
            # Get EC2 instances
            ec2_client = self.clients[region]['ec2']
            instances = ec2_client.describe_instances()
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    
                    # CPU Utilization
                    cpu_data = cw_client.get_metric_statistics(
                        Namespace='AWS/EC2',
                        MetricName='CPUUtilization',
                        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                        StartTime=datetime.utcnow() - timedelta(minutes=10),
                        EndTime=datetime.utcnow(),
                        Period=300,
                        Statistics=['Average']
                    )
                    
                    if cpu_data['Datapoints']:
                        cpu_value = cpu_data['Datapoints'][-1]['Average']
                        status = 'critical' if cpu_value > 90 else 'warning' if cpu_value > 75 else 'healthy'
                        
                        metrics.append(HealthMetric(
                            service='EC2',
                            region=region,
                            metric_name=f'CPUUtilization-{instance_id}',
                            value=cpu_value,
                            timestamp=datetime.utcnow(),
                            threshold=75.0,
                            status=status
                        ))
                        
        except Exception as e:
            logger.error(f"Error getting EC2 metrics: {str(e)}")
            
        return metrics
    
    def _get_elb_metrics(self, cw_client, region: str) -> List[HealthMetric]:
        """Get ELB health metrics"""
        metrics = []
        
        try:
            elb_client = self.clients[region]['elbv2']
            load_balancers = elb_client.describe_load_balancers()
            
            for lb in load_balancers['LoadBalancers']:
                lb_name = lb['LoadBalancerName']
                
                # Target Response Time
                response_time_data = cw_client.get_metric_statistics(
                    Namespace='AWS/ApplicationELB',
                    MetricName='TargetResponseTime',
                    Dimensions=[{'Name': 'LoadBalancer', 'Value': lb_name}],
                    StartTime=datetime.utcnow() - timedelta(minutes=10),
                    EndTime=datetime.utcnow(),
                    Period=300,
                    Statistics=['Average']
                )
                
                if response_time_data['Datapoints']:
                    response_time = response_time_data['Datapoints'][-1]['Average']
                    status = 'critical' if response_time > 5 else 'warning' if response_time > 2 else 'healthy'
                    
                    metrics.append(HealthMetric(
                        service='ELB',
                        region=region,
                        metric_name=f'TargetResponseTime-{lb_name}',
                        value=response_time,
                        timestamp=datetime.utcnow(),
                        threshold=2.0,
                        status=status
                    ))
                    
        except Exception as e:
            logger.error(f"Error getting ELB metrics: {str(e)}")
            
        return metrics
    
    def _get_rds_metrics(self, cw_client, region: str) -> List[HealthMetric]:
        """Get RDS health metrics"""
        metrics = []
        
        try:
            rds_client = self.clients[region]['rds']
            db_instances = rds_client.describe_db_instances()
            
            for db in db_instances['DBInstances']:
                db_id = db['DBInstanceIdentifier']
                
                # CPU Utilization
                cpu_data = cw_client.get_metric_statistics(
                    Namespace='AWS/RDS',
                    MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                    StartTime=datetime.utcnow() - timedelta(minutes=10),
                    EndTime=datetime.utcnow(),
                    Period=300,
                    Statistics=['Average']
                )
                
                if cpu_data['Datapoints']:
                    cpu_value = cpu_data['Datapoints'][-1]['Average']
                    status = 'critical' if cpu_value > 80 else 'warning' if cpu_value > 60 else 'healthy'
                    
                    metrics.append(HealthMetric(
                        service='RDS',
                        region=region,
                        metric_name=f'CPUUtilization-{db_id}',
                        value=cpu_value,
                        timestamp=datetime.utcnow(),
                        threshold=60.0,
                        status=status
                    ))
                    
        except Exception as e:
            logger.error(f"Error getting RDS metrics: {str(e)}")
            
        return metrics
    
    def _get_ecs_metrics(self, cw_client, region: str) -> List[HealthMetric]:
        """Get ECS health metrics"""
        metrics = []
        
        try:
            ecs_client = self.clients[region]['ecs']
            clusters = ecs_client.list_clusters()
            
            for cluster_arn in clusters['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                
                # CPU Utilization
                cpu_data = cw_client.get_metric_statistics(
                    Namespace='AWS/ECS',
                    MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'ClusterName', 'Value': cluster_name}],
                    StartTime=datetime.utcnow() - timedelta(minutes=10),
                    EndTime=datetime.utcnow(),
                    Period=300,
                    Statistics=['Average']
                )
                
                if cpu_data['Datapoints']:
                    cpu_value = cpu_data['Datapoints'][-1]['Average']
                    status = 'critical' if cpu_value > 85 else 'warning' if cpu_value > 70 else 'healthy'
                    
                    metrics.append(HealthMetric(
                        service='ECS',
                        region=region,
                        metric_name=f'CPUUtilization-{cluster_name}',
                        value=cpu_value,
                        timestamp=datetime.utcnow(),
                        threshold=70.0,
                        status=status
                    ))
                    
        except Exception as e:
            logger.error(f"Error getting ECS metrics: {str(e)}")
            
        return metrics
    
    def _get_lambda_metrics(self, cw_client, region: str) -> List[HealthMetric]:
        """Get Lambda health metrics"""
        metrics = []
        
        try:
            lambda_client = self.clients[region]['lambda']
            functions = lambda_client.list_functions()
            
            for function in functions['Functions']:
                function_name = function['FunctionName']
                
                # Error Rate
                error_data = cw_client.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Errors',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=datetime.utcnow() - timedelta(minutes=10),
                    EndTime=datetime.utcnow(),
                    Period=300,
                    Statistics=['Sum']
                )
                
                if error_data['Datapoints']:
                    error_count = error_data['Datapoints'][-1]['Sum']
                    status = 'critical' if error_count > 10 else 'warning' if error_count > 5 else 'healthy'
                    
                    metrics.append(HealthMetric(
                        service='Lambda',
                        region=region,
                        metric_name=f'Errors-{function_name}',
                        value=error_count,
                        timestamp=datetime.utcnow(),
                        threshold=5.0,
                        status=status
                    ))
                    
        except Exception as e:
            logger.error(f"Error getting Lambda metrics: {str(e)}")
            
        return metrics
    
    def _get_health_dashboard_metrics(self, region: str) -> List[HealthMetric]:
        """Get AWS Health Dashboard metrics"""
        metrics = []
        
        try:
            health_client = self.clients[region]['health']
            
            # Get current health events
            events = health_client.describe_events(
                filter={
                    'regions': [region],
                    'eventStatusCodes': ['open', 'upcoming']
                }
            )
            
            for event in events['events']:
                severity_score = self._calculate_health_severity(event)
                status = 'critical' if severity_score > 8 else 'warning' if severity_score > 5 else 'healthy'
                
                metrics.append(HealthMetric(
                    service='AWS-Health',
                    region=region,
                    metric_name=f"HealthEvent-{event['eventTypeCode']}",
                    value=severity_score,
                    timestamp=datetime.utcnow(),
                    threshold=5.0,
                    status=status
                ))
                
        except Exception as e:
            logger.error(f"Error getting Health Dashboard metrics: {str(e)}")
            
        return metrics
    
    def _calculate_health_severity(self, event: Dict) -> float:
        """Calculate severity score for health events"""
        severity_map = {
            'high': 10,
            'medium': 6,
            'low': 3,
            'informational': 1
        }
        
        event_type_severity = {
            'AWS_EC2_OPERATIONAL_ISSUE': 9,
            'AWS_RDS_OPERATIONAL_ISSUE': 8,
            'AWS_ELB_OPERATIONAL_ISSUE': 8,
            'AWS_LAMBDA_OPERATIONAL_ISSUE': 7
        }
        
        base_severity = severity_map.get(event.get('eventScopeCode', 'low'), 3)
        type_severity = event_type_severity.get(event.get('eventTypeCode', ''), 5)
        
        return (base_severity + type_severity) / 2
    
    def analyze_dns_failures(self, health_checks: List[DNSHealthCheck]) -> List[OutageAlert]:
        """Analyze DNS health checks for potential failures and cascade risks"""
        alerts = []
        
        try:
            # Group health checks by service and region
            service_checks = {}
            for check in health_checks:
                key = f"{check.service}-{check.region}"
                if key not in service_checks:
                    service_checks[key] = []
                service_checks[key].append(check)
            
            # Analyze each service
            for service_key, checks in service_checks.items():
                service, region = service_key.split('-', 1)
                
                # Check for DNS resolution failures
                failed_checks = [c for c in checks if not c.resolution_success]
                total_checks = len(checks)
                
                if failed_checks:
                    failure_rate = len(failed_checks) / total_checks
                    
                    # Critical: Any DNS failure for DynamoDB (like the AWS outage)
                    if service == 'dynamodb' and failure_rate > 0:
                        alert = OutageAlert(
                            alert_id=f"dns-failure-{service}-{region}-{int(time.time())}",
                            severity='critical',
                            alert_type='dns_failure',
                            service=service,
                            region=region,
                            affected_endpoints=[c.endpoint for c in failed_checks],
                            message=f"CRITICAL: DynamoDB DNS resolution failure in {region} - Potential cascade outage risk",
                            timestamp=datetime.utcnow(),
                            predicted_impact="High - Potential cascade failure affecting multiple AWS services",
                            recommended_actions=[
                                "Immediately verify DNS records for DynamoDB endpoints",
                                "Check internal DNS management system for conflicts",
                                "Prepare for multi-region failover",
                                "Alert all dependent services",
                                "Monitor cascade impact on Lambda, ECS, EC2"
                            ]
                        )
                        alerts.append(alert)
                    
                    # High severity for other critical services
                    elif failure_rate >= 0.5:
                        severity = 'critical' if failure_rate >= 0.8 else 'high'
                        
                        alert = OutageAlert(
                            alert_id=f"dns-failure-{service}-{region}-{int(time.time())}",
                            severity=severity,
                            alert_type='dns_failure',
                            service=service,
                            region=region,
                            affected_endpoints=[c.endpoint for c in failed_checks],
                            message=f"DNS resolution failure for {service} in {region} ({failure_rate:.1%} failure rate)",
                            timestamp=datetime.utcnow(),
                            predicted_impact=self._predict_dns_failure_impact(service, failure_rate),
                            recommended_actions=self._get_dns_failure_actions(service, failure_rate)
                        )
                        alerts.append(alert)
                
                # Check for cascade risks
                cascade_risk = self._assess_cascade_risk(service, region, failed_checks)
                if cascade_risk.risk_score > 0.7:
                    alert = OutageAlert(
                        alert_id=f"cascade-risk-{service}-{region}-{int(time.time())}",
                        severity='high',
                        alert_type='cascade_risk',
                        service=service,
                        region=region,
                        affected_endpoints=[],
                        message=f"High cascade failure risk detected for {service} in {region}",
                        timestamp=datetime.utcnow(),
                        predicted_impact=cascade_risk.potential_impact,
                        recommended_actions=cascade_risk.mitigation_actions
                    )
                    alerts.append(alert)
            
            # Use ML for pattern detection in DNS failures
            if len(health_checks) >= 20:
                ml_alerts = self._ml_analyze_dns_patterns(health_checks)
                alerts.extend(ml_alerts)
                
        except Exception as e:
            logger.error(f"Error analyzing DNS failures: {str(e)}")
            
        return alerts
    
    def _assess_cascade_risk(self, service: str, region: str, failed_checks: List[DNSHealthCheck]) -> CascadeRisk:
        """Assess cascade failure risk for a service"""
        try:
            dependent_services = self.service_dependencies.get(service, [])
            
            # Calculate risk score based on:
            # 1. Number of failed endpoints
            # 2. Number of dependent services
            # 3. Service criticality
            
            failure_score = len(failed_checks) * 0.3
            dependency_score = len(dependent_services) * 0.4
            criticality_score = 0.8 if service == 'dynamodb' else 0.5
            
            risk_score = min(1.0, failure_score + dependency_score + criticality_score)
            
            # Determine potential impact
            if risk_score > 0.8:
                impact = "Critical - Multi-service cascade failure likely"
            elif risk_score > 0.6:
                impact = "High - Significant service disruption expected"
            elif risk_score > 0.4:
                impact = "Medium - Limited service impact"
            else:
                impact = "Low - Minimal cascade risk"
            
            # Generate mitigation actions
            actions = [
                f"Monitor dependent services: {', '.join(dependent_services)}",
                "Prepare failover procedures",
                "Scale up healthy regions",
                "Implement circuit breakers"
            ]
            
            if service == 'dynamodb':
                actions.extend([
                    "Verify DynamoDB DNS records immediately",
                    "Check internal DNS management system",
                    "Prepare for region-wide service impact"
                ])
            
            return CascadeRisk(
                service=service,
                region=region,
                dependency_services=dependent_services,
                risk_score=risk_score,
                potential_impact=impact,
                mitigation_actions=actions
            )
            
        except Exception as e:
            logger.error(f"Error assessing cascade risk: {str(e)}")
            return CascadeRisk(service, region, [], 0.0, "Unknown", [])
    
    def _ml_analyze_dns_patterns(self, health_checks: List[DNSHealthCheck]) -> List[OutageAlert]:
        """Use ML to detect patterns in DNS failures"""
        alerts = []
        
        try:
            # Prepare data for ML analysis
            df = pd.DataFrame([
                {
                    'service': check.service,
                    'region': check.region,
                    'success': 1 if check.resolution_success else 0,
                    'response_time': check.response_time,
                    'timestamp': check.timestamp.timestamp(),
                    'hour': check.timestamp.hour
                }
                for check in health_checks
            ])
            
            # Feature engineering
            features = df[['success', 'response_time', 'hour']].values
            
            if len(features) >= 10:
                features_scaled = self.scaler.fit_transform(features)
                anomalies = self.ml_model.fit_predict(features_scaled)
                
                # Generate alerts for detected anomalies
                anomaly_indices = [i for i, a in enumerate(anomalies) if a == -1]
                
                if len(anomaly_indices) > len(features) * 0.1:  # More than 10% anomalies
                    alert = OutageAlert(
                        alert_id=f"ml-dns-pattern-{int(time.time())}",
                        severity='high',
                        alert_type='dns_failure',
                        service='multiple',
                        region='multiple',
                        affected_endpoints=[],
                        message="ML detected unusual DNS failure patterns across services",
                        timestamp=datetime.utcnow(),
                        predicted_impact="High - Systematic DNS issues detected",
                        recommended_actions=[
                            "Investigate DNS infrastructure",
                            "Check for systematic DNS management issues",
                            "Review recent DNS configuration changes",
                            "Prepare for potential widespread impact"
                        ]
                    )
                    alerts.append(alert)
                    
        except Exception as e:
            logger.error(f"Error in ML DNS pattern analysis: {str(e)}")
            
        return alerts
    
    def _predict_impact(self, service: str, metric_value: float) -> str:
        """Predict the impact of detected anomalies"""
        impact_map = {
            'EC2': {
                90: 'High - Potential instance failure',
                75: 'Medium - Performance degradation',
                50: 'Low - Minor impact'
            },
            'ELB': {
                5: 'High - Service unavailability',
                2: 'Medium - Slow response times',
                1: 'Low - Minor delays'
            },
            'RDS': {
                80: 'High - Database performance issues',
                60: 'Medium - Query slowdowns',
                40: 'Low - Minor impact'
            }
        }
        
        service_thresholds = impact_map.get(service, {})
        
        for threshold in sorted(service_thresholds.keys(), reverse=True):
            if metric_value >= threshold:
                return service_thresholds[threshold]
                
        return 'Low - Minimal impact expected'
    
    def _get_recommended_actions(self, service: str, metric_value: float) -> List[str]:
        """Get recommended actions based on service and metric value"""
        actions = {
            'EC2': [
                'Scale out EC2 instances',
                'Check for resource-intensive processes',
                'Consider upgrading instance types',
                'Enable auto-scaling if not already configured'
            ],
            'ELB': [
                'Check target health',
                'Scale backend services',
                'Review load balancer configuration',
                'Consider adding more availability zones'
            ],
            'RDS': [
                'Check for long-running queries',
                'Consider read replicas',
                'Review database configuration',
                'Monitor connection pool usage'
            ],
            'Lambda': [
                'Check function timeout settings',
                'Review memory allocation',
                'Monitor concurrent executions',
                'Check for cold start issues'
            ]
        }
        
        return actions.get(service, ['Monitor closely', 'Review service configuration'])
    
    def trigger_automated_response(self, alert: OutageAlert):
        """Trigger automated responses to prevent DNS-related outages"""
        try:
            logger.info(f"Triggering automated response for alert: {alert.alert_id}")
            
            if alert.alert_type == 'dns_failure':
                if alert.service == 'dynamodb':
                    # Critical DynamoDB DNS failure - immediate action required
                    self._handle_dynamodb_dns_failure(alert)
                else:
                    # Other service DNS failures
                    self._handle_service_dns_failure(alert)
                    
            elif alert.alert_type == 'cascade_risk':
                # Prevent cascade failures
                self._prevent_cascade_failure(alert)
                
            # Send notifications
            self._send_alert_notification(alert)
            
        except Exception as e:
            logger.error(f"Error in automated response: {str(e)}")
    
    def _handle_dynamodb_dns_failure(self, alert: OutageAlert):
        """Handle critical DynamoDB DNS failures"""
        try:
            logger.critical(f"CRITICAL: DynamoDB DNS failure detected in {alert.region}")
            
            # 1. Verify DNS records
            self._verify_dns_records(alert.region, 'dynamodb')
            
            # 2. Initiate multi-region failover preparation
            self._prepare_region_failover(alert.region)
            
            # 3. Scale up other regions
            for region in self.regions:
                if region != alert.region:
                    self._scale_up_region_services(region)
            
            # 4. Alert dependent services
            self._alert_dependent_services('dynamodb', alert.region)
            
        except Exception as e:
            logger.error(f"Error handling DynamoDB DNS failure: {str(e)}")
    
    def _handle_service_dns_failure(self, alert: OutageAlert):
        """Handle DNS failures for other services"""
        try:
            logger.warning(f"DNS failure for {alert.service} in {alert.region}")
            
            # 1. Verify DNS records
            self._verify_dns_records(alert.region, alert.service)
            
            # 2. Check service health via alternative methods
            self._check_service_health_alternative(alert.region, alert.service)
            
            # 3. Scale up if needed
            if alert.severity in ['critical', 'high']:
                self._scale_up_service(alert.region, alert.service)
                
        except Exception as e:
            logger.error(f"Error handling service DNS failure: {str(e)}")
    
    def _prevent_cascade_failure(self, alert: OutageAlert):
        """Prevent cascade failures"""
        try:
            logger.warning(f"Preventing cascade failure for {alert.service} in {alert.region}")
            
            # 1. Implement circuit breakers
            self._implement_circuit_breakers(alert.service, alert.region)
            
            # 2. Scale up dependent services
            dependent_services = self.service_dependencies.get(alert.service, [])
            for dep_service in dependent_services:
                self._scale_up_service(alert.region, dep_service)
            
            # 3. Prepare failover for critical dependencies
            if alert.service == 'dynamodb':
                self._prepare_dynamodb_failover(alert.region)
                
        except Exception as e:
            logger.error(f"Error preventing cascade failure: {str(e)}")
    
    def _verify_dns_records(self, region: str, service: str):
        """Verify DNS records for a service"""
        try:
            # This would integrate with Route 53 to verify DNS records
            logger.info(f"Verifying DNS records for {service} in {region}")
            
            route53_client = self.clients[region]['route53']
            
            # Get hosted zones and check records
            # Implementation would depend on specific DNS setup
            
        except Exception as e:
            logger.error(f"Error verifying DNS records: {str(e)}")
    
    def _prepare_region_failover(self, failed_region: str):
        """Prepare for region failover"""
        try:
            logger.info(f"Preparing failover from region {failed_region}")
            
            # This would integrate with the multi-region failover system
            # Implementation depends on specific failover requirements
            
        except Exception as e:
            logger.error(f"Error preparing region failover: {str(e)}")
    
    def _scale_up_region_services(self, region: str):
        """Scale up services in a region"""
        try:
            logger.info(f"Scaling up services in region {region}")
            
            # Scale Auto Scaling Groups
            autoscaling_client = self.clients[region]['autoscaling']
            asgs = autoscaling_client.describe_auto_scaling_groups()
            
            for asg in asgs['AutoScalingGroups']:
                current_capacity = asg['DesiredCapacity']
                new_capacity = min(current_capacity + 2, asg['MaxSize'])
                
                if new_capacity > current_capacity:
                    autoscaling_client.update_auto_scaling_group(
                        AutoScalingGroupName=asg['AutoScalingGroupName'],
                        DesiredCapacity=new_capacity
                    )
                    logger.info(f"Scaled ASG {asg['AutoScalingGroupName']} to {new_capacity}")
            
        except Exception as e:
            logger.error(f"Error scaling up region services: {str(e)}")
    
    def _alert_dependent_services(self, service: str, region: str):
        """Alert services that depend on the failed service"""
        try:
            dependent_services = self.service_dependencies.get(service, [])
            logger.info(f"Alerting dependent services of {service}: {dependent_services}")
            
            # This would send alerts to monitoring systems for dependent services
            
        except Exception as e:
            logger.error(f"Error alerting dependent services: {str(e)}")
    
    def _check_service_health_alternative(self, region: str, service: str):
        """Check service health using alternative methods when DNS fails"""
        try:
            # Use CloudWatch metrics instead of DNS resolution
            cloudwatch = self.clients[region]['cloudwatch']
            
            # Get recent metrics for the service
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=10)
            
            # Service-specific health checks
            if service == 'dynamodb':
                metrics = cloudwatch.get_metric_statistics(
                    Namespace='AWS/DynamoDB',
                    MetricName='SuccessfulRequestLatency',
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,
                    Statistics=['Average']
                )
                
                if metrics['Datapoints']:
                    logger.info(f"DynamoDB alternative health check: {len(metrics['Datapoints'])} datapoints")
                else:
                    logger.warning(f"No DynamoDB metrics available - service may be down")
            
        except Exception as e:
            logger.error(f"Error in alternative health check: {str(e)}")
    
    def _scale_up_service(self, region: str, service: str):
        """Scale up a specific service"""
        try:
            logger.info(f"Scaling up {service} in {region}")
            
            # Service-specific scaling logic would go here
            # This is a placeholder for actual scaling implementation
            
        except Exception as e:
            logger.error(f"Error scaling up service: {str(e)}")
    
    def _implement_circuit_breakers(self, service: str, region: str):
        """Implement circuit breakers to prevent cascade failures"""
        try:
            logger.info(f"Implementing circuit breakers for {service} in {region}")
            
            # This would implement circuit breaker patterns
            # Placeholder for actual implementation
            
        except Exception as e:
            logger.error(f"Error implementing circuit breakers: {str(e)}")
    
    def _prepare_dynamodb_failover(self, region: str):
        """Prepare DynamoDB failover procedures"""
        try:
            logger.info(f"Preparing DynamoDB failover from {region}")
            
            # This would prepare DynamoDB global tables failover
            # Placeholder for actual implementation
            
        except Exception as e:
            logger.error(f"Error preparing DynamoDB failover: {str(e)}")
    
    def _predict_dns_failure_impact(self, service: str, failure_rate: float) -> str:
        """Predict impact of DNS failures"""
        if service == 'dynamodb':
            if failure_rate > 0.5:
                return "Critical - Potential region-wide cascade failure affecting Lambda, ECS, EC2"
            else:
                return "High - DynamoDB-dependent services at risk"
        elif service in ['rds', 'lambda']:
            if failure_rate > 0.8:
                return "High - Service unavailability likely"
            else:
                return "Medium - Degraded service performance"
        else:
            return "Medium - Service disruption expected"
    
    def _get_dns_failure_actions(self, service: str, failure_rate: float) -> List[str]:
        """Get recommended actions for DNS failures"""
        actions = [
            "Verify DNS records immediately",
            "Check DNS management system for conflicts",
            "Monitor service health via alternative methods"
        ]
        
        if service == 'dynamodb':
            actions.extend([
                "Prepare for cascade failure prevention",
                "Alert all DynamoDB-dependent services",
                "Consider region failover if failure persists"
            ])
        
        if failure_rate > 0.8:
            actions.extend([
                "Initiate emergency response procedures",
                "Scale up alternative regions",
                "Implement traffic routing changes"
            ])
        
        return actions
    
    def _scale_ec2_instances(self, region: str):
        """Automatically scale EC2 instances"""
        try:
            # This would integrate with Auto Scaling Groups
            logger.info(f"Scaling EC2 instances in region {region}")
            # Implementation would depend on specific ASG configuration
            
        except Exception as e:
            logger.error(f"Error scaling EC2 instances: {str(e)}")
    
    def _check_target_health(self, region: str):
        """Check and fix ELB target health"""
        try:
            elb_client = self.clients[region]['elbv2']
            target_groups = elb_client.describe_target_groups()
            
            for tg in target_groups['TargetGroups']:
                health = elb_client.describe_target_health(
                    TargetGroupArn=tg['TargetGroupArn']
                )
                
                unhealthy_targets = [
                    target for target in health['TargetHealthDescriptions']
                    if target['TargetHealth']['State'] != 'healthy'
                ]
                
                if unhealthy_targets:
                    logger.warning(f"Found {len(unhealthy_targets)} unhealthy targets in {region}")
                    # Could trigger instance replacement or health checks
                    
        except Exception as e:
            logger.error(f"Error checking target health: {str(e)}")
    
    def _optimize_rds_performance(self, region: str):
        """Optimize RDS performance"""
        try:
            # This could trigger performance insights analysis
            logger.info(f"Optimizing RDS performance in region {region}")
            # Implementation would analyze slow queries and suggest optimizations
            
        except Exception as e:
            logger.error(f"Error optimizing RDS performance: {str(e)}")
    
    def _send_alert_notification(self, alert: OutageAlert):
        """Send alert notifications"""
        try:
            # This would integrate with SNS, Slack, PagerDuty, etc.
            logger.info(f"Sending notification for alert: {alert.alert_id}")
            
            # Example: Send to CloudWatch Logs for now
            log_message = {
                'alert_id': alert.alert_id,
                'severity': alert.severity,
                'service': alert.service,
                'region': alert.region,
                'message': alert.message,
                'timestamp': alert.timestamp.isoformat(),
                'predicted_impact': alert.predicted_impact,
                'recommended_actions': alert.recommended_actions
            }
            
            logger.info(f"OUTAGE ALERT: {json.dumps(log_message, indent=2)}")
            
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
    
    def start_monitoring(self):
        """Start continuous DNS monitoring to prevent outages"""
        self.is_monitoring = True
        logger.info("Starting DNS outage prevention monitoring...")
        
        def monitor_loop():
            while self.is_monitoring:
                try:
                    all_health_checks = []
                    
                    # Perform DNS health checks for all regions
                    for region in self.regions:
                        region_checks = self.perform_dns_health_checks(region)
                        all_health_checks.extend(region_checks)
                        
                        # Log DNS health status
                        failed_checks = [c for c in region_checks if not c.resolution_success]
                        if failed_checks:
                            logger.warning(f"DNS failures in {region}: {len(failed_checks)} endpoints failed")
                            for check in failed_checks:
                                logger.warning(f"  - {check.endpoint}: {check.error_message}")
                    
                    # Analyze DNS failures and cascade risks
                    alerts = self.analyze_dns_failures(all_health_checks)
                    
                    # Process alerts
                    for alert in alerts:
                        self.alerts.append(alert)
                        self.trigger_automated_response(alert)
                    
                    # Publish custom metrics
                    self._publish_dns_metrics(all_health_checks)
                    
                    # Log current status
                    total_checks = len(all_health_checks)
                    failed_checks = [c for c in all_health_checks if not c.resolution_success]
                    success_rate = (total_checks - len(failed_checks)) / total_checks if total_checks > 0 else 1.0
                    
                    logger.info(f"DNS monitoring cycle complete - Success rate: {success_rate:.2%} "
                              f"({total_checks - len(failed_checks)}/{total_checks}), Alerts: {len(alerts)}")
                    
                    # Wait before next cycle - more frequent for DNS monitoring
                    time.sleep(30)  # Monitor every 30 seconds for DNS
                    
                except Exception as e:
                    logger.error(f"Error in DNS monitoring loop: {str(e)}")
                    time.sleep(15)  # Wait 15 seconds on error
        
        # Start monitoring in background thread
        monitor_thread = threading.Thread(target=monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        logger.info("Stopping AWS resilience monitoring...")
    
    def _publish_dns_metrics(self, health_checks: List[DNSHealthCheck]):
        """Publish DNS health metrics to CloudWatch"""
        try:
            for region in self.regions:
                cloudwatch = self.clients[region]['cloudwatch']
                
                # Calculate DNS success rate by service
                region_checks = [c for c in health_checks if c.region == region]
                
                for service in self.critical_endpoints.keys():
                    service_checks = [c for c in region_checks if c.service == service]
                    
                    if service_checks:
                        successful_checks = [c for c in service_checks if c.resolution_success]
                        success_rate = len(successful_checks) / len(service_checks)
                        
                        # Average response time
                        avg_response_time = sum(c.response_time for c in successful_checks) / len(successful_checks) if successful_checks else 0
                        
                        # Publish metrics
                        cloudwatch.put_metric_data(
                            Namespace='Custom/DNSOutagePrevention',
                            MetricData=[
                                {
                                    'MetricName': 'DNSSuccessRate',
                                    'Dimensions': [
                                        {'Name': 'Service', 'Value': service},
                                        {'Name': 'Region', 'Value': region}
                                    ],
                                    'Value': success_rate,
                                    'Unit': 'Percent',
                                    'Timestamp': datetime.utcnow()
                                },
                                {
                                    'MetricName': 'DNSResponseTime',
                                    'Dimensions': [
                                        {'Name': 'Service', 'Value': service},
                                        {'Name': 'Region', 'Value': region}
                                    ],
                                    'Value': avg_response_time,
                                    'Unit': 'Seconds',
                                    'Timestamp': datetime.utcnow()
                                }
                            ]
                        )
                
                # Overall DNS health score
                total_checks = len(region_checks)
                successful_checks = [c for c in region_checks if c.resolution_success]
                overall_success_rate = len(successful_checks) / total_checks if total_checks > 0 else 1.0
                
                cloudwatch.put_metric_data(
                    Namespace='Custom/DNSOutagePrevention',
                    MetricData=[
                        {
                            'MetricName': 'OverallDNSHealth',
                            'Dimensions': [
                                {'Name': 'Region', 'Value': region}
                            ],
                            'Value': overall_success_rate,
                            'Unit': 'Percent',
                            'Timestamp': datetime.utcnow()
                        }
                    ]
                )
                
        except Exception as e:
            logger.error(f"Error publishing DNS metrics: {str(e)}")
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current DNS monitoring status"""
        recent_checks = [
            c for c in self.dns_health_checks 
            if c.timestamp > datetime.utcnow() - timedelta(minutes=5)
        ]
        
        recent_alerts = [
            a for a in self.alerts 
            if a.timestamp > datetime.utcnow() - timedelta(minutes=30)
        ]
        
        # Calculate DNS health by service
        dns_health_by_service = {}
        for service in self.critical_endpoints.keys():
            service_checks = [c for c in recent_checks if c.service == service]
            if service_checks:
                successful = [c for c in service_checks if c.resolution_success]
                dns_health_by_service[service] = len(successful) / len(service_checks)
            else:
                dns_health_by_service[service] = 1.0
        
        status = {
            'timestamp': datetime.utcnow().isoformat(),
            'monitoring_active': self.is_monitoring,
            'regions_monitored': self.regions,
            'recent_dns_checks': len(recent_checks),
            'recent_alerts_count': len(recent_alerts),
            'dns_health_by_service': dns_health_by_service,
            'critical_alerts': [
                a for a in recent_alerts if a.severity == 'critical'
            ],
            'dns_failure_alerts': [
                a for a in recent_alerts if a.alert_type == 'dns_failure'
            ],
            'cascade_risk_alerts': [
                a for a in recent_alerts if a.alert_type == 'cascade_risk'
            ],
            'latest_alerts': [
                {
                    'alert_id': a.alert_id,
                    'severity': a.severity,
                    'alert_type': a.alert_type,
                    'service': a.service,
                    'region': a.region,
                    'message': a.message,
                    'affected_endpoints': a.affected_endpoints,
                    'predicted_impact': a.predicted_impact
                }
                for a in recent_alerts[-5:]  # Last 5 alerts
            ]
        }
        
        return status

# Example usage and testing
if __name__ == "__main__":
    # Initialize the DNS outage prevention system
    dns_monitor = DNSOutagePreventionSystem(regions=['us-east-1', 'us-west-2', 'eu-west-1'])
    
    # Start monitoring
    dns_monitor.start_monitoring()
    
    try:
        # Let it run for a while
        time.sleep(300)  # 5 minutes
        
        # Get status
        status = dns_monitor.get_current_status()
        print(json.dumps(status, indent=2))
        
    except KeyboardInterrupt:
        print("Stopping DNS monitoring...")
        dns_monitor.stop_monitoring()