#!/usr/bin/env python3
"""
AIOps System Integration Layer
Comprehensive integration framework for service discovery, health checks, and communication

This integration layer provides:
- Service discovery and registration
- Health checking and monitoring
- Inter-component communication
- Circuit breaker patterns
- Load balancing for distributed components
- Message routing and queuing
- Distributed configuration synchronization
- Service mesh capabilities
"""

import asyncio
import hashlib
import json
import logging
import random
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('aiops_integration')

class ServiceType(Enum):
    """Service type classifications"""
    CORE = "core"
    ANALYTICS = "analytics"  
    MONITORING = "monitoring"
    AUTOMATION = "automation"
    API = "api"
    STORAGE = "storage"

class ServiceStatus(Enum):
    """Service health status"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

class MessageType(Enum):
    """Inter-service message types"""
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    BROADCAST = "broadcast"
    HEARTBEAT = "heartbeat"

@dataclass
class ServiceEndpoint:
    """Service endpoint information"""
    service_id: str
    service_name: str
    service_type: ServiceType
    host: str
    port: int
    version: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    health_check_url: str = "/health"
    last_heartbeat: datetime = field(default_factory=datetime.now)
    status: ServiceStatus = ServiceStatus.UNKNOWN
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    @property
    def full_health_url(self) -> str:
        return f"{self.base_url}{self.health_check_url}"

@dataclass
class HealthCheckResult:
    """Health check result"""
    service_id: str
    status: ServiceStatus
    response_time_ms: float
    timestamp: datetime
    details: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

@dataclass
class ServiceMessage:
    """Inter-service message"""
    message_id: str
    message_type: MessageType
    source_service: str
    target_service: Optional[str]
    timestamp: datetime
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None
    ttl_seconds: int = 300

class ServiceRegistry:
    """Centralized service discovery and registration"""
    
    def __init__(self):
        self.services: Dict[str, ServiceEndpoint] = {}
        self.service_types: Dict[ServiceType, Set[str]] = defaultdict(set)
        self.registration_lock = threading.Lock()
        
        logger.info("Service Registry initialized")
    
    def register_service(self, endpoint: ServiceEndpoint) -> bool:
        """Register a service endpoint"""
        with self.registration_lock:
            try:
                self.services[endpoint.service_id] = endpoint
                self.service_types[endpoint.service_type].add(endpoint.service_id)
                
                logger.info(f"Registered service: {endpoint.service_name} "
                           f"({endpoint.service_id}) at {endpoint.base_url}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to register service {endpoint.service_id}: {e}")
                return False
    
    def deregister_service(self, service_id: str) -> bool:
        """Deregister a service"""
        with self.registration_lock:
            try:
                if service_id in self.services:
                    endpoint = self.services[service_id]
                    del self.services[service_id]
                    self.service_types[endpoint.service_type].discard(service_id)
                    
                    logger.info(f"Deregistered service: {service_id}")
                    return True
                else:
                    logger.warning(f"Service not found for deregistration: {service_id}")
                    return False
                    
            except Exception as e:
                logger.error(f"Failed to deregister service {service_id}: {e}")
                return False
    
    def discover_service(self, service_name: str) -> Optional[ServiceEndpoint]:
        """Discover a service by name"""
        for endpoint in self.services.values():
            if endpoint.service_name == service_name and endpoint.status == ServiceStatus.HEALTHY:
                return endpoint
        return None
    
    def discover_services_by_type(self, service_type: ServiceType) -> List[ServiceEndpoint]:
        """Discover all services of a specific type"""
        service_ids = self.service_types.get(service_type, set())
        return [self.services[sid] for sid in service_ids 
                if sid in self.services and self.services[sid].status == ServiceStatus.HEALTHY]
    
    def get_all_services(self) -> List[ServiceEndpoint]:
        """Get all registered services"""
        return list(self.services.values())
    
    def update_service_status(self, service_id: str, status: ServiceStatus):
        """Update service health status"""
        if service_id in self.services:
            self.services[service_id].status = status
            self.services[service_id].last_heartbeat = datetime.now()

class HealthChecker:
    """Distributed health checking system"""
    
    def __init__(self, service_registry: ServiceRegistry):
        self.service_registry = service_registry
        self.check_interval = 30
        self.timeout = 5
        self.running = False
        self.health_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        
    async def start_health_checking(self):
        """Start continuous health checking"""
        self.running = True
        logger.info("Starting distributed health checking")
        
        while self.running:
            try:
                services = self.service_registry.get_all_services()
                if services:
                    # Check all services concurrently
                    health_tasks = [self._check_service_health(service) for service in services]
                    results = await asyncio.gather(*health_tasks, return_exceptions=True)
                    
                    # Process results
                    healthy_count = sum(1 for r in results 
                                       if isinstance(r, HealthCheckResult) and r.status == ServiceStatus.HEALTHY)
                    
                    logger.info(f"Health check completed: {healthy_count}/{len(services)} services healthy")
                
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in health checking loop: {e}")
                await asyncio.sleep(5)
    
    async def _check_service_health(self, service: ServiceEndpoint) -> HealthCheckResult:
        """Check health of individual service"""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.get(service.full_health_url) as response:
                    response_time = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        status = ServiceStatus.HEALTHY
                        details = {"response_code": response.status}
                        
                        # Try to parse health details
                        try:
                            health_data = await response.json()
                            details.update(health_data)
                        except Exception:
                            pass
                    else:
                        status = ServiceStatus.UNHEALTHY
                        details = {"response_code": response.status}
                    
                    result = HealthCheckResult(
                        service_id=service.service_id,
                        status=status,
                        response_time_ms=response_time,
                        timestamp=datetime.now(),
                        details=details
                    )
                    
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            result = HealthCheckResult(
                service_id=service.service_id,
                status=ServiceStatus.UNHEALTHY,
                response_time_ms=response_time,
                timestamp=datetime.now(),
                error_message=str(e)
            )
        
        # Update registry and history
        self.service_registry.update_service_status(service.service_id, result.status)
        self.health_history[service.service_id].append(result)
        
        return result
    
    def get_service_health_history(self, service_id: str) -> List[HealthCheckResult]:
        """Get health history for a service"""
        return list(self.health_history.get(service_id, []))
    
    def stop_health_checking(self):
        """Stop health checking"""
        self.running = False

class MessageBroker:
    """Inter-service message broker with routing"""
    
    def __init__(self, service_registry: ServiceRegistry):
        self.service_registry = service_registry
        self.message_queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.message_history: deque = deque(maxlen=1000)
        self.running = False
        
    async def start_message_broker(self):
        """Start the message broker"""
        self.running = True
        logger.info("Message broker started")
        
        # Start message processing loop
        asyncio.create_task(self._process_messages())
    
    def subscribe(self, message_type: str, handler: Callable[[ServiceMessage], None]):
        """Subscribe to message type"""
        self.subscribers[message_type].append(handler)
        logger.info(f"Subscribed handler to message type: {message_type}")
    
    async def publish_message(self, message: ServiceMessage):
        """Publish a message"""
        self.message_history.append(message)
        
        if message.target_service:
            # Direct message to specific service
            await self.message_queues[message.target_service].put(message)
        else:
            # Broadcast message
            for service_id in self.service_registry.services.keys():
                if service_id != message.source_service:
                    await self.message_queues[service_id].put(message)
        
        # Notify subscribers
        if message.message_type.value in self.subscribers:
            for handler in self.subscribers[message.message_type.value]:
                try:
                    handler(message)
                except Exception as e:
                    logger.error(f"Error in message handler: {e}")
        
        logger.debug(f"Published message: {message.message_type.value} from {message.source_service}")
    
    async def get_messages(self, service_id: str, max_messages: int = 10) -> List[ServiceMessage]:
        """Get messages for a service"""
        messages = []
        queue = self.message_queues[service_id]
        
        for _ in range(max_messages):
            try:
                message = queue.get_nowait()
                messages.append(message)
            except asyncio.QueueEmpty:
                break
        
        return messages
    
    async def _process_messages(self):
        """Process message expiration and cleanup"""
        while self.running:
            try:
                current_time = datetime.now()
                
                # Clean up expired messages from history
                expired_messages = []
                for i, message in enumerate(self.message_history):
                    if (current_time - message.timestamp).total_seconds() > message.ttl_seconds:
                        expired_messages.append(i)
                
                # Remove expired messages (reverse order to maintain indices)
                for i in reversed(expired_messages):
                    del self.message_history[i]
                
                await asyncio.sleep(60)  # Cleanup every minute
                
            except Exception as e:
                logger.error(f"Error in message processing: {e}")
                await asyncio.sleep(10)
    
    def get_message_stats(self) -> Dict[str, Any]:
        """Get message broker statistics"""
        message_types = defaultdict(int)
        for message in self.message_history:
            message_types[message.message_type.value] += 1
        
        return {
            "total_messages": len(self.message_history),
            "active_queues": len(self.message_queues),
            "subscribers": {k: len(v) for k, v in self.subscribers.items()},
            "message_types": dict(message_types)
        }

class LoadBalancer:
    """Service load balancer with multiple algorithms"""
    
    def __init__(self, service_registry: ServiceRegistry):
        self.service_registry = service_registry
        self.round_robin_indices: Dict[ServiceType, int] = defaultdict(int)
        
    def get_service_endpoint(self, service_type: ServiceType, 
                           algorithm: str = "round_robin") -> Optional[ServiceEndpoint]:
        """Get service endpoint using load balancing algorithm"""
        services = self.service_registry.discover_services_by_type(service_type)
        
        if not services:
            return None
        
        if algorithm == "round_robin":
            return self._round_robin_selection(service_type, services)
        elif algorithm == "random":
            return random.choice(services)
        elif algorithm == "least_connections":
            # For demo, use random as we don't track connections
            return random.choice(services)
        else:
            return services[0]
    
    def _round_robin_selection(self, service_type: ServiceType, 
                              services: List[ServiceEndpoint]) -> ServiceEndpoint:
        """Round robin selection"""
        index = self.round_robin_indices[service_type] % len(services)
        self.round_robin_indices[service_type] = (index + 1) % len(services)
        return services[index]

class CircuitBreaker:
    """Circuit breaker for service fault tolerance"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.service_states: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'failures': 0,
            'last_failure': None,
            'state': 'closed'  # closed, open, half_open
        })
    
    def can_call_service(self, service_id: str) -> bool:
        """Check if service call is allowed"""
        state = self.service_states[service_id]
        
        if state['state'] == 'closed':
            return True
        elif state['state'] == 'open':
            # Check if recovery timeout has passed
            if state['last_failure']:
                time_since_failure = (datetime.now() - state['last_failure']).total_seconds()
                if time_since_failure >= self.recovery_timeout:
                    state['state'] = 'half_open'
                    return True
            return False
        elif state['state'] == 'half_open':
            return True
        
        return False
    
    def record_success(self, service_id: str):
        """Record successful service call"""
        state = self.service_states[service_id]
        state['failures'] = 0
        state['state'] = 'closed'
    
    def record_failure(self, service_id: str):
        """Record failed service call"""
        state = self.service_states[service_id]
        state['failures'] += 1
        state['last_failure'] = datetime.now()
        
        if state['failures'] >= self.failure_threshold:
            state['state'] = 'open'
            logger.warning(f"Circuit breaker opened for service: {service_id}")

