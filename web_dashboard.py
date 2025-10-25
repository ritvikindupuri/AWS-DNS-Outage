#!/usr/bin/env python3
"""
Real-time DNS Outage Prevention Web Dashboard
Beautiful web interface showing live DNS monitoring data
"""

import asyncio
import json
import time
import socket
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
import random

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dns-outage-prevention-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

@dataclass
class DNSEndpointStatus:
    """DNS endpoint status for dashboard"""
    service: str
    region: str
    endpoint: str
    status: str  # 'healthy', 'warning', 'critical'
    response_time: float
    ip_address: str
    last_check: str
    uptime_percentage: float
    priority: str

class DNSDashboardMonitor:
    """Real-time DNS monitoring for web dashboard"""
    
    def __init__(self):
        self.is_monitoring = False
        self.endpoint_statuses = {}
        self.historical_data = []
        
        # AWS service endpoints with priorities
        self.services = {
            'dynamodb': {
                'endpoints': ['dynamodb.{region}.amazonaws.com', 'streams.dynamodb.{region}.amazonaws.com'],
                'priority': 'critical',
                'color': '#ff4757',
                'icon': '🚨'
            },
            'rds': {
                'endpoints': ['rds.{region}.amazonaws.com'],
                'priority': 'high',
                'color': '#ff6b35',
                'icon': '⚠️'
            },
            'lambda': {
                'endpoints': ['lambda.{region}.amazonaws.com'],
                'priority': 'high',
                'color': '#ffa502',
                'icon': '⚠️'
            },
            'ec2': {
                'endpoints': ['ec2.{region}.amazonaws.com'],
                'priority': 'medium',
                'color': '#2ed573',
                'icon': 'ℹ️'
            },
            'elbv2': {
                'endpoints': ['elasticloadbalancing.{region}.amazonaws.com'],
                'priority': 'medium',
                'color': '#1e90ff',
                'icon': 'ℹ️'
            },
            's3': {
                'endpoints': ['s3.{region}.amazonaws.com'],
                'priority': 'low',
                'color': '#5352ed',
                'icon': 'ℹ️'
            }
        }
        
        self.regions = ['us-east-1', 'us-west-2', 'eu-west-1']
        
    def check_dns_endpoint(self, endpoint: str, region: str, service: str) -> DNSEndpointStatus:
        """Check DNS endpoint and return status"""
        start_time = time.time()
        
        try:
            socket.setdefaulttimeout(3)
            ip_addresses = socket.gethostbyname_ex(endpoint)[2]
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Determine status based on response time and service priority
            if response_time > 100:
                status = 'warning'
            elif response_time > 200:
                status = 'critical'
            else:
                status = 'healthy'
            
            # Critical services have stricter thresholds
            if service == 'dynamodb':
                if response_time > 50:
                    status = 'warning'
                if response_time > 100:
                    status = 'critical'
            
            # Calculate uptime (simulate based on status)
            uptime = 99.9 if status == 'healthy' else 95.5 if status == 'warning' else 85.2
            
            return DNSEndpointStatus(
                service=service,
                region=region,
                endpoint=endpoint,
                status=status,
                response_time=response_time,
                ip_address=ip_addresses[0] if ip_addresses else 'N/A',
                last_check=datetime.now().strftime('%H:%M:%S'),
                uptime_percentage=uptime,
                priority=self.services[service]['priority']
            )
            
        except Exception as e:
            return DNSEndpointStatus(
                service=service,
                region=region,
                endpoint=endpoint,
                status='critical',
                response_time=0,
                ip_address='FAILED',
                last_check=datetime.now().strftime('%H:%M:%S'),
                uptime_percentage=0.0,
                priority=self.services[service]['priority']
            )
    
    def perform_health_checks(self):
        """Perform health checks for all endpoints"""
        current_statuses = {}
        
        for region in self.regions:
            for service, config in self.services.items():
                for endpoint_template in config['endpoints']:
                    endpoint = endpoint_template.format(region=region)
                    key = f"{service}-{region}-{endpoint}"
                    
                    status = self.check_dns_endpoint(endpoint, region, service)
                    current_statuses[key] = status
        
        self.endpoint_statuses = current_statuses
        
        # Store historical data
        timestamp = datetime.now()
        self.historical_data.append({
            'timestamp': timestamp.isoformat(),
            'total_endpoints': len(current_statuses),
            'healthy': len([s for s in current_statuses.values() if s.status == 'healthy']),
            'warning': len([s for s in current_statuses.values() if s.status == 'warning']),
            'critical': len([s for s in current_statuses.values() if s.status == 'critical'])
        })
        
        # Keep only last 50 data points
        if len(self.historical_data) > 50:
            self.historical_data = self.historical_data[-50:]
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get formatted data for dashboard"""
        if not self.endpoint_statuses:
            return {'endpoints': [], 'summary': {}, 'regions': {}}
        
        # Group by region and service
        regions_data = {}
        for region in self.regions:
            regions_data[region] = {
                'services': {},
                'total_endpoints': 0,
                'healthy': 0,
                'warning': 0,
                'critical': 0
            }
        
        # Process endpoint statuses
        endpoints_list = []
        for key, status in self.endpoint_statuses.items():
            endpoints_list.append(asdict(status))
            
            # Update region data
            region_data = regions_data[status.region]
            region_data['total_endpoints'] += 1
            
            if status.status == 'healthy':
                region_data['healthy'] += 1
            elif status.status == 'warning':
                region_data['warning'] += 1
            else:
                region_data['critical'] += 1
            
            # Update service data
            if status.service not in region_data['services']:
                region_data['services'][status.service] = {
                    'status': 'healthy',
                    'endpoints': 0,
                    'avg_response_time': 0,
                    'color': self.services[status.service]['color'],
                    'icon': self.services[status.service]['icon'],
                    'priority': self.services[status.service]['priority']
                }
            
            service_data = region_data['services'][status.service]
            service_data['endpoints'] += 1
            service_data['avg_response_time'] = (service_data['avg_response_time'] + status.response_time) / 2
            
            # Update service status (worst status wins)
            if status.status == 'critical':
                service_data['status'] = 'critical'
            elif status.status == 'warning' and service_data['status'] != 'critical':
                service_data['status'] = 'warning'
        
        # Calculate overall summary
        total_endpoints = len(endpoints_list)
        healthy_count = len([e for e in endpoints_list if e['status'] == 'healthy'])
        warning_count = len([e for e in endpoints_list if e['status'] == 'warning'])
        critical_count = len([e for e in endpoints_list if e['status'] == 'critical'])
        
        summary = {
            'total_endpoints': total_endpoints,
            'healthy': healthy_count,
            'warning': warning_count,
            'critical': critical_count,
            'uptime_percentage': (healthy_count / total_endpoints * 100) if total_endpoints > 0 else 100,
            'avg_response_time': sum(e['response_time'] for e in endpoints_list) / len(endpoints_list) if endpoints_list else 0
        }
        
        return {
            'endpoints': endpoints_list,
            'summary': summary,
            'regions': regions_data,
            'historical': self.historical_data[-20:],  # Last 20 data points
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def start_monitoring(self):
        """Start background monitoring"""
        self.is_monitoring = True
        
        def monitor_loop():
            while self.is_monitoring:
                try:
                    self.perform_health_checks()
                    
                    # Emit data to connected clients
                    dashboard_data = self.get_dashboard_data()
                    socketio.emit('dashboard_update', dashboard_data)
                    
                    time.sleep(10)  # Update every 10 seconds for web dashboard
                    
                except Exception as e:
                    print(f"Error in monitoring loop: {e}")
                    time.sleep(5)
        
        monitor_thread = threading.Thread(target=monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False

# Global monitor instance
monitor = DNSDashboardMonitor()

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """API endpoint for dashboard data"""
    return jsonify(monitor.get_dashboard_data())

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    # Send initial data
    emit('dashboard_update', monitor.get_dashboard_data())

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

if __name__ == '__main__':
    # Start monitoring
    monitor.start_monitoring()
    
    print("🎯 DNS Outage Prevention Web Dashboard")
    print("=" * 50)
    print("🌐 Starting web server...")
    print("📊 Dashboard will be available at: http://localhost:5000")
    print("🔍 Real-time DNS monitoring active")
    print("⏹️  Press Ctrl+C to stop")
    
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 Stopping web dashboard...")
        monitor.stop_monitoring()
        print("✅ Web dashboard stopped")