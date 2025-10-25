"""
Multi-Region Failover System for AWS Outage Prevention
Automatically switches traffic between regions during outages
"""

import boto3
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import threading
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FailoverStatus(Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    FAILING_OVER = "failing_over"
    FAILED = "failed"

@dataclass
class RegionHealth:
    """Region health status"""
    region: str
    status: FailoverStatus
    health_score: float
    last_check: datetime
    services_healthy: int
    services_total: int
    response_time: float

@dataclass
class FailoverEvent:
    """Failover event record"""
    event_id: str
    timestamp: datetime
    from_region: str
    to_region: str
    trigger_reason: str
    duration_seconds: float
    success: bool
    rollback_performed: bool

class MultiRegionFailoverManager:
    """
    Manages automatic failover between AWS regions to prevent outages
    """
    
    def __init__(self, primary_region: str = 'us-east-1', 
                 secondary_regions: List[str] = None):
        self.primary_region = primary_region
        self.secondary_regions = secondary_regions or ['us-west-2', 'eu-west-1']
        self.all_regions = [primary_region] + self.secondary_regions
        
        self.clients = self._initialize_clients()
        self.region_health = {}
        self.failover_events = []
        self.current_active_region = primary_region
        self.is_monitoring = False
        self.failover_in_progress = False
        
        # Failover thresholds
        self.health_threshold = 0.7  # Minimum health score to remain active
        self.response_time_threshold = 5.0  # Maximum response time in seconds
        self.consecutive_failures_threshold = 3
        
        # Initialize region health tracking
        for region in self.all_regions:
            self.region_health[region] = RegionHealth(
                region=region,
                status=FailoverStatus.ACTIVE if region == primary_region else FailoverStatus.STANDBY,
                health_score=1.0,
                last_check=datetime.utcnow(),
                services_healthy=0,
                services_total=0,
                response_time=0.0
            )
    
    def _initialize_clients(self) -> Dict[str, Dict[str, Any]]:
        """Initialize AWS clients for all regions"""
        clients = {}
        
        for region in self.all_regions:
            try:
                clients[region] = {
                    'route53': boto3.client('route53'),  # Global service
                    'cloudfront': boto3.client('cloudfront'),  # Global service
                    'elbv2': boto3.client('elbv2', region_name=region),
                    'ec2': boto3.client('ec2', region_name=region),
                    'rds': boto3.client('rds', region_name=region),
                    'ecs': boto3.client('ecs', region_name=region),
                    'cloudwatch': boto3.client('cloudwatch', region_name=region),
                    'autoscaling': boto3.client('autoscaling', region_name=region)
                }
            except Exception as e:
                logger.error(f"Failed to initialize clients for region {region}: {str(e)}")
                
        return clients
    
    def check_region_health(self, region: str) -> RegionHealth:
        """Comprehensive health check for a region"""
        start_time = time.time()
        
        try:
            services_healthy = 0
            services_total = 0
            
            # Check ELB health
            elb_healthy = self._check_elb_health(region)
            services_total += 1
            if elb_healthy:
                services_healthy += 1
            
            # Check EC2 health
            ec2_healthy = self._check_ec2_health(region)
            services_total += 1
            if ec2_healthy:
                services_healthy += 1
            
            # Check RDS health
            rds_healthy = self._check_rds_health(region)
            services_total += 1
            if rds_healthy:
                services_healthy += 1
            
            # Check ECS health
            ecs_healthy = self._check_ecs_health(region)
            services_total += 1
            if ecs_healthy:
                services_healthy += 1
            
            # Calculate health score
            health_score = services_healthy / services_total if services_total > 0 else 0.0
            response_time = time.time() - start_time
            
            # Determine status
            current_status = self.region_health[region].status
            if health_score < self.health_threshold or response_time > self.response_time_threshold:
                if current_status == FailoverStatus.ACTIVE:
                    new_status = FailoverStatus.FAILING_OVER
                else:
                    new_status = FailoverStatus.FAILED
            else:
                new_status = FailoverStatus.ACTIVE if region == self.current_active_region else FailoverStatus.STANDBY
            
            # Update region health
            region_health = RegionHealth(
                region=region,
                status=new_status,
                health_score=health_score,
                last_check=datetime.utcnow(),
                services_healthy=services_healthy,
                services_total=services_total,
                response_time=response_time
            )
            
            self.region_health[region] = region_health
            
            logger.info(f"Region {region} health: {health_score:.2f} "
                       f"({services_healthy}/{services_total} services healthy, "
                       f"{response_time:.2f}s response time)")
            
            return region_health
            
        except Exception as e:
            logger.error(f"Error checking health for region {region}: {str(e)}")
            
            # Mark region as failed
            failed_health = RegionHealth(
                region=region,
                status=FailoverStatus.FAILED,
                health_score=0.0,
                last_check=datetime.utcnow(),
                services_healthy=0,
                services_total=0,
                response_time=float('inf')
            )
            
            self.region_health[region] = failed_health
            return failed_health
    
    def _check_elb_health(self, region: str) -> bool:
        """Check ELB health in region"""
        try:
            elb_client = self.clients[region]['elbv2']
            load_balancers = elb_client.describe_load_balancers()
            
            if not load_balancers['LoadBalancers']:
                return True  # No load balancers to check
            
            healthy_count = 0
            total_count = len(load_balancers['LoadBalancers'])
            
            for lb in load_balancers['LoadBalancers']:
                if lb['State']['Code'] == 'active':
                    # Check target health
                    target_groups = elb_client.describe_target_groups(
                        LoadBalancerArn=lb['LoadBalancerArn']
                    )
                    
                    for tg in target_groups['TargetGroups']:
                        health = elb_client.describe_target_health(
                            TargetGroupArn=tg['TargetGroupArn']
                        )
                        
                        healthy_targets = [
                            t for t in health['TargetHealthDescriptions']
                            if t['TargetHealth']['State'] == 'healthy'
                        ]
                        
                        if len(healthy_targets) > 0:
                            healthy_count += 1
                            break
            
            return healthy_count / total_count >= 0.5  # At least 50% healthy
            
        except Exception as e:
            logger.error(f"Error checking ELB health in {region}: {str(e)}")
            return False
    
    def _check_ec2_health(self, region: str) -> bool:
        """Check EC2 health in region"""
        try:
            ec2_client = self.clients[region]['ec2']
            instances = ec2_client.describe_instances(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running']}
                ]
            )
            
            if not instances['Reservations']:
                return True  # No instances to check
            
            total_instances = 0
            healthy_instances = 0
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    total_instances += 1
                    
                    # Check instance status
                    status = ec2_client.describe_instance_status(
                        InstanceIds=[instance['InstanceId']]
                    )
                    
                    if status['InstanceStatuses']:
                        instance_status = status['InstanceStatuses'][0]
                        if (instance_status['InstanceStatus']['Status'] == 'ok' and
                            instance_status['SystemStatus']['Status'] == 'ok'):
                            healthy_instances += 1
            
            return healthy_instances / total_instances >= 0.7 if total_instances > 0 else True
            
        except Exception as e:
            logger.error(f"Error checking EC2 health in {region}: {str(e)}")
            return False
    
    def _check_rds_health(self, region: str) -> bool:
        """Check RDS health in region"""
        try:
            rds_client = self.clients[region]['rds']
            db_instances = rds_client.describe_db_instances()
            
            if not db_instances['DBInstances']:
                return True  # No databases to check
            
            healthy_count = 0
            total_count = len(db_instances['DBInstances'])
            
            for db in db_instances['DBInstances']:
                if db['DBInstanceStatus'] == 'available':
                    healthy_count += 1
            
            return healthy_count / total_count >= 0.8  # At least 80% healthy
            
        except Exception as e:
            logger.error(f"Error checking RDS health in {region}: {str(e)}")
            return False
    
    def _check_ecs_health(self, region: str) -> bool:
        """Check ECS health in region"""
        try:
            ecs_client = self.clients[region]['ecs']
            clusters = ecs_client.list_clusters()
            
            if not clusters['clusterArns']:
                return True  # No clusters to check
            
            healthy_clusters = 0
            total_clusters = len(clusters['clusterArns'])
            
            for cluster_arn in clusters['clusterArns']:
                cluster_details = ecs_client.describe_clusters(
                    clusters=[cluster_arn]
                )
                
                if cluster_details['clusters']:
                    cluster = cluster_details['clusters'][0]
                    if cluster['status'] == 'ACTIVE':
                        # Check services in cluster
                        services = ecs_client.list_services(cluster=cluster_arn)
                        
                        if services['serviceArns']:
                            service_details = ecs_client.describe_services(
                                cluster=cluster_arn,
                                services=services['serviceArns']
                            )
                            
                            running_services = [
                                s for s in service_details['services']
                                if s['status'] == 'ACTIVE' and s['runningCount'] > 0
                            ]
                            
                            if len(running_services) >= len(service_details['services']) * 0.7:
                                healthy_clusters += 1
                        else:
                            healthy_clusters += 1  # No services, cluster is healthy
            
            return healthy_clusters / total_clusters >= 0.7
            
        except Exception as e:
            logger.error(f"Error checking ECS health in {region}: {str(e)}")
            return False
    
    def select_best_failover_region(self) -> Optional[str]:
        """Select the best region for failover"""
        available_regions = [
            region for region in self.secondary_regions
            if (self.region_health[region].status in [FailoverStatus.STANDBY, FailoverStatus.ACTIVE] and
                self.region_health[region].health_score >= self.health_threshold)
        ]
        
        if not available_regions:
            logger.error("No healthy regions available for failover!")
            return None
        
        # Sort by health score and response time
        available_regions.sort(
            key=lambda r: (
                -self.region_health[r].health_score,  # Higher health score first
                self.region_health[r].response_time   # Lower response time first
            )
        )
        
        best_region = available_regions[0]
        logger.info(f"Selected {best_region} as failover target "
                   f"(health: {self.region_health[best_region].health_score:.2f}, "
                   f"response: {self.region_health[best_region].response_time:.2f}s)")
        
        return best_region
    
    def perform_failover(self, from_region: str, to_region: str, reason: str) -> bool:
        """Perform failover from one region to another"""
        if self.failover_in_progress:
            logger.warning("Failover already in progress, skipping...")
            return False
        
        self.failover_in_progress = True
        start_time = time.time()
        
        event_id = f"failover-{int(start_time)}"
        logger.info(f"Starting failover {event_id}: {from_region} -> {to_region} (Reason: {reason})")
        
        try:
            # Step 1: Update Route 53 DNS records
            dns_success = self._update_dns_records(from_region, to_region)
            
            # Step 2: Update CloudFront distributions
            cloudfront_success = self._update_cloudfront_origins(from_region, to_region)
            
            # Step 3: Scale up services in target region
            scaling_success = self._scale_up_target_region(to_region)
            
            # Step 4: Verify target region is ready
            verification_success = self._verify_target_region(to_region)
            
            success = dns_success and cloudfront_success and scaling_success and verification_success
            
            if success:
                # Update active region
                self.current_active_region = to_region
                self.region_health[to_region].status = FailoverStatus.ACTIVE
                self.region_health[from_region].status = FailoverStatus.FAILED
                
                logger.info(f"Failover {event_id} completed successfully in {time.time() - start_time:.2f}s")
            else:
                logger.error(f"Failover {event_id} failed, attempting rollback...")
                rollback_success = self._rollback_failover(to_region, from_region)
                
            # Record failover event
            failover_event = FailoverEvent(
                event_id=event_id,
                timestamp=datetime.utcnow(),
                from_region=from_region,
                to_region=to_region,
                trigger_reason=reason,
                duration_seconds=time.time() - start_time,
                success=success,
                rollback_performed=not success
            )
            
            self.failover_events.append(failover_event)
            
            return success
            
        except Exception as e:
            logger.error(f"Error during failover {event_id}: {str(e)}")
            return False
            
        finally:
            self.failover_in_progress = False
    
    def _update_dns_records(self, from_region: str, to_region: str) -> bool:
        """Update Route 53 DNS records to point to new region"""
        try:
            route53_client = self.clients[from_region]['route53']
            
            # Get hosted zones
            hosted_zones = route53_client.list_hosted_zones()
            
            for zone in hosted_zones['HostedZones']:
                zone_id = zone['Id']
                
                # Get record sets
                record_sets = route53_client.list_resource_record_sets(
                    HostedZoneId=zone_id
                )
                
                for record in record_sets['ResourceRecordSets']:
                    if record['Type'] in ['A', 'CNAME'] and 'ResourceRecords' in record:
                        # Check if record points to old region
                        for resource_record in record['ResourceRecords']:
                            if from_region in resource_record['Value']:
                                # Update to new region
                                new_value = resource_record['Value'].replace(from_region, to_region)
                                
                                # Create change batch
                                change_batch = {
                                    'Changes': [{
                                        'Action': 'UPSERT',
                                        'ResourceRecordSet': {
                                            'Name': record['Name'],
                                            'Type': record['Type'],
                                            'TTL': record.get('TTL', 300),
                                            'ResourceRecords': [{'Value': new_value}]
                                        }
                                    }]
                                }
                                
                                # Apply change
                                route53_client.change_resource_record_sets(
                                    HostedZoneId=zone_id,
                                    ChangeBatch=change_batch
                                )
                                
                                logger.info(f"Updated DNS record {record['Name']} to point to {to_region}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating DNS records: {str(e)}")
            return False
    
    def _update_cloudfront_origins(self, from_region: str, to_region: str) -> bool:
        """Update CloudFront distribution origins"""
        try:
            cloudfront_client = self.clients[from_region]['cloudfront']
            
            # Get distributions
            distributions = cloudfront_client.list_distributions()
            
            if 'Items' not in distributions['DistributionList']:
                return True  # No distributions to update
            
            for distribution in distributions['DistributionList']['Items']:
                dist_id = distribution['Id']
                
                # Get distribution config
                config_response = cloudfront_client.get_distribution_config(Id=dist_id)
                config = config_response['DistributionConfig']
                etag = config_response['ETag']
                
                # Update origins
                updated = False
                for origin in config['Origins']['Items']:
                    if from_region in origin['DomainName']:
                        origin['DomainName'] = origin['DomainName'].replace(from_region, to_region)
                        updated = True
                        logger.info(f"Updated CloudFront origin to {origin['DomainName']}")
                
                # Update distribution if changes were made
                if updated:
                    cloudfront_client.update_distribution(
                        Id=dist_id,
                        DistributionConfig=config,
                        IfMatch=etag
                    )
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating CloudFront origins: {str(e)}")
            return False
    
    def _scale_up_target_region(self, region: str) -> bool:
        """Scale up services in target region"""
        try:
            # Scale up Auto Scaling Groups
            autoscaling_client = self.clients[region]['autoscaling']
            
            asgs = autoscaling_client.describe_auto_scaling_groups()
            
            for asg in asgs['AutoScalingGroups']:
                asg_name = asg['AutoScalingGroupName']
                current_capacity = asg['DesiredCapacity']
                
                # Increase capacity by 50% or minimum 2 instances
                new_capacity = max(current_capacity + 2, int(current_capacity * 1.5))
                
                autoscaling_client.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    DesiredCapacity=new_capacity
                )
                
                logger.info(f"Scaled ASG {asg_name} from {current_capacity} to {new_capacity} instances")
            
            # Scale up ECS services
            ecs_client = self.clients[region]['ecs']
            clusters = ecs_client.list_clusters()
            
            for cluster_arn in clusters['clusterArns']:
                services = ecs_client.list_services(cluster=cluster_arn)
                
                for service_arn in services['serviceArns']:
                    service_details = ecs_client.describe_services(
                        cluster=cluster_arn,
                        services=[service_arn]
                    )
                    
                    if service_details['services']:
                        service = service_details['services'][0]
                        current_count = service['desiredCount']
                        new_count = max(current_count + 1, int(current_count * 1.5))
                        
                        ecs_client.update_service(
                            cluster=cluster_arn,
                            service=service_arn,
                            desiredCount=new_count
                        )
                        
                        logger.info(f"Scaled ECS service {service['serviceName']} "
                                   f"from {current_count} to {new_count} tasks")
            
            return True
            
        except Exception as e:
            logger.error(f"Error scaling up target region {region}: {str(e)}")
            return False
    
    def _verify_target_region(self, region: str) -> bool:
        """Verify target region is ready to handle traffic"""
        try:
            # Wait for services to be ready
            max_wait_time = 300  # 5 minutes
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                region_health = self.check_region_health(region)
                
                if (region_health.health_score >= self.health_threshold and
                    region_health.response_time < self.response_time_threshold):
                    logger.info(f"Target region {region} is ready (health: {region_health.health_score:.2f})")
                    return True
                
                logger.info(f"Waiting for target region {region} to be ready... "
                           f"(health: {region_health.health_score:.2f})")
                time.sleep(30)
            
            logger.error(f"Target region {region} failed to become ready within {max_wait_time}s")
            return False
            
        except Exception as e:
            logger.error(f"Error verifying target region {region}: {str(e)}")
            return False
    
    def _rollback_failover(self, failed_region: str, original_region: str) -> bool:
        """Rollback failed failover"""
        try:
            logger.info(f"Rolling back failover from {failed_region} to {original_region}")
            
            # Reverse DNS changes
            dns_rollback = self._update_dns_records(failed_region, original_region)
            
            # Reverse CloudFront changes
            cloudfront_rollback = self._update_cloudfront_origins(failed_region, original_region)
            
            success = dns_rollback and cloudfront_rollback
            
            if success:
                self.current_active_region = original_region
                self.region_health[original_region].status = FailoverStatus.ACTIVE
                logger.info("Rollback completed successfully")
            else:
                logger.error("Rollback failed - manual intervention required")
            
            return success
            
        except Exception as e:
            logger.error(f"Error during rollback: {str(e)}")
            return False
    
    def start_monitoring(self):
        """Start continuous monitoring and automatic failover"""
        self.is_monitoring = True
        logger.info("Starting multi-region failover monitoring...")
        
        def monitor_loop():
            consecutive_failures = {region: 0 for region in self.all_regions}
            
            while self.is_monitoring:
                try:
                    # Check health of all regions
                    for region in self.all_regions:
                        region_health = self.check_region_health(region)
                        
                        if region_health.health_score < self.health_threshold:
                            consecutive_failures[region] += 1
                            logger.warning(f"Region {region} health check failed "
                                         f"({consecutive_failures[region]} consecutive failures)")
                        else:
                            consecutive_failures[region] = 0
                    
                    # Check if active region needs failover
                    active_region = self.current_active_region
                    active_health = self.region_health[active_region]
                    
                    if (consecutive_failures[active_region] >= self.consecutive_failures_threshold or
                        active_health.health_score < self.health_threshold):
                        
                        logger.warning(f"Active region {active_region} is unhealthy, initiating failover...")
                        
                        # Select best failover target
                        target_region = self.select_best_failover_region()
                        
                        if target_region:
                            reason = f"Active region health: {active_health.health_score:.2f}, " \
                                   f"consecutive failures: {consecutive_failures[active_region]}"
                            
                            success = self.perform_failover(active_region, target_region, reason)
                            
                            if success:
                                consecutive_failures[active_region] = 0
                                logger.info(f"Failover to {target_region} completed successfully")
                            else:
                                logger.error(f"Failover to {target_region} failed")
                        else:
                            logger.critical("No healthy regions available for failover!")
                    
                    # Wait before next check
                    time.sleep(60)  # Check every minute
                    
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {str(e)}")
                    time.sleep(30)
        
        # Start monitoring in background thread
        monitor_thread = threading.Thread(target=monitor_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        logger.info("Stopping multi-region failover monitoring...")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current failover system status"""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'monitoring_active': self.is_monitoring,
            'current_active_region': self.current_active_region,
            'failover_in_progress': self.failover_in_progress,
            'region_health': {
                region: {
                    'status': health.status.value,
                    'health_score': health.health_score,
                    'services_healthy': health.services_healthy,
                    'services_total': health.services_total,
                    'response_time': health.response_time,
                    'last_check': health.last_check.isoformat()
                }
                for region, health in self.region_health.items()
            },
            'recent_failover_events': [
                {
                    'event_id': event.event_id,
                    'timestamp': event.timestamp.isoformat(),
                    'from_region': event.from_region,
                    'to_region': event.to_region,
                    'trigger_reason': event.trigger_reason,
                    'duration_seconds': event.duration_seconds,
                    'success': event.success,
                    'rollback_performed': event.rollback_performed
                }
                for event in self.failover_events[-10:]  # Last 10 events
            ]
        }

# Example usage
if __name__ == "__main__":
    # Initialize failover manager
    failover_manager = MultiRegionFailoverManager(
        primary_region='us-east-1',
        secondary_regions=['us-west-2', 'eu-west-1']
    )
    
    # Start monitoring
    failover_manager.start_monitoring()
    
    try:
        # Let it run
        while True:
            time.sleep(60)
            status = failover_manager.get_status()
            print(f"Active Region: {status['current_active_region']}")
            
            for region, health in status['region_health'].items():
                print(f"  {region}: {health['status']} "
                      f"(health: {health['health_score']:.2f})")
                
    except KeyboardInterrupt:
        print("Stopping failover monitoring...")
        failover_manager.stop_monitoring()