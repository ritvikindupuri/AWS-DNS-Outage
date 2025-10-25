#!/usr/bin/env python3
"""
DNS Outage Prevention System Launcher
Launches the complete system with web dashboard
"""

import os
import sys
import time
import webbrowser
import threading
from datetime import datetime

def print_banner():
    """Print system banner"""
    print("=" * 70)
    print("🛡️  DNS OUTAGE PREVENTION SYSTEM")
    print("=" * 70)
    print("🎯 Prevents DNS failures like the AWS DynamoDB outage")
    print("📊 Real-time monitoring with beautiful web dashboard")
    print("🚨 Automated alerts and cascade failure prevention")
    print("=" * 70)
    print()

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = ['flask', 'flask-socketio', 'boto3']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print()
        print("📦 Install missing packages with:")
        print(f"   pip install {' '.join(missing_packages)}")
        return False
    
    return True

def open_browser_delayed():
    """Open browser after a delay"""
    time.sleep(3)  # Wait for server to start
    try:
        webbrowser.open('http://localhost:5000')
        print("🌐 Opened dashboard in your default browser")
    except Exception as e:
        print(f"⚠️  Could not open browser automatically: {e}")
        print("🔗 Please open http://localhost:5000 manually")

def main():
    """Main launcher function"""
    print_banner()
    
    # Check dependencies
    print("🔍 Checking dependencies...")
    if not check_dependencies():
        sys.exit(1)
    print("✅ All dependencies found")
    print()
    
    # Show system information
    print("📋 System Information:")
    print(f"   • Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   • Dashboard URL: http://localhost:5000")
    print(f"   • Monitoring Regions: us-east-1, us-west-2, eu-west-1")
    print(f"   • Update Interval: 10 seconds")
    print()
    
    # Start browser opening in background
    browser_thread = threading.Thread(target=open_browser_delayed)
    browser_thread.daemon = True
    browser_thread.start()
    
    print("🚀 Starting DNS Outage Prevention Dashboard...")
    print("⏹️  Press Ctrl+C to stop the system")
    print()
    
    try:
        # Import and run the web dashboard
        from web_dashboard import app, socketio, monitor
        
        # Start monitoring
        monitor.start_monitoring()
        
        # Run the web server
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=False)
        
    except KeyboardInterrupt:
        print("\n🛑 Shutting down DNS Outage Prevention System...")
        try:
            monitor.stop_monitoring()
        except:
            pass
        print("✅ System stopped successfully")
        
    except Exception as e:
        print(f"❌ Error starting system: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()