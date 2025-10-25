#!/usr/bin/env python3
"""
One-Click AWS Outage Prevention System Deployment
Run this script to deploy the complete system
"""

import sys
import os
import subprocess
import json
import time
from datetime import datetime

def check_prerequisites():
    """Check if all prerequisites are met"""
    print("🔍 Checking prerequisites...")
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ is required")
        return False
    
    # Check AWS CLI
    try:
        result = subprocess.run(['aws', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ AWS CLI is not installed or configured")
            return False
        print(f"✅ AWS CLI: {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌ AWS CLI is not installed")
        return False
    
    # Check AWS credentials
    try:
        result = subprocess.run(['aws', 'sts', 'get-caller-identity'], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ AWS credentials not configured")
            return False
        
        identity = json.loads(result.stdout)
        print(f"✅ AWS Account: {identity['Account']}")
        print(f"✅ AWS User: {identity['Arn']}")
    except Exception as e:
        print(f"❌ Error checking AWS credentials: {str(e)}")
        return False
    
    return True

def install_dependencies():
    """Install required Python packages"""
    print("📦 Installing dependencies...")
    
    requirements = [
        'boto3>=1.26.0',
        'numpy>=1.21.0',
        'pandas>=1.3.0',
        'scikit-learn>=1.0.0',
        'dnspython>=2.2.0'
    ]
    
    for requirement in requirements:
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', requirement], 
                         check=True, capture_output=True)
            print(f"✅ Installed: {requirement}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install {requirement}: {e}")
            return False
    
    return True

def deploy_system():
    """Deploy the outage prevention system"""
    print("🚀 Deploying AWS Outage Prevention System...")
    
    try:
        # Add current directory to Python path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'aws'))
        
        # Import and run deployment
        from aws.deployment_script import deploy_aws_outage_prevention
        
        result = deploy_aws_outage_prevention()
        
        print("\n" + "="*80)
        print("🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!")
        print("="*80)
        
        return result
        
    except Exception as e:
        print(f"❌ Deployment failed: {str(e)}")
        return None

def main():
    """Main deployment function"""
    print("🎯 DNS OUTAGE PREVENTION SYSTEM DEPLOYMENT")
    print("="*50)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check prerequisites
    if not check_prerequisites():
        print("\n❌ Prerequisites not met. Please fix the issues above and try again.")
        sys.exit(1)
    
    print("✅ All prerequisites met!")
    print()
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Failed to install dependencies.")
        sys.exit(1)
    
    print("✅ Dependencies installed!")
    print()
    
    # Confirm deployment
    print("⚠️  This will deploy AWS resources that may incur costs.")
    print("   The DNS outage prevention system will create:")
    print("   • DNS monitoring Lambda functions in multiple regions")
    print("   • Real-time DNS health dashboards")
    print("   • DNS failure detection and alerting")
    print("   • Cascade failure prevention automation")
    print("   • EventBridge rules for continuous monitoring")
    print()
    
    confirm = input("Do you want to proceed? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("❌ Deployment cancelled.")
        sys.exit(0)
    
    print()
    
    # Deploy system
    result = deploy_system()
    
    if result:
        print(f"\n📄 Deployment details saved to: deployment_result_{result['deployment_id']}.json")
        print("\n🔗 Next steps:")
        print("1. Open AWS Console > CloudWatch > Dashboards")
        print("2. Look for dashboards starting with 'AWS-Outage-Prevention'")
        print("3. Configure SNS topic subscriptions for alerts")
        print("4. Monitor the system health in real-time")
        print("\n✨ Your AWS infrastructure is now protected against DNS-related outages!")
    else:
        print("\n❌ Deployment failed. Check the logs above for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()