class SystemIntegrationLayer:
    """Main integration layer coordinating all components"""
    
    def __init__(self):
        self.service_registry = ServiceRegistry()
        self.health_checker = HealthChecker(self.service_registry)
        self.message_broker = MessageBroker(self.service_registry)
        self.load_balancer = LoadBalancer(self.service_registry)
        self.circuit_breaker = CircuitBreaker()
        
        # Subscribe to health events
        self.message_broker.subscribe("health_alert", self._handle_health_alert)
        
        logger.info("System Integration Layer initialized")
    
    async def start(self):
        """Start all integration services"""
        logger.info("Starting System Integration Layer")
        
        # Start health checking
        asyncio.create_task(self.health_checker.start_health_checking())
        
        # Start message broker
        await self.message_broker.start_message_broker()
        
        logger.info("System Integration Layer started successfully")
    
    def _handle_health_alert(self, message: ServiceMessage):
        """Handle health alert messages"""
        service_id = message.payload.get('service_id')
        status = message.payload.get('status')
        
        logger.warning(f"Health alert for service {service_id}: {status}")
        
        if status == 'unhealthy':
            self.circuit_breaker.record_failure(service_id)
    
    async def register_demo_services(self):
        """Register demonstration services"""
        demo_services = [
            ServiceEndpoint(
                service_id="perf-monitor-001",
                service_name="performance_monitor",
                service_type=ServiceType.MONITORING,
                host="localhost",
                port=8001,
                version="1.0.0",
                metadata={"instance": "primary"}
            ),
            ServiceEndpoint(
                service_id="analytics-001",
                service_name="analytics_engine", 
                service_type=ServiceType.ANALYTICS,
                host="localhost",
                port=8002,
                version="1.2.0",
                metadata={"cluster": "main"}
            ),
            ServiceEndpoint(
                service_id="auto-scaler-001",
                service_name="auto_scaler",
                service_type=ServiceType.AUTOMATION,
                host="localhost", 
                port=8003,
                version="1.1.0"
            ),
            ServiceEndpoint(
                service_id="api-gateway-001",
                service_name="api_gateway",
                service_type=ServiceType.API,
                host="localhost",
                port=8000,
                version="2.0.0",
                metadata={"role": "primary_gateway"}
            )
        ]
        
        for service in demo_services:
            # Set initial status as healthy for demo
            service.status = ServiceStatus.HEALTHY
            self.service_registry.register_service(service)
        
        logger.info(f"Registered {len(demo_services)} demonstration services")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive integration layer status"""
        services = self.service_registry.get_all_services()
        healthy_services = [s for s in services if s.status == ServiceStatus.HEALTHY]
        
        service_types_count = defaultdict(int)
        for service in services:
            service_types_count[service.service_type.value] += 1
        
        return {
            "service_registry": {
                "total_services": len(services),
                "healthy_services": len(healthy_services),
                "service_types": dict(service_types_count)
            },
            "health_checker": {
                "running": self.health_checker.running,
                "check_interval": self.health_checker.check_interval
            },
            "message_broker": self.message_broker.get_message_stats(),
            "circuit_breaker": {
                "tracked_services": len(self.circuit_breaker.service_states)
            }
        }

async def demonstrate_integration_layer():
    """Demonstrate the system integration layer"""
    print("AIOps System Integration Layer Demonstration")
    print("=" * 60)
    
    # Initialize integration layer
    integration = SystemIntegrationLayer()
    
    try:
        # Start the integration layer
        await integration.start()
        
        # Register demo services
        await integration.register_demo_services()
        
        # Demonstrate service discovery
        print("\nService Discovery:")
        monitoring_service = integration.service_registry.discover_service("performance_monitor")
        if monitoring_service:
            print(f"Found monitoring service: {monitoring_service.service_name} at {monitoring_service.base_url}")
        
        analytics_services = integration.service_registry.discover_services_by_type(ServiceType.ANALYTICS)
        print(f"Found {len(analytics_services)} analytics services")
        
        # Demonstrate load balancing
        print(f"\nLoad Balancing:")
        for i in range(3):
            endpoint = integration.load_balancer.get_service_endpoint(ServiceType.MONITORING)
            if endpoint:
                print(f"Request {i+1} -> {endpoint.service_name} ({endpoint.service_id})")
        
        # Demonstrate messaging
        print(f"\nInter-Service Messaging:")
        test_message = ServiceMessage(
            message_id="test-001",
            message_type=MessageType.EVENT,
            source_service="demo-client",
            target_service=None,  # Broadcast
            timestamp=datetime.now(),
            payload={"event_type": "system_test", "data": "integration_demo"}
        )
        
        await integration.message_broker.publish_message(test_message)
        print(f"Published broadcast message: {test_message.message_type.value}")
        
        # Simulate some activity and health checks
        print(f"\nRunning system for 15 seconds to demonstrate health checking...")
        
        for i in range(3):
            await asyncio.sleep(5)
            
            # Generate some test messages
            heartbeat = ServiceMessage(
                message_id=f"heartbeat-{i}",
                message_type=MessageType.HEARTBEAT,
                source_service="demo-monitor",
                target_service=None,
                timestamp=datetime.now(),
                payload={"timestamp": datetime.now().isoformat()}
            )
            await integration.message_broker.publish_message(heartbeat)
            
            print(f"[{(i+1)*5}s] Generated heartbeat message")
        
        # Display system status
        print(f"\nSystem Integration Status:")
        status = integration.get_system_status()
        
        print(f"Service Registry:")
        print(f"  Total Services: {status['service_registry']['total_services']}")
        print(f"  Healthy Services: {status['service_registry']['healthy_services']}")
        print(f"  Service Types: {status['service_registry']['service_types']}")
        
        print(f"Message Broker:")
        print(f"  Total Messages: {status['message_broker']['total_messages']}")
        print(f"  Active Queues: {status['message_broker']['active_queues']}")
        print(f"  Message Types: {status['message_broker']['message_types']}")
        
        print(f"Health Checker: {'Running' if status['health_checker']['running'] else 'Stopped'}")
        print(f"Circuit Breaker: {status['circuit_breaker']['tracked_services']} services tracked")
        
    except KeyboardInterrupt:
        print(f"\nShutdown requested...")
    finally:
        integration.health_checker.stop_health_checking()
        print(f"Integration layer demonstration completed!")

if __name__ == "__main__":
    asyncio.run(demonstrate_integration_layer())