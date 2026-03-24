#!/usr/bin/env python3
"""
Intelligent Auto-Scaling System
Advanced horizontal and vertical scaling automation

This system provides:
- Dynamic horizontal scaling based on load patterns
- Intelligent vertical scaling with resource adjustment
- Predictive scaling using ML-based forecasting
- Auto-scaling policies with customizable triggers
- Resource provisioning and deprovisioning
- Load-aware scaling decisions
"""

import psutil
import time
import json
import logging
import threading
import subprocess
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Any
import statistics
import random
from collections import deque
import math

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('auto_scaler')

@dataclass
class ScalingAction:
    """Auto-scaling action record"""
    id: str
    timestamp: datetime
    action_type: str  # scale_up, scale_down, scale_out, scale_in
    resource_type: str  # cpu, memory, instances
    trigger_metric: str
    trigger_value: float
    threshold: float
    instances_before: int
    instances_after: int
    resources_before: Dict[str, float]
    resources_after: Dict[str, float]
    success: bool
    duration_seconds: float
    cost_impact: float

@dataclass
class ScalingPolicy:
    """Auto-scaling policy configuration"""
    name: str
    resource_type: str
    scaling_type: str  # horizontal, vertical
    metric_name: str
    scale_up_threshold: float
    scale_down_threshold: float
    cooldown_minutes: int
    min_instances: int
    max_instances: int
    scale_increment: int
    enabled: bool
    priority: int

@dataclass
class Instance:
    """Instance representation"""
    id: str
    name: str
    status: str  # running, pending, terminated
    cpu_cores: int
    memory_gb: float
    created_at: datetime
    cost_per_hour: float
    current_load: Dict[str, float]

@dataclass
class ScalingMetrics:
    """Current scaling metrics"""
    timestamp: datetime
    cpu_utilization: float
    memory_utilization: float
    network_throughput: float
    disk_io_rate: float
    request_rate: float
    response_time: float
    error_rate: float
    queue_length: int
    active_connections: int

