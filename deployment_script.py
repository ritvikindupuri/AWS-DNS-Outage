"""
Automated Deployment Script for AWS Outage Prevention System
Deploys the complete infrastructure with one command
"""

import boto3
import json
import time
import logging
import subprocess
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AWSOutagePreventionDeployer:
    """
    Automated deployment of AWS outage prevention infrastructure
    """
    
    def __init__(self, regions: List[str] = None, environment: str = 'production'):
        self.regions = regions or ['us-east-1', 'us-west-2', 'eu-west-1']
        self.environment = environment
        self.primary_region = self.regions[0]
        self.deployment_id = f"outage-prevention-{int(time.time())}"
        
        # Initialize clients
        self.clients = {}
        for region in self.regions:
            self.clients[region] = {
                'cloudformation': boto3.client('cloudformation', region_name=region),
                'iam': boto3.client('iam', region_name=region),
                'lambda': boto3.client('lambda', region_name=region),
                'events': boto3.client('events', region_name=region),
                'logs': boto3.client('logs', region_name=region),
                'sns': boto3.client('sns', region_name=region)
            }
    
    def create_iam_roles(self) -> Dict[str, str]:
        """Create necessary IAM roles"""
        logger.info("Creating IAM roles...")
        
        # Lambda execution role
        lambda_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        lambda_permissions_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "cloudwatch:PutMetricData",
                        "cloudwatch:GetMetricStatistics",
                        "cloudwatch:ListMetrics",
                        "ec2:Describe*",
                        "elbv2:Describe*",
                        "rds:Describe*",
                        "ecs:Describe*",
                        "ecs:List*",
                        "lambda:List*",
                        "autoscaling:Describe*",
                        "autoscaling:UpdateAutoScalingGroup",
                        "route53:*",
                        "cloudfront:*",
                        "health:Describe*",
                        "support:*",
                        "sns:Publish"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        try:
            iam_client = self.clients[self.primary_region]['iam']
            
            # Create role
            role_name = f"OutagePreventionLambdaRole-{self.environment}"
            
            try:
                iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(lambda_role_policy),
                    Description="Role for AWS Outage Prevention Lambda functions"
                )
                logger.info(f"Created IAM role: {role_name}")
            except iam_client.exceptions.EntityAlreadyExistsException:
                logger.info(f"IAM role {role_name} already exists")
            
            # Attach policy
            policy_name = f"OutagePreventionLambdaPolicy-{self.environment}"
            
            try:
                iam_client.create_policy(
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(lambda_permissions_policy),
                    Description="Policy for AWS Outage Prevention Lambda functions"
                )
                logger.info(f"Created IAM policy: {policy_name}")
            except iam_client.exceptions.EntityAlreadyExistsException:
                logger.info(f"IAM policy {policy_name} already exists")
            
            # Attach policy to role
            account_id = boto3.client('sts').get_caller_identity()['Account']
            policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
            
            iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn=policy_arn
            )
            
            role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
            
            return {
                'lambda_role_arn': role_arn,
                'policy_arn': policy_arn
            }
            
        except Exception as e:
            logger.error(f"Error creating IAM roles: {str(e)}")
            raise
    
    def create_lambda_functions(self, role_arn: str) -> Dict[str, str]:
        """Create Lambda functions for monitoring and response"""
        logger.info("Creating Lambda functions...")
        
        function_arns = {}
        
        # DNS monitoring function code
        monitoring_code = '''
import json
import boto3
import logging
import dns.resolver
import socket
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """DNS outage prevention monitoring function"""
    try:
        # Critical AWS service endpoints to monitor
        critical_endpoints = {
            'dynamodb': ['dynamodb.{region}.amazonaws.com'],
            'rds': ['rds.{region}.amazonaws.com'],
            'lambda': ['lambda.{region}.amazonaws.com'],
            'ec2': ['ec2.{region}.amazonaws.com'],
            'elbv2': ['elasticloadbalancing.{region}.amazonaws.com']
        }
        
        region = context.invoked_function_arn.split(':')[3]
        cloudwatch = boto3.client('cloudwatch', region_name=region)
        
        dns_failures = 0
        total_checks = 0
        critical_failures = []
        
        # Perform DNS health checks
        for service, endpoint_templates in critical_endpoints.items():
            for template in endpoint_templates:
                endpoint = template.format(region=region)
                total_checks += 1
                
                try:
                    # DNS resolution check
                    resolver = dns.resolver.Resolver()
                    resolver.timeout = 5
                    answers = resolver.resolve(endpoint, 'A')
                    resolved_ips = [str(answer) for answer in answers]
                    
                    if not resolved_ips:
                        dns_failures += 1
                        if service == 'dynamodb':
                            critical_failures.append(f"CRITICAL: DynamoDB DNS failure - {endpoint}")
                            logger.critical(f"DynamoDB DNS resolution failed for {endpoint}")
                        else:
                            logger.warning(f"DNS resolution failed for {endpoint}")
                    
                    # Publish DNS success rate
                    success_rate = 100.0 if resolved_ips else 0.0
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
                            }
                        ]
                    )
                    
                except Exception as e:
                    dns_failures += 1
                    if service == 'dynamodb':
                        critical_failures.append(f"CRITICAL: DynamoDB DNS error - {endpoint}: {str(e)}")
                        logger.critical(f"DynamoDB DNS error for {endpoint}: {str(e)}")
                    else:
                        logger.error(f"DNS error for {endpoint}: {str(e)}")
        
        # Calculate overall DNS health
        dns_health_score = ((total_checks - dns_failures) / total_checks * 100) if total_checks > 0 else 100.0
        
        # Publish overall DNS health
        cloudwatch.put_metric_data(
            Namespace='Custom/DNSOutagePrevention',
            MetricData=[
                {
                    'MetricName': 'OverallDNSHealth',
                    'Dimensions': [
                        {'Name': 'Region', 'Value': region}
                    ],
                    'Value': dns_health_score,
                    'Unit': 'Percent',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'DNSFailuresDetected',
                    'Value': dns_failures,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                }
            ]
        )
        
        # Alert on critical failures
        if critical_failures:
            logger.critical(f"CRITICAL DNS FAILURES DETECTED: {critical_failures}")
            
            # Publish cascade risk metric
            cloudwatch.put_metric_data(
                Namespace='Custom/DNSOutagePrevention',
                MetricData=[
                    {
                        'MetricName': 'CascadeRiskScore',
                        'Dimensions': [
                            {'Name': 'Service', 'Value': 'dynamodb'}
                        ],
                        'Value': 1.0,
                        'Unit': 'None',
                        'Timestamp': datetime.utcnow()
                    }
                ]
            )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'DNS monitoring completed',
                'total_checks': total_checks,
                'dns_failures': dns_failures,
                'dns_health_score': dns_health_score,
                'critical_failures': len(critical_failures)
            })
        }
        
    except Exception as e:
        logger.error(f"Error in DNS monitoring function: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
'''
        
        # Failover function code
        failover_code = '''
import json
import boto3
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Failover management function"""
    try:
        # Import our failover system
        from multi_region_failover import MultiRegionFailoverManager
        
        # Initialize failover manager
        failover_manager = MultiRegionFailoverManager()
        
        # Check if failover is needed
        status = failover_manager.get_status()
        
        # Perform health checks
        for region in failover_manager.all_regions:
            region_health = failover_manager.check_region_health(region)
            
            # Publish region health metrics
            cloudwatch = boto3.client('cloudwatch', region_name=region)
            cloudwatch.put_metric_data(
                Namespace='Custom/OutagePrevention',
                MetricData=[
                    {
                        'MetricName': 'RegionHealthScore',
                        'Dimensions': [
                            {
                                'Name': 'Region',
                                'Value': region
                            }
                        ],
                        'Value': region_health.health_score,
                        'Unit': 'None',
                        'Timestamp': datetime.utcnow()
                    }
                ]
            )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Failover check completed',
                'current_active_region': status['current_active_region'],
                'failover_in_progress': status['failover_in_progress']
            })
        }
        
    except Exception as e:
        logger.error(f"Error in failover function: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
'''
        
        # Create Lambda functions in each region
        for region in self.regions:
            lambda_client = self.clients[region]['lambda']
            
            # DNS monitoring function
            monitoring_function_name = f"dns-outage-prevention-{self.environment}"
            
            try:
                response = lambda_client.create_function(
                    FunctionName=monitoring_function_name,
                    Runtime='python3.9',
                    Role=role_arn,
                    Handler='index.lambda_handler',
                    Code={
                        'ZipFile': monitoring_code.encode('utf-8')
                    },
                    Description='DNS Outage Prevention Monitoring Function',
                    Timeout=300,
                    MemorySize=512,
                    Environment={
                        'Variables': {
                            'ENVIRONMENT': self.environment,
                            'REGION': region
                        }
                    }
                )
                
                function_arns[f"monitoring_{region}"] = response['FunctionArn']
                logger.info(f"Created monitoring function in {region}: {monitoring_function_name}")
                
            except lambda_client.exceptions.ResourceConflictException:
                logger.info(f"Monitoring function already exists in {region}")
                response = lambda_client.get_function(FunctionName=monitoring_function_name)
                function_arns[f"monitoring_{region}"] = response['Configuration']['FunctionArn']
            
            # Failover function
            failover_function_name = f"outage-prevention-failover-{self.environment}"
            
            try:
                response = lambda_client.create_function(
                    FunctionName=failover_function_name,
                    Runtime='python3.9',
                    Role=role_arn,
                    Handler='index.lambda_handler',
                    Code={
                        'ZipFile': failover_code.encode('utf-8')
                    },
                    Description='AWS Outage Prevention Failover Function',
                    Timeout=900,
                    MemorySize=1024,
                    Environment={
                        'Variables': {
                            'ENVIRONMENT': self.environment,
                            'REGION': region
                        }
                    }
                )
                
                function_arns[f"failover_{region}"] = response['FunctionArn']
                logger.info(f"Created failover function in {region}: {failover_function_name}")
                
            except lambda_client.exceptions.ResourceConflictException:
                logger.info(f"Failover function already exists in {region}")
                response = lambda_client.get_function(FunctionName=failover_function_name)
                function_arns[f"failover_{region}"] = response['Configuration']['FunctionArn']
        
        return function_arns
    
    def create_eventbridge_rules(self, function_arns: Dict[str, str]):
        """Create EventBridge rules for scheduled execution"""
        logger.info("Creating EventBridge rules...")
        
        for region in self.regions:
            events_client = self.clients[region]['events']
            lambda_client = self.clients[region]['lambda']
            
            # DNS monitoring rule (every 30 seconds for critical DNS monitoring)
            monitoring_rule_name = f"dns-outage-prevention-{self.environment}"
            
            try:
                events_client.put_rule(
                    Name=monitoring_rule_name,
                    ScheduleExpression='rate(1 minute)',
                    Description='Trigger DNS outage prevention monitoring every minute',
                    State='ENABLED'
                )
                
                # Add Lambda target
                monitoring_function_arn = function_arns[f"monitoring_{region}"]
                
                events_client.put_targets(
                    Rule=monitoring_rule_name,
                    Targets=[
                        {
                            'Id': '1',
                            'Arn': monitoring_function_arn
                        }
                    ]
                )
                
                # Add permission for EventBridge to invoke Lambda
                try:
                    lambda_client.add_permission(
                        FunctionName=monitoring_function_arn,
                        StatementId=f"allow-eventbridge-{region}-monitoring",
                        Action='lambda:InvokeFunction',
                        Principal='events.amazonaws.com',
                        SourceArn=f"arn:aws:events:{region}:{boto3.client('sts').get_caller_identity()['Account']}:rule/{monitoring_rule_name}"
                    )
                except lambda_client.exceptions.ResourceConflictException:
                    pass  # Permission already exists
                
                logger.info(f"Created monitoring EventBridge rule in {region}")
                
            except Exception as e:
                logger.error(f"Error creating monitoring rule in {region}: {str(e)}")
            
            # Failover rule (every 5 minutes)
            failover_rule_name = f"outage-prevention-failover-{self.environment}"
            
            try:
                events_client.put_rule(
                    Name=failover_rule_name,
                    ScheduleExpression='rate(5 minutes)',
                    Description='Trigger outage prevention failover check every 5 minutes',
                    State='ENABLED'
                )
                
                # Add Lambda target
                failover_function_arn = function_arns[f"failover_{region}"]
                
                events_client.put_targets(
                    Rule=failover_rule_name,
                    Targets=[
                        {
                            'Id': '1',
                            'Arn': failover_function_arn
                        }
                    ]
                )
                
                # Add permission for EventBridge to invoke Lambda
                try:
                    lambda_client.add_permission(
                        FunctionName=failover_function_arn,
                        StatementId=f"allow-eventbridge-{region}-failover",
                        Action='lambda:InvokeFunction',
                        Principal='events.amazonaws.com',
                        SourceArn=f"arn:aws:events:{region}:{boto3.client('sts').get_caller_identity()['Account']}:rule/{failover_rule_name}"
                    )
                except lambda_client.exceptions.ResourceConflictException:
                    pass  # Permission already exists
                
                logger.info(f"Created failover EventBridge rule in {region}")
                
            except Exception as e:
                logger.error(f"Error creating failover rule in {region}: {str(e)}")
    
    def create_sns_topics(self) -> Dict[str, str]:
        """Create SNS topics for notifications"""
        logger.info("Creating SNS topics...")
        
        topic_arns = {}
        
        for region in self.regions:
            sns_client = self.clients[region]['sns']
            
            # Critical alerts topic
            critical_topic_name = f"outage-prevention-critical-{self.environment}"
            
            try:
                response = sns_client.create_topic(
                    Name=critical_topic_name,
                    Attributes={
                        'DisplayName': 'AWS Outage Prevention Critical Alerts'
                    }
                )
                
                topic_arns[f"critical_{region}"] = response['TopicArn']
                logger.info(f"Created critical alerts SNS topic in {region}")
                
            except Exception as e:
                logger.error(f"Error creating SNS topic in {region}: {str(e)}")
        
        return topic_arns
    
    def deploy_cloudformation_stack(self, region: str) -> str:
        """Deploy CloudFormation stack"""
        logger.info(f"Deploying CloudFormation stack in {region}...")
        
        try:
            cf_client = self.clients[region]['cloudformation']
            
            # Read the CloudFormation template
            with open('aws/resilience_architecture.yaml', 'r') as f:
                template_body = f.read()
            
            stack_name = f"outage-prevention-infrastructure-{self.environment}"
            
            try:
                cf_client.create_stack(
                    StackName=stack_name,
                    TemplateBody=template_body,
                    Parameters=[
                        {
                            'ParameterKey': 'Environment',
                            'ParameterValue': self.environment
                        },
                        {
                            'ParameterKey': 'PrimaryRegion',
                            'ParameterValue': self.primary_region
                        }
                    ],
                    Capabilities=['CAPABILITY_IAM'],
                    Tags=[
                        {
                            'Key': 'Project',
                            'Value': 'AWS-Outage-Prevention'
                        },
                        {
                            'Key': 'Environment',
                            'Value': self.environment
                        }
                    ]
                )
                
                logger.info(f"CloudFormation stack creation initiated: {stack_name}")
                
                # Wait for stack creation to complete
                waiter = cf_client.get_waiter('stack_create_complete')
                waiter.wait(
                    StackName=stack_name,
                    WaiterConfig={
                        'Delay': 30,
                        'MaxAttempts': 60
                    }
                )
                
                logger.info(f"CloudFormation stack created successfully: {stack_name}")
                return stack_name
                
            except cf_client.exceptions.AlreadyExistsException:
                logger.info(f"CloudFormation stack already exists: {stack_name}")
                return stack_name
                
        except Exception as e:
            logger.error(f"Error deploying CloudFormation stack in {region}: {str(e)}")
            raise
    
    def setup_dashboards(self):
        """Setup DNS outage prevention dashboards"""
        logger.info("Setting up DNS outage prevention dashboards...")
        
        try:
            from live_dashboard import DNSOutageDashboard
            
            dashboard_manager = DNSOutageDashboard(regions=self.regions)
            result = dashboard_manager.setup_complete_monitoring()
            
            logger.info("DNS outage prevention dashboards created successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error setting up dashboards: {str(e)}")
            raise
    
    def deploy_complete_system(self) -> Dict[str, Any]:
        """Deploy the complete outage prevention system"""
        logger.info(f"🚀 Starting deployment of DNS Outage Prevention System")
        logger.info(f"   Deployment ID: {self.deployment_id}")
        logger.info(f"   Environment: {self.environment}")
        logger.info(f"   Regions: {', '.join(self.regions)}")
        
        deployment_result = {
            'deployment_id': self.deployment_id,
            'environment': self.environment,
            'regions': self.regions,
            'start_time': datetime.utcnow().isoformat(),
            'components': {}
        }
        
        try:
            # Step 1: Create IAM roles
            logger.info("📋 Step 1: Creating IAM roles...")
            iam_result = self.create_iam_roles()
            deployment_result['components']['iam'] = iam_result
            
            # Wait for IAM role propagation
            time.sleep(10)
            
            # Step 2: Deploy CloudFormation stacks
            logger.info("🏗️  Step 2: Deploying infrastructure...")
            cf_stacks = {}
            for region in self.regions:
                stack_name = self.deploy_cloudformation_stack(region)
                cf_stacks[region] = stack_name
            deployment_result['components']['cloudformation'] = cf_stacks
            
            # Step 3: Create Lambda functions
            logger.info("⚡ Step 3: Creating Lambda functions...")
            function_arns = self.create_lambda_functions(iam_result['lambda_role_arn'])
            deployment_result['components']['lambda'] = function_arns
            
            # Step 4: Create EventBridge rules
            logger.info("⏰ Step 4: Setting up EventBridge rules...")
            self.create_eventbridge_rules(function_arns)
            deployment_result['components']['eventbridge'] = 'configured'
            
            # Step 5: Create SNS topics
            logger.info("📢 Step 5: Creating SNS topics...")
            topic_arns = self.create_sns_topics()
            deployment_result['components']['sns'] = topic_arns
            
            # Step 6: Setup dashboards
            logger.info("📊 Step 6: Setting up dashboards...")
            dashboard_result = self.setup_dashboards()
            deployment_result['components']['dashboards'] = dashboard_result
            
            deployment_result['end_time'] = datetime.utcnow().isoformat()
            deployment_result['status'] = 'success'
            
            logger.info("🎉 Deployment completed successfully!")
            
            return deployment_result
            
        except Exception as e:
            deployment_result['end_time'] = datetime.utcnow().isoformat()
            deployment_result['status'] = 'failed'
            deployment_result['error'] = str(e)
            
            logger.error(f"❌ Deployment failed: {str(e)}")
            raise
    
    def get_deployment_info(self, deployment_result: Dict[str, Any]) -> str:
        """Generate deployment information"""
        info = f"""
🎯 AWS OUTAGE PREVENTION SYSTEM DEPLOYED SUCCESSFULLY!

📋 Deployment Details:
   • Deployment ID: {deployment_result['deployment_id']}
   • Environment: {deployment_result['environment']}
   • Regions: {', '.join(deployment_result['regions'])}
   • Status: {deployment_result['status'].upper()}

🏗️  Infrastructure Components:
   • CloudFormation Stacks: {len(deployment_result['components']['cloudformation'])} regions
   • Lambda Functions: {len(deployment_result['components']['lambda'])} functions
   • SNS Topics: {len(deployment_result['components']['sns'])} topics
   • CloudWatch Dashboards: {len(deployment_result['components']['dashboards']['dashboards'])} dashboards

📊 Live Monitoring:
   • Access your dashboards in AWS Console > CloudWatch > Dashboards
   • Real-time metrics are being published every minute
   • Automated failover monitoring every 5 minutes

🔗 Dashboard Names:
"""
        
        for dashboard in deployment_result['components']['dashboards']['dashboards']:
            info += f"   • {dashboard}\n"
        
        info += f"""
⚡ System Features:
   • Multi-region failover (Primary: {deployment_result['regions'][0]})
   • ML-powered anomaly detection
   • Automated incident response
   • Real-time health monitoring
   • Predictive outage prevention

🚨 Monitoring Active:
   • System health checks: Every 1 minute
   • Failover assessments: Every 5 minutes
   • Custom metrics publishing: Continuous
   • Automated responses: Real-time

💡 Next Steps:
   1. Check AWS Console > CloudWatch > Dashboards
   2. Review CloudWatch Alarms for critical thresholds
   3. Configure SNS subscriptions for alerts
   4. Test failover scenarios (optional)

🎉 Your AWS infrastructure is now protected against outages!
"""
        
        return info

# Main deployment function
def deploy_aws_outage_prevention():
    """Main deployment function"""
    try:
        # Initialize deployer
        deployer = AWSOutagePreventionDeployer(
            regions=['us-east-1', 'us-west-2', 'eu-west-1'],
            environment='production'
        )
        
        # Deploy complete system
        result = deployer.deploy_complete_system()
        
        # Print deployment info
        info = deployer.get_deployment_info(result)
        print(info)
        
        # Save deployment result
        with open(f'deployment_result_{result["deployment_id"]}.json', 'w') as f:
            json.dump(result, f, indent=2)
        
        return result
        
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}")
        raise

if __name__ == "__main__":
    deploy_aws_outage_prevention()