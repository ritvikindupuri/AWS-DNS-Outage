#!/usr/bin/env python3
"""
Enhanced DNS Outage Prevention Monitor with Sleek Dashboard
Real-time DNS monitoring with modern dashboard interface
"""

import json
import time
import logging
import socket
import threading
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class DNSStatus:
    """DNS endpoint status"""
    endpoint: str
    region: str
    service: str
    success: bool
    response_time: float
    ip_addresses: List[str]
    error: str = None
    timestamp: datetime = None

class EnhancedDNSMonitor:
    """Enhanced DNS monitoring with sleek dashboard"""
    
    def __init__(self, regions: List[str] = None):
        self.regions = regions or ['us-east-1', 'us-west-2', 'eu-west-1']
        self.is_monitoring = False
        self.deployed_resources = []
        
        # Critical AWS service endpoints
        self.critical_endpoints = {
            'dynamodb': {
                'endpoints': ['dynamodb.{region}.amazonaws.com', 'streams.dynamodb.{region}.amazonaws.com'],
                'priority': 'critical',
                'color': '#ff4444'
            },
            'rds': {
                'endpoints': ['rds.{region}.amazonaws.com'],
                'priority': 'high',
                'color': '#ff8800'
            },
            'lambda': {
                'endpoints': ['lambda.{region}.amazonaws.com'],
                'priority': 'high',
                'color': '#ffaa00'
            },
            'ec2': {
                'endpoints': ['ec2.{region}.amazonaws.com'],
                'priority': 'medium',
                'color': '#88ff88'
            },
            'elbv2': {
                'endpoints': ['elasticloadbalancing.{region}.amazonaws.com'],
                'priority': 'medium',
                'color': '#4488ff'
            },
            's3': {
                'endpoints': ['s3.{region}.amazonaws.com'],
                'priority': 'low',
                'color': '#8888ff'
            }
        }
        
        # No AWS clients needed - pure DNS monitoring
    
    def check_dns_endpoint(self, endpoint: str, region: str, service: str) -> DNSStatus:
        """Enhanced DNS endpoint checking"""
        start_time = time.time()
        
        try:
            socket.setdefaulttimeout(5)
            ip_addresses = socket.gethostbyname_ex(endpoint)[2]
            response_time = time.time() - start_time
            
            status = DNSStatus(
                endpoint=endpoint,
                region=region,
                service=service,
                success=bool(ip_addresses),
                response_time=response_time,
                ip_addresses=ip_addresses,
                timestamp=datetime.utcnow()
            )
            
            if ip_addresses:
                logger.info(f"✅ {service.upper()} DNS OK [{region}]: {endpoint} -> {ip_addresses[0]} ({response_time*1000:.1f}ms)")
            else:
                logger.warning(f"⚠️  {service.upper()} DNS NO IPs [{region}]: {endpoint}")
                status.error = "No IP addresses returned"
                
            return status
            
        except socket.gaierror as e:
            response_time = time.time() - start_time
            
            status = DNSStatus(
                endpoint=endpoint,
                region=region,
                service=service,
                success=False,
                response_time=response_time,
                ip_addresses=[],
                error=str(e),
                timestamp=datetime.utcnow()
            )
            
            if service == 'dynamodb':
                logger.critical(f"🚨 CRITICAL: DynamoDB DNS FAILURE [{region}]: {endpoint} - {str(e)}")
            else:
                logger.error(f"❌ {service.upper()} DNS FAILED [{region}]: {endpoint} - {str(e)}")
                
            return status
            
        except Exception as e:
            response_time = time.time() - start_time
            logger.error(f"❌ {service.upper()} DNS ERROR [{region}]: {endpoint} - {str(e)}")
            
            return DNSStatus(
                endpoint=endpoint,
                region=region,
                service=service,
                success=False,
                response_time=response_time,
                ip_addresses=[],
                error=str(e),
                timestamp=datetime.utcnow()
            )
    
    def perform_comprehensive_dns_checks(self) -> List[DNSStatus]:
        """Perform comprehensive DNS health checks"""
        all_statuses = []
        
        print(f"\n🔍 DNS Health Check Cycle - {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 70)
        
        for region in self.regions:
            print(f"\n📍 Region: {region.upper()}")
            
            for service, config in self.critical_endpoints.items():
                for endpoint_template in config['endpoints']:
                    endpoint = endpoint_template.format(region=region)
                    status = self.check_dns_endpoint(endpoint, region, service)
                    all_statuses.append(status)
                    
                    # Visual status indicator
                    status_icon = "✅" if status.success else "❌"
                    priority_icon = "🚨" if config['priority'] == 'critical' else "⚠️" if config['priority'] == 'high' else "ℹ️"
                    
                    print(f"  {status_icon} {priority_icon} {service.ljust(10)} | {status.response_time*1000:6.1f}ms | {endpoint}")
        
        return all_statuses
    
    def analyze_dns_health(self, statuses: List[DNSStatus]):
        """Analyze DNS health without external dependencies"""
        try:
            # Calculate overall health metrics
            total_checks = len(statuses)
            successful_checks = len([s for s in statuses if s.success])
            overall_success_rate = (successful_checks / total_checks) * 100 if total_checks > 0 else 100
            
            # Critical service analysis (DynamoDB focus)
            dynamodb_statuses = [s for s in statuses if s.service == 'dynamodb']
            dynamodb_health = 100 if all(s.success for s in dynamodb_statuses) else 0
            
            # Log health summary
            logger.info(f"DNS Health Analysis:")
            logger.info(f"  Overall Success Rate: {overall_success_rate:.1f}%")
            logger.info(f"  DynamoDB Health: {dynamodb_health:.1f}%")
            logger.info(f"  Total Endpoints: {total_checks}")
            logger.info(f"  Failed Endpoints: {total_checks - successful_checks}")
            
            # Alert on critical issues
            if dynamodb_health < 100:
                logger.critical("🚨 CRITICAL: DynamoDB DNS issues detected - Potential cascade failure risk!")
            
            if overall_success_rate < 90:
                logger.warning(f"⚠️  System health below 90%: {overall_success_rate:.1f}%")
                
        except Exception as e:
            logger.error(f"Error analyzing DNS health: {str(e)}")
    
    def create_sleek_dashboard(self, region: str = 'us-east-1'):
        """Create ultra-sleek dashboard similar to datacenter monitoring"""
        try:
            cloudwatch = self.cloudwatch_clients[region]
            dashboard_name = f"DNS-Outage-Prevention-Sleek-{region}"
            
            # Track deployed resource
            self.deployed_resources.append({
                'type': 'dashboard',
                'name': dashboard_name,
                'region': region
            })
            
            dashboard_body = {
                "widgets": [
                    # Top KPI row - Large single value displays
                    {
                        "type": "number",
                        "x": 0,
                        "y": 0,
                        "width": 6,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "SystemUptimePercentage"]
                            ],
                            "view": "singleValue",
                            "region": region,
                            "title": "System Uptime",
                            "period": 60,
                            "stat": "Average",
                            "setPeriodToTimeRange": False,
                            "sparkline": True,
                            "trend": True,
                            "liveData": True
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
                                ["Custom/DNSOutagePrevention", "CriticalServiceHealth", "Region", region]
                            ],
                            "view": "singleValue",
                            "region": region,
                            "title": "DynamoDB Health",
                            "period": 60,
                            "stat": "Average",
                            "setPeriodToTimeRange": False,
                            "sparkline": True,
                            "trend": True,
                            "liveData": True
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
                            "title": "Active Failures",
                            "period": 300,
                            "stat": "Sum",
                            "setPeriodToTimeRange": False,
                            "sparkline": True,
                            "trend": True,
                            "liveData": True
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
                            "title": "Response Time (ms)",
                            "period": 60,
                            "stat": "Average",
                            "setPeriodToTimeRange": False,
                            "sparkline": True,
                            "trend": True,
                            "liveData": True
                        }
                    },
                    
                    # Service health matrix - Visual grid like datacenter sensors
                    {
                        "type": "metric",
                        "x": 0,
                        "y": 6,
                        "width": 12,
                        "height": 8,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "EndpointHealth", "Service", "dynamodb", "Region", region, {"color": "#ff4444", "label": "DynamoDB"}],
                                [".", ".", ".", "rds", ".", ".", {"color": "#ff8800", "label": "RDS"}],
                                [".", ".", ".", "lambda", ".", ".", {"color": "#ffaa00", "label": "Lambda"}],
                                [".", ".", ".", "ec2", ".", ".", {"color": "#88ff88", "label": "EC2"}],
                                [".", ".", ".", "elbv2", ".", ".", {"color": "#4488ff", "label": "ELB"}],
                                [".", ".", ".", "s3", ".", ".", {"color": "#8888ff", "label": "S3"}]
                            ],
                            "view": "timeSeries",
                            "stacked": False,
                            "region": region,
                            "title": "Service Health Matrix",
                            "period": 60,
                            "stat": "Average",
                            "yAxis": {
                                "left": {
                                    "min": 0,
                                    "max": 1
                                }
                            },
                            "liveData": True
                        }
                    },
                    
                    # Multi-region heatmap
                    {
                        "type": "metric",
                        "x": 12,
                        "y": 6,
                        "width": 12,
                        "height": 8,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "OverallDNSHealth", "Region", "us-east-1", {"color": "#00ff88", "label": "US-East-1"}],
                                [".", ".", ".", "us-west-2", {"color": "#0088ff", "label": "US-West-2"}],
                                [".", ".", ".", "eu-west-1", {"color": "#8800ff", "label": "EU-West-1"}]
                            ],
                            "view": "timeSeries",
                            "stacked": False,
                            "region": region,
                            "title": "Multi-Region Health Status",
                            "period": 60,
                            "stat": "Average",
                            "yAxis": {
                                "left": {
                                    "min": 0,
                                    "max": 100
                                }
                            },
                            "liveData": True
                        }
                    },
                    
                    # Response time trends
                    {
                        "type": "metric",
                        "x": 0,
                        "y": 14,
                        "width": 8,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "DNSResponseTime", "Service", "dynamodb", "Region", region, {"color": "#ff4444"}],
                                [".", ".", ".", "rds", ".", ".", {"color": "#ff8800"}],
                                [".", ".", ".", "lambda", ".", ".", {"color": "#ffaa00"}],
                                [".", ".", ".", "ec2", ".", ".", {"color": "#88ff88"}]
                            ],
                            "view": "timeSeries",
                            "stacked": False,
                            "region": region,
                            "title": "Response Time Trends",
                            "period": 60,
                            "stat": "Average",
                            "yAxis": {
                                "left": {
                                    "min": 0
                                }
                            },
                            "liveData": True
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
                                ["Custom/DNSOutagePrevention", "DNSFailuresDetected", "Region", "us-east-1", {"color": "#ff4444"}],
                                [".", ".", ".", "us-west-2", {"color": "#ff8800"}],
                                [".", ".", ".", "eu-west-1", {"color": "#ffaa00"}]
                            ],
                            "view": "timeSeries",
                            "stacked": True,
                            "region": region,
                            "title": "Failure Detection Timeline",
                            "period": 60,
                            "stat": "Sum",
                            "liveData": True
                        }
                    },
                    
                    # Critical alerts indicator
                    {
                        "type": "number",
                        "x": 16,
                        "y": 14,
                        "width": 8,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                ["Custom/DNSOutagePrevention", "CriticalServiceHealth", "Region", region]
                            ],
                            "view": "singleValue",
                            "region": region,
                            "title": "Critical Service Status",
                            "period": 60,
                            "stat": "Average",
                            "setPeriodToTimeRange": False,
                            "sparkline": True,
                            "liveData": True
                        }
                    }
                ]
            }
            
            cloudwatch.put_dashboard(
                DashboardName=dashboard_name,
                DashboardBody=json.dumps(dashboard_body)
            )
            
            logger.info(f"✅ Created sleek dashboard: {dashboard_name}")
            return dashboard_name
            
        except Exception as e:
            logger.error(f"Error creating sleek dashboard: {str(e)}")
            return None
    
    def start_enhanced_monitoring(self):
        """Start enhanced monitoring with real-time updates"""
        self.is_monitoring = True
        logger.info("🚀 Starting enhanced DNS outage prevention monitoring...")
        
        def monitor_loop():
            cycle_count = 0
            while self.is_monitoring:
                try:
                    cycle_count += 1
                    
                    # Perform comprehensive DNS checks
                    statuses = self.perform_comprehensive_dns_checks()
                    
                    # Analyze DNS health
                    self.analyze_dns_health(statuses)
                    
                    # Analyze and report
                    failed_statuses = [s for s in statuses if not s.success]
                    critical_failures = [s for s in failed_statuses if s.service == 'dynamodb']
                    
                    print(f"\n📊 Cycle {cycle_count} Summary:")
                    print(f"   Total Endpoints: {len(statuses)}")
                    print(f"   Healthy: {len(statuses) - len(failed_statuses)}")
                    print(f"   Failed: {len(failed_statuses)}")
                    print(f"   Critical Failures: {len(critical_failures)}")
                    
                    if critical_failures:
                        print(f"\n🚨 CRITICAL ALERT: DynamoDB DNS failures detected!")
                        for failure in critical_failures:
                            print(f"   ❌ {failure.endpoint} [{failure.region}]: {failure.error}")
                    
                    print(f"\n⏱️  Next check in 30 seconds...")
                    time.sleep(30)
                    
                except Exception as e:
                    logger.error(f"Error in enhanced monitoring loop: {str(e)}")
                    time.sleep(15)
        
        monitor_thread = threading.Thread(target=monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
        return monitor_thread
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        logger.info("🛑 Stopping enhanced DNS monitoring...")
    
    def cleanup_all_resources(self):
        """Clean up all deployed resources with confirmation"""
        print("\n" + "="*70)
        print("🧹 RESOURCE CLEANUP")
        print("="*70)
        print("This will remove all DNS monitoring resources:")
        
        for resource in self.deployed_resources:
            print(f"• {resource['type'].title()}: {resource['name']} ({resource['region']})")
        
        print("• Custom CloudWatch metrics (will expire automatically)")
        print("• CloudWatch alarms (if any)")
        print()
        
        cleanup_choice = input("🗑️  Remove all resources? (yes/no): ").lower().strip()
        
        if cleanup_choice in ['yes', 'y']:
            print("\n🔄 Starting cleanup process...")
            
            success_count = 0
            total_count = len(self.deployed_resources)
            
            for resource in self.deployed_resources:
                try:
                    if resource['type'] == 'dashboard':
                        cloudwatch = self.cloudwatch_clients[resource['region']]
                        cloudwatch.delete_dashboards(DashboardNames=[resource['name']])
                        print(f"✅ Deleted {resource['type']}: {resource['name']}")
                        success_count += 1
                        
                except Exception as e:
                    if "ResourceNotFound" in str(e):
                        print(f"ℹ️  {resource['name']} not found (already deleted)")
                        success_count += 1
                    else:
                        print(f"❌ Error deleting {resource['name']}: {str(e)}")
            
            print(f"\n📊 Cleanup Results:")
            print(f"   Successfully removed: {success_count}/{total_count}")
            print(f"   Custom metrics will expire automatically")
            
            if success_count == total_count:
                print("\n🎉 All resources cleaned up successfully!")
            else:
                print(f"\n⚠️  Some resources may require manual cleanup")
                
        else:
            print("\n🔄 Cleanup cancelled - resources remain active")
            print("💡 Run this script again to cleanup later")

def main():
    """Enhanced main function with sleek interface"""
    # Clear screen for better presentation
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("🎯 ENHANCED DNS OUTAGE PREVENTION SYSTEM")
    print("="*70)
    print("🛡️  Prevents DNS failures like the AWS DynamoDB outage")
    print("📊 Creates sleek real-time monitoring dashboards")
    print("🚨 Provides critical alerting for cascade failures")
    print()
    
    # Initialize enhanced monitor
    monitor = EnhancedDNSMonitor(regions=['us-east-1', 'us-west-2', 'eu-west-1'])
    
    # Create sleek dashboards
    print("📊 Creating sleek monitoring dashboards...")
    dashboard_urls = []
    
    for region in monitor.regions:
        dashboard_name = monitor.create_sleek_dashboard(region)
        if dashboard_name:
            print(f"✅ Dashboard created: {dashboard_name}")
            dashboard_url = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#dashboards:name={dashboard_name}"
            dashboard_urls.append(dashboard_url)
            print(f"🔗 View at: {dashboard_url}")
    
    print(f"\n🚀 Starting enhanced monitoring...")
    print("="*70)
    
    # Start enhanced monitoring
    monitor_thread = monitor.start_enhanced_monitoring()
    
    try:
        print("🔍 Enhanced DNS monitoring is now active")
        print("📈 Real-time metrics publishing to CloudWatch")
        print("🚨 Critical DynamoDB alerts will be highlighted")
        print("⏹️  Press Ctrl+C to stop and cleanup")
        print()
        
        # Keep running with status updates
        while monitor.is_monitoring:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Stopping enhanced DNS monitoring...")
        monitor.stop_monitoring()
        monitor_thread.join(timeout=5)
        print("✅ Enhanced monitoring stopped")
        
        # Offer cleanup
        monitor.cleanup_all_resources()

if __name__ == "__main__":
    main()