class IntelligentAutoScaler:
    """Advanced auto-scaling engine with predictive capabilities"""
    
    def __init__(self):
        self.scaling_actions: List[ScalingAction] = []
        self.scaling_policies: List[ScalingPolicy] = []
        self.instances: List[Instance] = []
        self.metrics_history: deque = deque(maxlen=1440)  # 24 hours at 1-minute intervals
        self.is_monitoring = False
        self.monitoring_thread = None
        
        # Scaling parameters
        self.default_instance_specs = {
            "cpu_cores": 2,
            "memory_gb": 4.0,
            "cost_per_hour": 0.10
        }
        
        # Predictive scaling parameters
        self.prediction_window_minutes = 15
        self.scaling_confidence_threshold = 0.7
        
        # Initialize with default policies and instances
        self._initialize_default_policies()
        self._initialize_default_instances()
        
        logger.info("⚡ Intelligent Auto-Scaler initialized")
    
    def _initialize_default_policies(self):
        """Initialize default auto-scaling policies"""
        
        default_policies = [
            ScalingPolicy(
                name="CPU-based Horizontal Scaling",
                resource_type="cpu",
                scaling_type="horizontal",
                metric_name="cpu_utilization",
                scale_up_threshold=75.0,
                scale_down_threshold=30.0,
                cooldown_minutes=5,
                min_instances=1,
                max_instances=10,
                scale_increment=1,
                enabled=True,
                priority=1
            ),
            ScalingPolicy(
                name="Memory-based Horizontal Scaling",
                resource_type="memory",
                scaling_type="horizontal",
                metric_name="memory_utilization",
                scale_up_threshold=80.0,
                scale_down_threshold=40.0,
                cooldown_minutes=10,
                min_instances=1,
                max_instances=8,
                scale_increment=1,
                enabled=True,
                priority=2
            ),
            ScalingPolicy(
                name="Response Time Scaling",
                resource_type="performance",
                scaling_type="horizontal",
                metric_name="response_time",
                scale_up_threshold=2.0,  # 2 seconds
                scale_down_threshold=0.5,  # 0.5 seconds
                cooldown_minutes=8,
                min_instances=1,
                max_instances=15,
                scale_increment=2,
                enabled=True,
                priority=3
            ),
            ScalingPolicy(
                name="Queue Length Scaling",
                resource_type="workload",
                scaling_type="horizontal",
                metric_name="queue_length",
                scale_up_threshold=50.0,
                scale_down_threshold=10.0,
                cooldown_minutes=3,
                min_instances=1,
                max_instances=20,
                scale_increment=3,
                enabled=True,
                priority=4
            )
        ]
        
        self.scaling_policies.extend(default_policies)
        logger.info(f"📋 Initialized {len(default_policies)} auto-scaling policies")
    
    def _initialize_default_instances(self):
        """Initialize with default instances"""
        
        # Start with one default instance
        default_instance = Instance(
            id="instance_001",
            name="primary-instance",
            status="running",
            cpu_cores=self.default_instance_specs["cpu_cores"],
            memory_gb=self.default_instance_specs["memory_gb"],
            created_at=datetime.now(),
            cost_per_hour=self.default_instance_specs["cost_per_hour"],
            current_load={"cpu": 45.0, "memory": 60.0}
        )
        
        self.instances.append(default_instance)
        logger.info(f"🖥️ Initialized with {len(self.instances)} instance(s)")
    
    def collect_scaling_metrics(self) -> ScalingMetrics:
        """Collect current metrics for scaling decisions"""
        try:
            # System metrics
            cpu_util = psutil.cpu_percent(interval=0.1)
            memory_util = psutil.virtual_memory().percent
            
            # Network metrics
            network_io = psutil.net_io_counters()
            network_throughput = 0
            if network_io and len(self.metrics_history) > 0:
                prev_metrics = self.metrics_history[-1]
                time_diff = (datetime.now() - prev_metrics.timestamp).total_seconds()
                if time_diff > 0:
                    network_throughput = ((network_io.bytes_sent + network_io.bytes_recv) - 
                                        (prev_metrics.network_throughput)) / time_diff
            
            # Disk I/O metrics
            disk_io = psutil.disk_io_counters()
            disk_io_rate = 0
            if disk_io and len(self.metrics_history) > 0:
                prev_metrics = self.metrics_history[-1]
                time_diff = (datetime.now() - prev_metrics.timestamp).total_seconds()
                if time_diff > 0:
                    disk_io_rate = ((disk_io.read_bytes + disk_io.write_bytes) - 
                                   (prev_metrics.disk_io_rate)) / time_diff
            
            # Simulated application metrics
            request_rate = max(10, cpu_util * 2 + random.normalvariate(50, 10))
            response_time = max(0.1, (cpu_util / 100) * 3 + random.normalvariate(0.5, 0.2))
            error_rate = max(0, (cpu_util - 50) / 10) if cpu_util > 50 else 0
            queue_length = max(0, int((cpu_util - 60) * 2)) if cpu_util > 60 else 0
            active_connections = max(1, int(request_rate * response_time))
            
            metrics = ScalingMetrics(
                timestamp=datetime.now(),
                cpu_utilization=cpu_util,
                memory_utilization=memory_util,
                network_throughput=network_throughput,
                disk_io_rate=disk_io_rate,
                request_rate=request_rate,
                response_time=response_time,
                error_rate=error_rate,
                queue_length=queue_length,
                active_connections=active_connections
            )
            
            self.metrics_history.append(metrics)
            return metrics
            
        except Exception as e:
            logger.error(f"💥 Error collecting scaling metrics: {e}")
            # Return default metrics
            return ScalingMetrics(
                timestamp=datetime.now(),
                cpu_utilization=50.0,
                memory_utilization=60.0,
                network_throughput=0,
                disk_io_rate=0,
                request_rate=20,
                response_time=1.0,
                error_rate=0,
                queue_length=0,
                active_connections=20
            )
    
    def evaluate_scaling_triggers(self, metrics: ScalingMetrics) -> List[Tuple[ScalingPolicy, str]]:
        """Evaluate which scaling policies should be triggered"""
        triggered_policies = []
        
        for policy in self.scaling_policies:
            if not policy.enabled:
                continue
            
            # Check cooldown
            if self._is_policy_in_cooldown(policy.name):
                continue
            
            # Get metric value
            metric_value = getattr(metrics, policy.metric_name, 0)
            
            # Determine scaling direction
            scaling_direction = None
            if metric_value > policy.scale_up_threshold:
                scaling_direction = "scale_up"
            elif metric_value < policy.scale_down_threshold:
                scaling_direction = "scale_down"
            
            if scaling_direction:
                # Check if scaling is possible
                if self._can_scale(policy, scaling_direction):
                    triggered_policies.append((policy, scaling_direction))
                    logger.info(f"🎯 Scaling trigger: {policy.name} - {scaling_direction} "
                              f"({policy.metric_name}: {metric_value:.1f})")
        
        # Sort by priority
        triggered_policies.sort(key=lambda x: x[0].priority)
        return triggered_policies
    
    def _is_policy_in_cooldown(self, policy_name: str) -> bool:
        """Check if a policy is in cooldown period"""
        policy = next((p for p in self.scaling_policies if p.name == policy_name), None)
        if not policy:
            return False
        
        # Find last scaling action for this policy
        for action in reversed(self.scaling_actions):
            if policy_name in action.id:
                cooldown_end = action.timestamp + timedelta(minutes=policy.cooldown_minutes)
                return datetime.now() < cooldown_end
        
        return False
    
    def _can_scale(self, policy: ScalingPolicy, direction: str) -> bool:
        """Check if scaling is possible given current constraints"""
        current_instances = len([i for i in self.instances if i.status == "running"])
        
        if direction == "scale_up":
            return current_instances < policy.max_instances
        elif direction == "scale_down":
            return current_instances > policy.min_instances
        
        return False
    
    def execute_scaling_action(self, policy: ScalingPolicy, direction: str, 
                             metrics: ScalingMetrics) -> ScalingAction:
        """Execute a scaling action"""
        action_id = f"{policy.name}_{direction}_{int(time.time())}"
        start_time = datetime.now()
        
        # Record before state
        instances_before = len([i for i in self.instances if i.status == "running"])
        resources_before = {
            "total_cpu_cores": sum(i.cpu_cores for i in self.instances if i.status == "running"),
            "total_memory_gb": sum(i.memory_gb for i in self.instances if i.status == "running"),
            "total_cost_per_hour": sum(i.cost_per_hour for i in self.instances if i.status == "running")
        }
        
        # Execute scaling
        success = False
        if policy.scaling_type == "horizontal":
            success = self._execute_horizontal_scaling(policy, direction)
        elif policy.scaling_type == "vertical":
            success = self._execute_vertical_scaling(policy, direction)
        
        # Record after state
        instances_after = len([i for i in self.instances if i.status == "running"])
        resources_after = {
            "total_cpu_cores": sum(i.cpu_cores for i in self.instances if i.status == "running"),
            "total_memory_gb": sum(i.memory_gb for i in self.instances if i.status == "running"),
            "total_cost_per_hour": sum(i.cost_per_hour for i in self.instances if i.status == "running")
        }
        
        # Calculate cost impact
        cost_impact = resources_after["total_cost_per_hour"] - resources_before["total_cost_per_hour"]
        
        # Create scaling action record
        action = ScalingAction(
            id=action_id,
            timestamp=start_time,
            action_type=f"{direction}_{policy.scaling_type}",
            resource_type=policy.resource_type,
            trigger_metric=policy.metric_name,
            trigger_value=getattr(metrics, policy.metric_name, 0),
            threshold=policy.scale_up_threshold if direction == "scale_up" else policy.scale_down_threshold,
            instances_before=instances_before,
            instances_after=instances_after,
            resources_before=resources_before,
            resources_after=resources_after,
            success=success,
            duration_seconds=(datetime.now() - start_time).total_seconds(),
            cost_impact=cost_impact
        )
        
        self.scaling_actions.append(action)
        
        if success:
            logger.info(f"✅ Scaling successful: {policy.name} - {direction} "
                       f"(instances: {instances_before}→{instances_after}, "
                       f"cost impact: ${cost_impact:.2f}/hour)")
        else:
            logger.warning(f"❌ Scaling failed: {policy.name} - {direction}")
        
        return action
    
    def _execute_horizontal_scaling(self, policy: ScalingPolicy, direction: str) -> bool:
        """Execute horizontal scaling (add/remove instances)"""
        try:
            if direction == "scale_up":
                # Add new instances
                for i in range(policy.scale_increment):
                    new_instance = Instance(
                        id=f"instance_{len(self.instances) + 1:03d}",
                        name=f"auto-scaled-instance-{len(self.instances) + 1}",
                        status="running",
                        cpu_cores=self.default_instance_specs["cpu_cores"],
                        memory_gb=self.default_instance_specs["memory_gb"],
                        created_at=datetime.now(),
                        cost_per_hour=self.default_instance_specs["cost_per_hour"],
                        current_load={"cpu": 30.0, "memory": 40.0}  # New instances start with low load
                    )
                    self.instances.append(new_instance)
                    logger.info(f"🖥️ Added new instance: {new_instance.name}")
                
                return True
                
            elif direction == "scale_down":
                # Remove instances (newest first)
                running_instances = [i for i in self.instances if i.status == "running"]
                instances_to_remove = min(policy.scale_increment, len(running_instances) - policy.min_instances)
                
                if instances_to_remove > 0:
                    # Sort by creation time (newest first) and remove
                    running_instances.sort(key=lambda x: x.created_at, reverse=True)
                    
                    for i in range(instances_to_remove):
                        instance = running_instances[i]
                        instance.status = "terminated"
                        logger.info(f"🗑️ Terminated instance: {instance.name}")
                    
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"💥 Horizontal scaling error: {e}")
            return False
    
    def _execute_vertical_scaling(self, policy: ScalingPolicy, direction: str) -> bool:
        """Execute vertical scaling (increase/decrease resources)"""
        try:
            running_instances = [i for i in self.instances if i.status == "running"]
            
            if not running_instances:
                return False
            
            for instance in running_instances:
                if direction == "scale_up":
                    # Increase resources
                    instance.cpu_cores = min(16, instance.cpu_cores + 1)
                    instance.memory_gb = min(32.0, instance.memory_gb + 2.0)
                    instance.cost_per_hour *= 1.5  # Cost increases with resources
                    
                elif direction == "scale_down":
                    # Decrease resources
                    instance.cpu_cores = max(1, instance.cpu_cores - 1)
                    instance.memory_gb = max(1.0, instance.memory_gb - 1.0)
                    instance.cost_per_hour /= 1.5
                
                logger.info(f"⚙️ Scaled instance {instance.name}: "
                           f"{instance.cpu_cores} cores, {instance.memory_gb}GB RAM")
            
            return True
            
        except Exception as e:
            logger.error(f"💥 Vertical scaling error: {e}")
            return False
    
    def predict_scaling_needs(self) -> List[Tuple[str, float, str]]:
        """Predict future scaling needs using historical data"""
        if len(self.metrics_history) < 10:
            return []
        
        predictions = []
        recent_metrics = list(self.metrics_history)[-10:]
        
        # Analyze trends for key metrics
        metrics_to_analyze = ['cpu_utilization', 'memory_utilization', 'response_time', 'queue_length']
        
        for metric_name in metrics_to_analyze:
            values = [getattr(m, metric_name) for m in recent_metrics]
            
            # Simple trend analysis
            if len(values) >= 3:
                # Calculate trend using linear regression slope
                x = list(range(len(values)))
                n = len(values)
                sum_x = sum(x)
                sum_y = sum(values)
                sum_xy = sum(x[i] * values[i] for i in range(n))
                sum_x2 = sum(xi * xi for xi in x)
                
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                
                # Predict value in prediction window
                predicted_value = values[-1] + slope * self.prediction_window_minutes
                
                # Determine if scaling might be needed
                confidence = min(1.0, abs(slope) / max(values) * 10)  # Confidence based on trend strength
                
                if confidence > self.scaling_confidence_threshold:
                    if predicted_value > max(values) * 1.2:  # 20% above current max
                        predictions.append((metric_name, predicted_value, "scale_up"))
                    elif predicted_value < min(values) * 0.8:  # 20% below current min
                        predictions.append((metric_name, predicted_value, "scale_down"))
        
        return predictions
    
    def get_scaling_summary(self) -> Dict[str, Any]:
        """Get comprehensive auto-scaling summary"""
        if not self.scaling_actions:
            return {
                "total_actions": 0,
                "current_instances": len([i for i in self.instances if i.status == "running"]),
                "total_instances": len(self.instances)
            }
        
        successful_actions = [a for a in self.scaling_actions if a.success]
        
        # Calculate cost savings/increases
        total_cost_impact = sum(a.cost_impact for a in self.scaling_actions)
        
        # Action type breakdown
        action_types = {}
        for action in self.scaling_actions:
            action_type = action.action_type
            if action_type not in action_types:
                action_types[action_type] = {"total": 0, "successful": 0}
            action_types[action_type]["total"] += 1
            if action.success:
                action_types[action_type]["successful"] += 1
        
        # Instance statistics
        running_instances = [i for i in self.instances if i.status == "running"]
        
        return {
            "total_actions": len(self.scaling_actions),
            "successful_actions": len(successful_actions),
            "success_rate": (len(successful_actions) / len(self.scaling_actions)) * 100 if self.scaling_actions else 0,
            "current_instances": len(running_instances),
            "total_instances": len(self.instances),
            "total_cpu_cores": sum(i.cpu_cores for i in running_instances),
            "total_memory_gb": sum(i.memory_gb for i in running_instances),
            "total_cost_per_hour": sum(i.cost_per_hour for i in running_instances),
            "cumulative_cost_impact": total_cost_impact,
            "action_breakdown": action_types,
            "active_policies": len([p for p in self.scaling_policies if p.enabled]),
            "metrics_collected": len(self.metrics_history)
        }
    
    def start_auto_scaling(self, interval_seconds: int = 60):
        """Start continuous auto-scaling monitoring"""
        if self.is_monitoring:
            logger.warning("⚠️ Auto-scaling already active")
            return
        
        self.is_monitoring = True
        
        def scaling_loop():
            logger.info(f"⚡ Starting auto-scaling monitoring (interval: {interval_seconds}s)")
            
            while self.is_monitoring:
                try:
                    # Collect current metrics
                    metrics = self.collect_scaling_metrics()
                    
                    # Evaluate scaling triggers
                    triggered_policies = self.evaluate_scaling_triggers(metrics)
                    
                    # Execute scaling actions
                    for policy, direction in triggered_policies:
                        action = self.execute_scaling_action(policy, direction, metrics)
                        
                        if action.success:
                            logger.info(f"✅ Auto-scaling executed: {policy.name}")
                    
                    # Predictive scaling analysis
                    if len(self.metrics_history) % 10 == 0:  # Every 10 samples
                        predictions = self.predict_scaling_needs()
                        if predictions:
                            logger.info(f"🔮 Predicted scaling needs: {len(predictions)} recommendations")
                    
                    time.sleep(interval_seconds)
                    
                except Exception as e:
                    logger.error(f"💥 Auto-scaling loop error: {e}")
                    time.sleep(interval_seconds * 2)
        
        self.monitoring_thread = threading.Thread(target=scaling_loop, daemon=True)
        self.monitoring_thread.start()
    
    def stop_auto_scaling(self):
        """Stop auto-scaling monitoring"""
        self.is_monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=10)
        logger.info("⏹️ Auto-scaling monitoring stopped")

