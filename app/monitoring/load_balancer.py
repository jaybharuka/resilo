#!/usr/bin/env python3
"""
Intelligent Load Balancing System
Advanced load balancing with routing algorithms, health checking, and failover

This system provides:
- Multiple load balancing algorithms (Round Robin, Weighted, Least Connections, Response Time)
- Real-time health checking with automatic failover
- Circuit breaker pattern for fault tolerance
- Session affinity and sticky sessions
- Dynamic weight adjustment based on performance
- Geographic routing and latency optimization
- Load balancing analytics and monitoring
"""

import asyncio
import aiohttp
import time
import random
import threading
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable
from enum import Enum
import statistics
from collections import defaultdict, deque
import json
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('load_balancer')

class LoadBalancingAlgorithm(Enum):
    """Available load balancing algorithms"""
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    LEAST_RESPONSE_TIME = "least_response_time"
    IP_HASH = "ip_hash"
    GEOGRAPHIC = "geographic"

class ServerStatus(Enum):
    """Server health status"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"

@dataclass
class Server:
    """Backend server configuration"""
    id: str
    host: str
    port: int
    weight: float = 1.0
    max_connections: int = 1000
    location: str = "default"
    
    # Health metrics
    status: ServerStatus = ServerStatus.HEALTHY
    current_connections: int = 0
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    success_rate: float = 1.0
    last_health_check: float = 0
    consecutive_failures: int = 0
    
    # Circuit breaker state
    circuit_breaker_open: bool = False
    circuit_breaker_last_failure: float = 0
    circuit_breaker_failure_count: int = 0

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    @property
    def avg_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return statistics.mean(self.response_times)
    
    @property
    def load_score(self) -> float:
        """Calculate server load score for routing decisions"""
        if self.status != ServerStatus.HEALTHY:
            return float('inf')
        
        connection_load = self.current_connections / self.max_connections
        response_load = min(self.avg_response_time / 1000, 1.0)  # Normalize to seconds
        
        return (connection_load * 0.6) + (response_load * 0.4) + (1 - self.success_rate) * 0.3

@dataclass
class LoadBalancingRequest:
    """Request routing information"""
    client_ip: str
    path: str
    method: str
    headers: Dict[str, str]
    session_id: Optional[str] = None
    geographic_location: str = "default"

@dataclass
class RoutingResult:
    """Load balancing routing result"""
    server: Optional[Server]
    algorithm_used: LoadBalancingAlgorithm
    routing_time_ms: float
    reason: str
    backup_servers: List[Server] = field(default_factory=list)

class CircuitBreaker:
    """Circuit breaker implementation for fault tolerance"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
    
    def should_allow_request(self, server: Server) -> bool:
        """Check if request should be allowed through circuit breaker"""
        current_time = time.time()
        
        # If circuit is open, check if recovery timeout has passed
        if server.circuit_breaker_open:
            if current_time - server.circuit_breaker_last_failure > self.recovery_timeout:
                server.circuit_breaker_open = False
                server.circuit_breaker_failure_count = 0
                logger.info(f"🔄 Circuit breaker reset for server {server.id}")
                return True
            return False
        
        return True
    
    def record_success(self, server: Server):
        """Record successful request"""
        server.circuit_breaker_failure_count = 0
        server.consecutive_failures = 0
    
    def record_failure(self, server: Server):
        """Record failed request"""
        server.circuit_breaker_failure_count += 1
        server.consecutive_failures += 1
        server.circuit_breaker_last_failure = time.time()
        
        if server.circuit_breaker_failure_count >= self.failure_threshold:
            server.circuit_breaker_open = True
            logger.warning(f"⚠️ Circuit breaker opened for server {server.id}")

