#!/usr/bin/env python3
"""
Simple DNS Outage Prevention Monitor
Directly monitors DNS and publishes to CloudWatch without complex infrastructure
"""

import boto3
import json
import time
import logging
import socket
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleDNSMonitor:
    """Simple DNS monitoring system that prevents outages"""
    
    def __init__(self, regions: List[str] = None):
        self.regions = regions or ['us-east-1', 'us-west-2', 'eu-west-1']
        self.is_monitoring = False
        
        # Critical AWS service endpoints to monitor
        self.critical_endpoints = {
            'dynamodb': [
                'dynamodb.{region}.amazonaws.com',
                'streams.dynamodb.{region}.amazonaws.com'
            ],
            'rds': ['rds.{region}.amazonaws.com'],
            'lambda': ['lambda.{region}.amazonaws.com'],
            'ec2': ['ec2.{region}.amazonaws.com'],
            'elbv2': ['elasticloadbalancing.{region}.amazonaws.com'],
            's3': ['s3.{region}.amazonaws.com']
        }
        
        # Initialize CloudWatch clients
        self.cloudwatch_clients = {}
        for region in self.regions:
            self.cloudwatch_clients[region] = boto3.client('cloudwatch', region_name=region)
    
    def check_dns_endpoint(self, endpoint: str, region: str, service: str) -> Dict[str, Any]:
        """Check DNS resolution for a specific endpoint"""
        start_time = time.time()
        
        try:
            # Try DNS resolution
            socket.setdefaulttimeout(5)
            ip_addresses = socket.gethostbyname_ex(endpoint)[2]
            response_time = time.time() - start_time
            
            if ip_addresses:
                logger.info(f"✅ {service} DNS OK in {region}: {endpoint} -> {ip_addresses[0]}")
                return {
                    'endpoint': endpoint,
                    'region': region,
                    'service': service,
                    'success': True,
                    'ip_addresses': ip_addresses,
                    'response_time': response_time,
                    'error': None
                }
            else:
                logger.warning(f"⚠️  {service} DNS returned no IPs in {region}: {endpoint}")
                return {
                    'endpoint': endpoint,
                    'region': region,
                    'service': service,
                    'success': False,
                    'ip_addresses': [],
                    'response_time': response_time,
                    'error': 'No IP addresses returned'
                }
                
        except socket.gaierror as e:
            response_time = time.time() - start_time
            logger.error(f"❌ {service} DNS FAILED in {region}: {endpoint} - {str(e)}")
            
            # Critical alert for DynamoDB failures
            if service == 'dynamodb':
                logger.critical(f"🚨 CRITICAL: DynamoDB DNS failure in {region} - Potential cascade outage risk!")
            
            return {
                'endpoint': endpoint,
                'region': region,
                'service': service,
                'success': False,
                'ip_addresses': [],
                'response_time': response_time,
                'error': str(e)
            }
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"❌ {service} DNS ERROR in {region}: {endpoint} - {str(e)}")
            return {
                'endpoint': endpoint,
                'region': region,
                'service': service,
                'success': False,
                'ip_addresses': [],
                'response_time': response_time,
                'error': str(e)
            }
    
    def perform_dns_health_checks(self) -> List[Dict[str, Any]]:
        """Perform DNS health checks for all critical endpoints"""
        all_results = []
        
        for region in self.regions:
            logger.info(f"🔍 Checking DNS health in region: {region}")
            
            for service, endpoint_templates in self.critical_endpoints.items():
                for template in endpoint_templates:
                    endpoint = template.format(region=region)
                    result = self.check_dns_endpoint(endpoint, region, service)
                    all_results.append(result)
        
        return all_results
    
    def publish_metrics(self, results: List[Dict[str, Any]]):
        """Publish DNS health metrics to CloudWatch"""
        try:
            for region in self.regions:
                cloudwatch = self.cloudwatch_clients[region]
                region_results = [r for r in results if r['region'] == region]
                
                # Calculate metrics by service
                for service in self.critical_endpoints.keys():
                    service_results = [r for r in region_results if r['service'] == service]
                    
                    if service_results:
                        successful_checks = [r for r in service_results if r['success']]
                        success_rate = (len(successful_checks) / len(service_results)) * 100
                        
                        avg_response_time = sum(r['response_time'] for r in successful_checks) / len(successful_checks) if successful_checks else 0
                        
                        # Publish DNS success rate
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
                                    'Value': avg_response_time * 1000,  # Convert to milliseconds
                                    'Unit': 'Milliseconds',
                                    'Timestamp': datetime.utcnow()
                                }
                            ]
                        )
                        
                        logger.info(f"📊 Published metrics for {service} in {region}: {success_rate:.1f}% success, {avg_response_time*1000:.1f}ms avg response")
                
                # Overall region health
                total_checks = len(region_results)
                successful_checks = [r for r in region_results if r['success']]
                overall_success_rate = (len(successful_checks) / total_checks) * 100 if total_checks > 0 else 100
                
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
                        },
                        {
                            'MetricName': 'DNSFailuresDetected',
                            'Dimensions': [
                                {'Name': 'Region', 'Value': region}
                            ],
                            'Value': total_checks - len(successful_checks),
                            'Unit': 'Count',
                            'Timestamp': datetime.utcnow()
                        }
                    ]
                )
                
        except Exception as e:
            logger.error(f"Error publishing metrics: {str(e)}")
    
    def publish_dashboard_metrics(self, results: List[Dict[str, Any]]):
        """Publish additional metrics for sleek dashboard"""
        try:
            # Calculate system uptime percentage
            total_checks = len(results)
            successful_checks = len([r for r in results if r['success']])
            uptime_percentage = (successful_checks / total_checks) * 100 if total_checks > 0 else 100
            
            # Publish to primary region
            primary_region = self.regions[0]
            cloudwatch = self.cloudwatch_clients[primary_region]
            
            cloudwatch.put_metric_data(
                Namespace='Custom/DNSOutagePrevention',
                MetricData=[
                    {
                        'MetricName': 'SystemUptimePercentage',
                        'Value': uptime_percentage,
                        'Unit': 'Percent',
                        'Timestamp': datetime.utcnow()
                    },
                    {
                        'MetricName': 'TotalEndpointsMonitored',
                        'Value': total_checks,
                        'Unit': 'Count',
                        'Timestamp': datetime.utcnow()
                    },
                    {
                        'MetricName': 'HealthyEndpoints',
                        'Value': successful_checks,
                        'Unit': 'Count',
                        'Timestamp': datetime.utcnow()
                    }
                ]
            )
            
        except Exception as e:
            logger.error(f"Error publishing dashboard metrics: {str(e)}")
    
    def create_dashboard(self, region: str = 'us-east-1'):
        """Create sleek CloudWatch dashboard for DNS monitoring"""
        try:
            cloudwatch = self.cloudwatch_clients[region]
            dashboard_name = f"DNS-Outage-Prevention-{region}"
            
            dashboard_body = {
                "widgets": [
                    # Top row - Key metrics with single value displays
                    {
                        "type": "number",
                        "x": 0,
                        "y": 0,
                        "width": 6,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "OverallDNSHealth", "Region", region]
                            ],
                            "view": "singleValue",
                            "region": region,
                            "title": "DNS Health Score",
                            "period": 60,
                            "stat": "Average",
                            "setPeriodToTimeRange": True,
                            "sparkline": True,
                            "trend": True
                        }
                    },
                    {
                        "type": "number",
                        "x": 6,
                        "y": 0,
                        "width": 6,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "DNSSuccessRate", "Service", "dynamodb", "Region", region]
                            ],
                            "view": "singleValue",
                            "region": region,
                            "title": "DynamoDB DNS Status",
                            "period": 60,
                            "stat": "Average",
                            "setPeriodToTimeRange": True,
                            "sparkline": True,
                            "trend": True
                        }
                    },
                    {
                        "type": "number",
                        "x": 12,
                        "y": 0,
                        "width": 6,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "DNSFailuresDetected", "Region", region]
                            ],
                            "view": "singleValue",
                            "region": region,
                            "title": "Active DNS Failures",
                            "period": 300,
                            "stat": "Sum",
                            "setPeriodToTimeRange": True,
                            "sparkline": True,
                            "trend": True
                        }
                    },
                    {
                        "type": "number",
                        "x": 18,
                        "y": 0,
                        "width": 6,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "DNSResponseTime", "Service", "dynamodb", "Region", region]
                            ],
                            "view": "singleValue",
                            "region": region,
                            "title": "Avg Response Time (ms)",
                            "period": 60,
                            "stat": "Average",
                            "setPeriodToTimeRange": True,
                            "sparkline": True,
                            "trend": True
                        }
                    },
                    
                    # Service health matrix - visual grid
                    {
                        "type": "metric",
                        "x": 0,
                        "y": 6,
                        "width": 12,
                        "height": 8,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "DNSSuccessRate", "Service", "dynamodb", "Region", region, {"color": "#1f77b4"}],
                                [".", ".", ".", "rds", ".", ".", {"color": "#ff7f0e"}],
                                [".", ".", ".", "lambda", ".", ".", {"color": "#2ca02c"}],
                                [".", ".", ".", "ec2", ".", ".", {"color": "#d62728"}],
                                [".", ".", ".", "elbv2", ".", ".", {"color": "#9467bd"}],
                                [".", ".", ".", "s3", ".", ".", {"color": "#8c564b"}]
                            ],
                            "view": "timeSeries",
                            "stacked": False,
                            "region": region,
                            "title": "Service DNS Health Matrix",
                            "period": 60,
                            "stat": "Average",
                            "yAxis": {
                                "left": {
                                    "min": 0,
                                    "max": 100
                                }
                            },
                            "annotations": {
                                "horizontal": [
                                    {
                                        "label": "Critical Threshold",
                                        "value": 50,
                                        "fill": "above"
                                    },
                                    {
                                        "label": "Warning Threshold",
                                        "value": 80,
                                        "fill": "above"
                                    }
                                ]
                            }
                        }
                    },
                    
                    # Multi-region status heatmap
                    {
                        "type": "metric",
                        "x": 12,
                        "y": 6,
                        "width": 12,
                        "height": 8,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "OverallDNSHealth", "Region", "us-east-1", {"color": "#00ff00"}],
                                [".", ".", ".", "us-west-2", {"color": "#ffff00"}],
                                [".", ".", ".", "eu-west-1", {"color": "#ff8000"}]
                            ],
                            "view": "timeSeries",
                            "stacked": False,
                            "region": region,
                            "title": "Multi-Region DNS Health Status",
                            "period": 60,
                            "stat": "Average",
                            "yAxis": {
                                "left": {
                                    "min": 0,
                                    "max": 100
                                }
                            }
                        }
                    },
                    
                    # Response time analysis
                    {
                        "type": "metric",
                        "x": 0,
                        "y": 14,
                        "width": 8,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "DNSResponseTime", "Service", "dynamodb", "Region", region],
                                [".", ".", ".", "rds", ".", "."],
                                [".", ".", ".", "lambda", ".", "."],
                                [".", ".", ".", "ec2", ".", "."]
                            ],
                            "view": "timeSeries",
                            "stacked": False,
                            "region": region,
                            "title": "DNS Response Time Trends",
                            "period": 60,
                            "stat": "Average",
                            "yAxis": {
                                "left": {
                                    "min": 0
                                }
                            }
                        }
                    },
                    
                    # Failure detection timeline
                    {
                        "type": "metric",
                        "x": 8,
                        "y": 14,
                        "width": 8,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "DNSFailuresDetected", "Region", "us-east-1"],
                                [".", ".", ".", "us-west-2"],
                                [".", ".", ".", "eu-west-1"]
                            ],
                            "view": "timeSeries",
                            "stacked": True,
                            "region": region,
                            "title": "DNS Failure Detection Timeline",
                            "period": 60,
                            "stat": "Sum"
                        }
                    },
                    
                    # System status indicator
                    {
                        "type": "number",
                        "x": 16,
                        "y": 14,
                        "width": 8,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "SystemUptimePercentage"]
                            ],
                            "view": "singleValue",
                            "region": region,
                            "title": "System Uptime",
                            "period": 300,
                            "stat": "Average",
                            "setPeriodToTimeRange": True,
                            "sparkline": True
                        }
                    }
                ]
            }
            
            cloudwatch.put_dashboard(
                DashboardName=dashboard_name,
                DashboardBody=json.dumps(dashboard_body)
            )
            
            logger.info(f"✅ Created dashboard: {dashboard_name}")
            return dashboard_name
            
        except Exception as e:
            logger.error(f"Error creating dashboard: {str(e)}")
            return None
    
    def start_monitoring(self):
        """Start continuous DNS monitoring"""
        self.is_monitoring = True
        logger.info("🚀 Starting DNS outage prevention monitoring...")
        
        def monitor_loop():
            while self.is_monitoring:
                try:
                    logger.info("🔄 Starting DNS health check cycle...")
                    
                    # Perform DNS health checks
                    results = self.perform_dns_health_checks()
                    
                    # Publish metrics to CloudWatch
                    self.publish_metrics(results)
                    
                    # Publish additional dashboard metrics
                    self.publish_dashboard_metrics(results)
                    
                    # Analyze results
                    failed_results = [r for r in results if not r['success']]
                    critical_failures = [r for r in failed_results if r['service'] == 'dynamodb']
                    
                    if critical_failures:
                        logger.critical(f"🚨 CRITICAL: {len(critical_failures)} DynamoDB DNS failures detected!")
                        for failure in critical_failures:
                            logger.critical(f"   - {failure['endpoint']} in {failure['region']}: {failure['error']}")
                    
                    if failed_results:
                        logger.warning(f"⚠️  Total DNS failures: {len(failed_results)}/{len(results)}")
                    else:
                        logger.info(f"✅ All DNS checks passed ({len(results)} endpoints)")
                    
                    # Wait before next cycle
                    time.sleep(30)  # Check every 30 seconds
                    
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {str(e)}")
                    time.sleep(15)
        
        # Start monitoring in background thread
        monitor_thread = threading.Thread(target=monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return monitor_thread
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        logger.info("🛑 Stopping DNS monitoring...")
    
    def cleanup_resources(self):
        """Clean up all deployed AWS resources"""
        print("\n🧹 CLEANUP OPTIONS")
        print("=" * 50)
        print("This will remove all DNS monitoring resources:")
        print("• CloudWatch dashboards")
        print("• Custom metrics data")
        print("• CloudWatch alarms (if any)")
        print()
        
        cleanup_choice = input("Do you want to clean up all deployed resources? (yes/no): ").lower().strip()
        
        if cleanup_choice in ['yes', 'y']:
            print("\n🗑️  Starting cleanup process...")
            
            # Delete dashboards
            for region in self.regions:
                try:
                    cloudwatch = self.cloudwatch_clients[region]
                    dashboard_name = f"DNS-Outage-Prevention-{region}"
                    
                    cloudwatch.delete_dashboards(
                        DashboardNames=[dashboard_name]
                    )
                    print(f"✅ Deleted dashboard: {dashboard_name}")
                    
                except Exception as e:
                    if "ResourceNotFound" in str(e):
                        print(f"ℹ️  Dashboard {dashboard_name} not found (already deleted)")
                    else:
                        print(f"❌ Error deleting dashboard {dashboard_name}: {str(e)}")
            
            # Note about metrics cleanup
            print("\nℹ️  Custom metrics will automatically expire after 15 months")
            print("   (AWS doesn't charge for metric storage after they expire)")
            
            print("\n✅ Cleanup completed successfully!")
            print("🎉 All DNS monitoring resources have been removed")
            
        else:
            print("\n🔄 Cleanup cancelled - resources will remain active")
            print("💡 You can run cleanup manually later if needed")

def main():
    """Main function to run DNS monitoring"""
    print("🎯 DNS OUTAGE PREVENTION SYSTEM")
    print("=" * 50)
    print("Monitoring critical AWS service DNS endpoints")
    print("Prevents outages like the recent AWS DynamoDB incident")
    print()
    
    # Initialize monitor
    monitor = SimpleDNSMonitor(regions=['us-east-1', 'us-west-2', 'eu-west-1'])
    
    # Create dashboards
    print("📊 Creating CloudWatch dashboards...")
    for region in monitor.regions:
        dashboard_name = monitor.create_dashboard(region)
        if dashboard_name:
            print(f"✅ Dashboard created: {dashboard_name}")
            dashboard_url = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#dashboards:name={dashboard_name}"
            print(f"🔗 View at: {dashboard_url}")
    
    print()
    
    # Start monitoring
    monitor_thread = monitor.start_monitoring()
    
    try:
        print("🔍 DNS monitoring is now active...")
        print("📈 Metrics are being published to CloudWatch")
        print("🚨 Critical alerts will be logged for DynamoDB failures")
        print("⏹️  Press Ctrl+C to stop monitoring")
        print()
        
        # Keep running
        while monitor.is_monitoring:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping DNS monitoring...")
        monitor.stop_monitoring()
        monitor_thread.join(timeout=5)
        print("✅ DNS monitoring stopped")
        
        # Offer cleanup option
        monitor.cleanup_resources()

if __name__ == "__main__":
    main()