def demo_auto_scaling():
    """Demonstrate the intelligent auto-scaling system"""
    print("⚡ Intelligent Auto-Scaling System Demo")
    print("=" * 70)
    print("Day 9: Performance Optimization and Scalability")
    print("=" * 70)
    
    # Initialize auto-scaler
    scaler = IntelligentAutoScaler()
    
    print(f"\n📋 Auto-scaling policies loaded:")
    for policy in scaler.scaling_policies:
        print(f"   🔸 {policy.name}")
        print(f"      Metric: {policy.metric_name} (up: {policy.scale_up_threshold}, down: {policy.scale_down_threshold})")
        print(f"      Instances: {policy.min_instances}-{policy.max_instances}, increment: {policy.scale_increment}")
    
    print(f"\n🖥️ Initial infrastructure:")
    for instance in scaler.instances:
        print(f"   🔸 {instance.name}: {instance.cpu_cores} cores, {instance.memory_gb}GB RAM, ${instance.cost_per_hour:.2f}/hour")
    
    print(f"\n📊 Simulating various load scenarios...")
    
    # Test scenarios
    test_scenarios = [
        {
            "name": "Normal Load",
            "duration": 3,
            "cpu_range": (40, 60),
            "memory_range": (50, 70),
            "response_time": 1.0,
            "queue_length": 5
        },
        {
            "name": "High CPU Load",
            "duration": 4,
            "cpu_range": (80, 95),
            "memory_range": (60, 75),
            "response_time": 2.5,
            "queue_length": 30
        },
        {
            "name": "Memory Pressure",
            "duration": 3,
            "cpu_range": (60, 70),
            "memory_range": (85, 95),
            "response_time": 1.8,
            "queue_length": 20
        },
        {
            "name": "Queue Overload",
            "duration": 3,
            "cpu_range": (70, 80),
            "memory_range": (70, 80),
            "response_time": 3.0,
            "queue_length": 60
        },
        {
            "name": "Cooling Down",
            "duration": 4,
            "cpu_range": (20, 35),
            "memory_range": (30, 45),
            "response_time": 0.3,
            "queue_length": 2
        }
    ]
    
    for scenario in test_scenarios:
        print(f"\n🎭 Scenario: {scenario['name']} ({scenario['duration']} samples)")
        
        for i in range(scenario['duration']):
            # Create simulated metrics
            metrics = ScalingMetrics(
                timestamp=datetime.now(),
                cpu_utilization=random.uniform(*scenario['cpu_range']),
                memory_utilization=random.uniform(*scenario['memory_range']),
                network_throughput=random.uniform(1000000, 5000000),
                disk_io_rate=random.uniform(500000, 2000000),
                request_rate=random.uniform(20, 100),
                response_time=scenario['response_time'] + random.normalvariate(0, 0.2),
                error_rate=max(0, random.normalvariate(1, 0.5)),
                queue_length=scenario['queue_length'] + int(random.normalvariate(0, 5)),
                active_connections=random.randint(10, 50)
            )
            
            scaler.metrics_history.append(metrics)
            
            print(f"   Sample {i+1}: CPU {metrics.cpu_utilization:.1f}%, "
                  f"Memory {metrics.memory_utilization:.1f}%, "
                  f"Queue {metrics.queue_length}, RT {metrics.response_time:.2f}s")
            
            # Evaluate scaling
            triggered_policies = scaler.evaluate_scaling_triggers(metrics)
            
            for policy, direction in triggered_policies:
                action = scaler.execute_scaling_action(policy, direction, metrics)
                status = "✅" if action.success else "❌"
                print(f"      {status} {direction.replace('_', ' ').title()}: {policy.name} "
                      f"(instances: {action.instances_before}→{action.instances_after})")
            
            time.sleep(0.5)
    
    # Predictive analysis
    print(f"\n🔮 Predictive scaling analysis...")
    predictions = scaler.predict_scaling_needs()
    if predictions:
        print(f"   📈 Predictions for next {scaler.prediction_window_minutes} minutes:")
        for metric, predicted_value, recommendation in predictions:
            print(f"   🔸 {metric}: {predicted_value:.1f} → {recommendation.replace('_', ' ')}")
    else:
        print(f"   📊 No significant trends detected for predictive scaling")
    
    # Show scaling summary
    print(f"\n📊 Auto-Scaling Summary:")
    summary = scaler.get_scaling_summary()
    
    print(f"   🔸 Total Scaling Actions: {summary['total_actions']}")
    print(f"   🔸 Successful Actions: {summary['successful_actions']}")
    print(f"   🔸 Success Rate: {summary['success_rate']:.1f}%")
    print(f"   🔸 Current Instances: {summary['current_instances']}")
    print(f"   🔸 Total CPU Cores: {summary['total_cpu_cores']}")
    print(f"   🔸 Total Memory: {summary['total_memory_gb']:.1f}GB")
    print(f"   🔸 Current Cost: ${summary['total_cost_per_hour']:.2f}/hour")
    print(f"   🔸 Cumulative Cost Impact: ${summary['cumulative_cost_impact']:.2f}/hour")
    
    if summary.get('action_breakdown'):
        print(f"\n📈 Scaling Action Breakdown:")
        for action_type, stats in summary['action_breakdown'].items():
            print(f"   🔸 {action_type.replace('_', ' ').title()}: {stats['successful']}/{stats['total']}")
    
    print(f"\n🎉 Auto-Scaling Demo Complete!")
    print("⚡ Intelligent auto-scaling system is operational with predictive capabilities!")

if __name__ == "__main__":
    demo_auto_scaling()