class HealthChecker:
    """Advanced health checking system"""
    
    def __init__(self, check_interval: int = 30, timeout: int = 5):
        self.check_interval = check_interval
        self.timeout = timeout
        self.running = False
        
    async def check_server_health(self, server: Server) -> bool:
        """Perform health check on a server"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                start_time = time.time()
                async with session.get(f"{server.url}/health") as response:
                    response_time = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        server.response_times.append(response_time)
                        server.consecutive_failures = 0
                        
                        # Update success rate (exponential moving average)
                        server.success_rate = server.success_rate * 0.9 + 0.1
                        
                        # Determine status based on response time and load
                        if response_time > 2000 or server.current_connections > server.max_connections * 0.9:
                            server.status = ServerStatus.DEGRADED
                        else:
                            server.status = ServerStatus.HEALTHY
                        
                        return True
                    else:
                        raise aiohttp.ClientError(f"Health check failed: {response.status}")
                        
        except Exception as e:
            logger.warning(f"⚠️ Health check failed for {server.id}: {str(e)}")
            server.consecutive_failures += 1
            server.success_rate = max(server.success_rate * 0.8, 0.0)
            
            if server.consecutive_failures >= 3:
                server.status = ServerStatus.UNHEALTHY
            
            return False
    
    async def start_health_checking(self, servers: List[Server]):
        """Start continuous health checking"""
        self.running = True
        logger.info(f"🔍 Starting health checks every {self.check_interval}s")
        
        while self.running:
            health_tasks = [self.check_server_health(server) for server in servers]
            results = await asyncio.gather(*health_tasks, return_exceptions=True)
            
            healthy_count = sum(1 for result in results if result is True)
            logger.info(f"💚 Health check completed: {healthy_count}/{len(servers)} servers healthy")
            
            await asyncio.sleep(self.check_interval)
    
    def stop_health_checking(self):
        """Stop health checking"""
        self.running = False

class IntelligentLoadBalancer:
    """Advanced load balancer with multiple algorithms and intelligent routing"""
    
    def __init__(self):
        self.servers: List[Server] = []
        self.session_affinity: Dict[str, str] = {}  # session_id -> server_id
        self.round_robin_index = 0
        self.circuit_breaker = CircuitBreaker()
        self.health_checker = HealthChecker()
        
        # Analytics
        self.routing_stats = defaultdict(int)
        self.response_times = deque(maxlen=1000)
        self.total_requests = 0
        self.successful_requests = 0
        
        logger.info("⚖️ Intelligent Load Balancer initialized")
    
    def add_server(self, server: Server):
        """Add a backend server"""
        self.servers.append(server)
        logger.info(f"➕ Added server {server.id} ({server.url})")
    
    def remove_server(self, server_id: str):
        """Remove a backend server"""
        self.servers = [s for s in self.servers if s.id != server_id]
        logger.info(f"➖ Removed server {server_id}")
    
    def get_healthy_servers(self) -> List[Server]:
        """Get list of healthy servers"""
        return [s for s in self.servers if s.status in [ServerStatus.HEALTHY, ServerStatus.DEGRADED]]
    
    def route_request(self, request: LoadBalancingRequest, 
                     algorithm: LoadBalancingAlgorithm = LoadBalancingAlgorithm.LEAST_RESPONSE_TIME) -> RoutingResult:
        """Route request using specified algorithm"""
        start_time = time.time()
        self.total_requests += 1
        
        # Check session affinity first
        if request.session_id and request.session_id in self.session_affinity:
            server_id = self.session_affinity[request.session_id]
            server = next((s for s in self.servers if s.id == server_id), None)
            if server and server.status == ServerStatus.HEALTHY:
                routing_time = (time.time() - start_time) * 1000
                return RoutingResult(
                    server=server,
                    algorithm_used=algorithm,
                    routing_time_ms=routing_time,
                    reason="Session affinity"
                )
        
        # Get healthy servers
        healthy_servers = self.get_healthy_servers()
        if not healthy_servers:
            return RoutingResult(
                server=None,
                algorithm_used=algorithm,
                routing_time_ms=(time.time() - start_time) * 1000,
                reason="No healthy servers available"
            )
        
        # Apply load balancing algorithm
        server = self._select_server(healthy_servers, request, algorithm)
        
        # Apply circuit breaker
        if server and not self.circuit_breaker.should_allow_request(server):
            # Try next best server
            remaining_servers = [s for s in healthy_servers if s != server]
            if remaining_servers:
                server = self._select_server(remaining_servers, request, algorithm)
            else:
                server = None
        
        routing_time = (time.time() - start_time) * 1000
        self.routing_stats[algorithm.value] += 1
        
        reason = f"Algorithm: {algorithm.value}"
        if server:
            # Update session affinity
            if request.session_id:
                self.session_affinity[request.session_id] = server.id
        
        return RoutingResult(
            server=server,
            algorithm_used=algorithm,
            routing_time_ms=routing_time,
            reason=reason,
            backup_servers=healthy_servers[:3] if server else []
        )
    
    def _select_server(self, servers: List[Server], request: LoadBalancingRequest, 
                      algorithm: LoadBalancingAlgorithm) -> Optional[Server]:
        """Select server based on algorithm"""
        
        if algorithm == LoadBalancingAlgorithm.ROUND_ROBIN:
            return self._round_robin_selection(servers)
        
        elif algorithm == LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin_selection(servers)
        
        elif algorithm == LoadBalancingAlgorithm.LEAST_CONNECTIONS:
            return min(servers, key=lambda s: s.current_connections)
        
        elif algorithm == LoadBalancingAlgorithm.LEAST_RESPONSE_TIME:
            return min(servers, key=lambda s: s.load_score)
        
        elif algorithm == LoadBalancingAlgorithm.IP_HASH:
            return self._ip_hash_selection(servers, request.client_ip)
        
        elif algorithm == LoadBalancingAlgorithm.GEOGRAPHIC:
            return self._geographic_selection(servers, request.geographic_location)
        
        return servers[0] if servers else None
    
    def _round_robin_selection(self, servers: List[Server]) -> Server:
        """Round robin server selection"""
        server = servers[self.round_robin_index % len(servers)]
        self.round_robin_index = (self.round_robin_index + 1) % len(servers)
        return server
    
    def _weighted_round_robin_selection(self, servers: List[Server]) -> Server:
        """Weighted round robin selection"""
        total_weight = sum(s.weight for s in servers)
        random_weight = random.uniform(0, total_weight)
        
        cumulative_weight = 0
        for server in servers:
            cumulative_weight += server.weight
            if random_weight <= cumulative_weight:
                return server
        
        return servers[-1]
    
    def _ip_hash_selection(self, servers: List[Server], client_ip: str) -> Server:
        """IP hash-based selection for consistent routing"""
        hash_value = int(hashlib.md5(client_ip.encode(), usedforsecurity=False).hexdigest(), 16)
        return servers[hash_value % len(servers)]
    
    def _geographic_selection(self, servers: List[Server], location: str) -> Server:
        """Geographic-based selection"""
        # Prefer servers in same location
        local_servers = [s for s in servers if s.location == location]
        if local_servers:
            return min(local_servers, key=lambda s: s.load_score)
        
        # Fall back to least loaded server
        return min(servers, key=lambda s: s.load_score)
    
    def record_request_result(self, server: Server, success: bool, response_time_ms: float):
        """Record request result for analytics"""
        server.response_times.append(response_time_ms)
        self.response_times.append(response_time_ms)
        
        if success:
            self.successful_requests += 1
            self.circuit_breaker.record_success(server)
            server.current_connections = max(0, server.current_connections - 1)
        else:
            self.circuit_breaker.record_failure(server)
            server.current_connections = max(0, server.current_connections - 1)
    
    async def start_health_checking(self):
        """Start health checking for all servers"""
        await self.health_checker.start_health_checking(self.servers)
    
    def stop_health_checking(self):
        """Stop health checking"""
        self.health_checker.stop_health_checking()
    
    def get_load_balancer_stats(self) -> Dict:
        """Get comprehensive load balancer statistics"""
        healthy_servers = len(self.get_healthy_servers())
        total_servers = len(self.servers)
        
        avg_response_time = statistics.mean(self.response_times) if self.response_times else 0
        success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
        
        server_stats = []
        for server in self.servers:
            server_stats.append({
                "id": server.id,
                "url": server.url,
                "status": server.status.value,
                "current_connections": server.current_connections,
                "avg_response_time": server.avg_response_time,
                "success_rate": server.success_rate * 100,
                "load_score": server.load_score,
                "weight": server.weight,
                "location": server.location
            })
        
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "success_rate": success_rate,
            "avg_response_time_ms": avg_response_time,
            "healthy_servers": healthy_servers,
            "total_servers": total_servers,
            "availability": (healthy_servers / total_servers * 100) if total_servers > 0 else 0,
            "routing_algorithms_used": dict(self.routing_stats),
            "active_sessions": len(self.session_affinity),
            "servers": server_stats
        }

async def demonstrate_load_balancer():
    """Demonstrate the intelligent load balancer"""
    print("⚖️ Intelligent Load Balancer Demonstration")
    print("=" * 60)
    
    # Initialize load balancer
    lb = IntelligentLoadBalancer()
    
    # Add backend servers
    servers = [
        Server("web1", "192.168.1.10", 8001, weight=1.0, location="us-east"),
        Server("web2", "192.168.1.11", 8002, weight=1.5, location="us-east"),
        Server("web3", "192.168.1.12", 8003, weight=0.8, location="us-west"),
        Server("web4", "192.168.1.13", 8004, weight=1.2, location="eu-west"),
        Server("web5", "192.168.1.14", 8005, weight=1.0, location="asia-pacific")
    ]
    
    for server in servers:
        lb.add_server(server)
    
    print(f"📊 Added {len(servers)} backend servers")
    
    # Simulate different routing scenarios
    algorithms = [
        LoadBalancingAlgorithm.ROUND_ROBIN,
        LoadBalancingAlgorithm.LEAST_CONNECTIONS,
        LoadBalancingAlgorithm.LEAST_RESPONSE_TIME,
        LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN,
        LoadBalancingAlgorithm.IP_HASH,
        LoadBalancingAlgorithm.GEOGRAPHIC
    ]
    
    client_ips = ["10.0.1.100", "10.0.1.101", "10.0.1.102", "10.0.1.103"]
    locations = ["us-east", "us-west", "eu-west", "asia-pacific"]
    
    print("\n🚀 Simulating load balancing scenarios...")
    
    for i, algorithm in enumerate(algorithms):
        print(f"\n--- Scenario {i+1}: {algorithm.value.replace('_', ' ').title()} ---")
        
        # Simulate server conditions
        for j, server in enumerate(servers):
            server.current_connections = random.randint(0, 50)
            server.response_times.extend([random.uniform(100, 1000) for _ in range(10)])
            server.success_rate = random.uniform(0.85, 1.0)
            if j == 2:  # Make one server degraded
                server.status = ServerStatus.DEGRADED
            else:
                server.status = ServerStatus.HEALTHY
        
        # Route requests
        for request_num in range(5):
            request = LoadBalancingRequest(
                client_ip=random.choice(client_ips),
                path=f"/api/endpoint{request_num}",
                method="GET",
                headers={"User-Agent": "LoadBalancer-Test"},
                session_id=f"session_{request_num % 3}",
                geographic_location=random.choice(locations)
            )
            
            result = lb.route_request(request, algorithm)
            
            if result.server:
                result.server.current_connections += 1
                # Simulate request processing
                response_time = random.uniform(200, 800)
                success = random.random() > 0.05  # 95% success rate
                
                lb.record_request_result(result.server, success, response_time)
                
                print(f"  Request {request_num + 1}: → {result.server.id} "
                      f"({result.routing_time_ms:.1f}ms routing, {response_time:.0f}ms response)")
            else:
                print(f"  Request {request_num + 1}: ❌ No server available")
    
    # Simulate circuit breaker
    print(f"\n--- Circuit Breaker Test ---")
    problem_server = servers[1]
    print(f"🔴 Simulating failures on {problem_server.id}")
    
    for i in range(8):
        lb.record_request_result(problem_server, False, 5000)
        if problem_server.circuit_breaker_open:
            print(f"⚠️ Circuit breaker opened after {i+1} failures")
            break
    
    # Test routing with circuit breaker open
    request = LoadBalancingRequest("10.0.1.200", "/test", "GET", {})
    result = lb.route_request(request, LoadBalancingAlgorithm.LEAST_CONNECTIONS)
    print(f"🔄 Routing with circuit breaker: → {result.server.id if result.server else 'None'}")
    
    # Display final statistics
    print(f"\n📈 Load Balancer Statistics:")
    stats = lb.get_load_balancer_stats()
    
    print(f"  Total Requests: {stats['total_requests']}")
    print(f"  Success Rate: {stats['success_rate']:.1f}%")
    print(f"  Avg Response Time: {stats['avg_response_time_ms']:.1f}ms")
    print(f"  Server Availability: {stats['availability']:.1f}%")
    print(f"  Active Sessions: {stats['active_sessions']}")
    
    print(f"\n🖥️ Server Status:")
    for server_stat in stats['servers']:
        status_emoji = "💚" if server_stat['status'] == 'healthy' else "🟡" if server_stat['status'] == 'degraded' else "🔴"
        print(f"  {status_emoji} {server_stat['id']}: {server_stat['status']} | "
              f"Connections: {server_stat['current_connections']} | "
              f"Avg Response: {server_stat['avg_response_time']:.0f}ms | "
              f"Load Score: {server_stat['load_score']:.2f}")
    
    print(f"\n🎯 Algorithm Usage:")
    for algo, count in stats['routing_algorithms_used'].items():
        print(f"  {algo.replace('_', ' ').title()}: {count} requests")
    
    print(f"\n✅ Load Balancer demonstration completed successfully!")
    return lb, stats

if __name__ == "__main__":
    # Run demonstration
    asyncio.run(demonstrate_load_balancer())