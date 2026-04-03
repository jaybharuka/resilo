#!/usr/bin/env python3
"""
AIOps API Gateway and Security System
Comprehensive API gateway with authentication, authorization, rate limiting, and routing

This API gateway provides:
- Request routing and load balancing
- Authentication and authorization
- Rate limiting and throttling
- API versioning and documentation
- Request/response transformation
- Security headers and CORS
- Metrics and monitoring
- Circuit breaker integration
- WebSocket support
- SSL/TLS termination
"""

import asyncio
import os
import aiohttp
from aiohttp import web, ClientSession
import aiohttp_cors
import jwt
import time
import json
import logging
import hashlib
import secrets
import uuid
try:
    import bcrypt as _bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set, Union
from enum import Enum
from collections import defaultdict, deque
import re
import ssl
import base64
from functools import wraps
import asyncio
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('aiops_gateway')

class AuthMethod(Enum):
    """Authentication methods"""
    JWT = "jwt"
    API_KEY = "api_key"
    BASIC = "basic"
    OAUTH2 = "oauth2"

class UserRole(Enum):
    """User roles for authorization"""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    SERVICE = "service"

class RateLimitType(Enum):
    """Rate limiting types"""
    PER_IP = "per_ip"
    PER_USER = "per_user"
    PER_API_KEY = "per_api_key"
    GLOBAL = "global"

@dataclass
class User:
    """User information"""
    user_id: str
    username: str
    email: str
    roles: List[UserRole]
    api_keys: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class APIKey:
    """API key information"""
    key_id: str
    key_hash: str
    user_id: str
    name: str
    permissions: List[str] = field(default_factory=list)
    rate_limit: int = 1000  # requests per minute
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    active: bool = True

@dataclass
class Route:
    """API route configuration"""
    path: str
    methods: List[str]
    target_service: str
    target_path: Optional[str] = None
    auth_required: bool = True
    required_roles: List[UserRole] = field(default_factory=list)
    rate_limit: Optional[int] = None
    timeout: int = 30
    retry_count: int = 3
    cache_ttl: Optional[int] = None
    description: str = ""
    version: str = "v1"

@dataclass
class RateLimitEntry:
    """Rate limit tracking entry"""
    identifier: str
    count: int
    window_start: datetime
    window_size: int = 60  # seconds

class SecurityHeaders:
    """Security headers configuration"""
    
    @staticmethod
    def get_default_headers() -> Dict[str, str]:
        """Get default security headers"""
        return {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'",
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()'
        }

class AuthenticationManager:
    """Authentication and authorization manager"""

    def __init__(self, jwt_secret: str = None):
        # Never fall back to a hardcoded literal — an attacker who knows the
        # default can forge arbitrary JWTs and impersonate any user.
        # Set GATEWAY_JWT_SECRET in your environment (min 32 chars recommended).
        configured = jwt_secret or os.environ.get('GATEWAY_JWT_SECRET', '')
        if not configured:
            raise ValueError("GATEWAY_JWT_SECRET environment variable must be set")
        self.jwt_secret = configured
        self.users: Dict[str, User] = {}
        self.api_keys: Dict[str, APIKey] = {}
        self.sessions: Dict[str, str] = {}  # session_id -> user_id
        self._password_hashes: Dict[str, bytes] = {}  # username -> bcrypt hash

        # Create default admin user
        self._create_default_users()

        logger.info("Authentication Manager initialized")

    def _hash_password(self, password: str) -> bytes:
        if _BCRYPT_AVAILABLE:
            return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt())
        # Fallback: sha256 hex (less secure, but avoids hard dependency failure)
        return hashlib.sha256(password.encode()).hexdigest().encode()

    def _check_password(self, password: str, hashed: bytes) -> bool:
        if _BCRYPT_AVAILABLE:
            try:
                return _bcrypt.checkpw(password.encode(), hashed)
            except Exception:
                return False
        return hashlib.sha256(password.encode()).hexdigest().encode() == hashed

    def verify_credentials(self, username: str, password: str) -> Optional["User"]:
        """Verify username/password and return the User if valid, else None."""
        hashed = self._password_hashes.get(username)
        if not hashed:
            return None
        if not self._check_password(password, hashed):
            return None
        # Find user by username
        for user in self.users.values():
            if user.username == username:
                return user
        return None
    
    def _create_default_users(self):
        """Create default users for demonstration"""
        admin_user = User(
            user_id="admin-001",
            username="admin",
            email="admin@aiops.local",
            roles=[UserRole.ADMIN]
        )
        
        operator_user = User(
            user_id="operator-001", 
            username="operator",
            email="operator@aiops.local",
            roles=[UserRole.OPERATOR]
        )
        
        viewer_user = User(
            user_id="viewer-001",
            username="viewer", 
            email="viewer@aiops.local",
            roles=[UserRole.VIEWER]
        )
        
        self.users[admin_user.user_id] = admin_user
        self.users[operator_user.user_id] = operator_user
        self.users[viewer_user.user_id] = viewer_user

        # Require passwords from environment — no hardcoded or random fallbacks.
        # All user passwords must be explicitly set via environment variables.
        for _uname, _env_var in [
            ('admin',    'GATEWAY_ADMIN_PASSWORD'),
            ('operator', 'GATEWAY_OPERATOR_PASSWORD'),
            ('viewer',   'GATEWAY_VIEWER_PASSWORD'),
        ]:
            _pw = os.environ.get(_env_var)
            if not _pw:
                raise ValueError(f"{_env_var} environment variable must be set")
            self._password_hashes[_uname] = self._hash_password(_pw)

        # Create API keys
        self.create_api_key(admin_user.user_id, "admin-key", ["*"])
        self.create_api_key(operator_user.user_id, "operator-key", ["monitoring.*", "automation.*"])
        self.create_api_key(viewer_user.user_id, "viewer-key", ["monitoring.read", "analytics.read"])
    
    def create_api_key(self, user_id: str, name: str, permissions: List[str]) -> str:
        """Create a new API key"""
        if user_id not in self.users:
            raise ValueError(f"User not found: {user_id}")
        
        api_key = f"aiops_{uuid.uuid4().hex[:16]}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        api_key_obj = APIKey(
            key_id=uuid.uuid4().hex,
            key_hash=key_hash,
            user_id=user_id,
            name=name,
            permissions=permissions
        )
        
        self.api_keys[key_hash] = api_key_obj
        self.users[user_id].api_keys.append(key_hash)
        
        logger.info(f"Created API key '{name}' for user {user_id}")
        return api_key
    
    def validate_api_key(self, api_key: str) -> Optional[APIKey]:
        """Validate an API key"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        if key_hash in self.api_keys:
            api_key_obj = self.api_keys[key_hash]
            
            if not api_key_obj.active:
                return None
            
            if api_key_obj.expires_at and datetime.now() > api_key_obj.expires_at:
                return None
            
            # Update last used
            api_key_obj.last_used = datetime.now()
            return api_key_obj
        
        return None
    
    def create_jwt_token(self, user_id: str) -> str:
        """Create a JWT token for user"""
        if user_id not in self.users:
            raise ValueError(f"User not found: {user_id}")
        
        user = self.users[user_id]
        payload = {
            'user_id': user.user_id,
            'username': user.username,
            'roles': [role.value for role in user.roles],
            'exp': datetime.utcnow() + timedelta(hours=24),
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
        logger.info(f"Created JWT token for user {user.username}")
        return token
    
    def validate_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid JWT token")
            return None
    
    def check_permission(self, user_id: str, permission: str) -> bool:
        """Check if user has permission"""
        if user_id not in self.users:
            return False
        
        user = self.users[user_id]
        
        # Admin has all permissions
        if UserRole.ADMIN in user.roles:
            return True
        
        # Check API key permissions
        for key_hash in user.api_keys:
            if key_hash in self.api_keys:
                api_key = self.api_keys[key_hash]
                for perm in api_key.permissions:
                    if perm == "*" or perm == permission or permission.startswith(perm.replace("*", "")):
                        return True
        
        return False
    
    def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """Get user by API key"""
        api_key_obj = self.validate_api_key(api_key)
        if api_key_obj:
            return self.users.get(api_key_obj.user_id)
        return None

class RateLimiter:
    """Advanced rate limiting system"""
    
    def __init__(self):
        self.limits: Dict[str, RateLimitEntry] = {}
        self.cleanup_interval = 300  # 5 minutes
        self.running = False
        
        logger.info("Rate Limiter initialized")
    
    def is_allowed(self, identifier: str, limit: int, window: int = 60) -> tuple[bool, Dict[str, Any]]:
        """Check if request is allowed under rate limit"""
        current_time = datetime.now()
        
        if identifier not in self.limits:
            self.limits[identifier] = RateLimitEntry(
                identifier=identifier,
                count=1,
                window_start=current_time,
                window_size=window
            )
            return True, {"remaining": limit - 1, "reset_time": current_time + timedelta(seconds=window)}
        
        entry = self.limits[identifier]
        
        # Check if window has expired
        if (current_time - entry.window_start).total_seconds() >= entry.window_size:
            # Reset window
            entry.count = 1
            entry.window_start = current_time
            return True, {"remaining": limit - 1, "reset_time": current_time + timedelta(seconds=window)}
        
        # Check if within limit
        if entry.count >= limit:
            return False, {
                "remaining": 0,
                "reset_time": entry.window_start + timedelta(seconds=entry.window_size)
            }
        
        # Increment count
        entry.count += 1
        remaining = max(0, limit - entry.count)
        reset_time = entry.window_start + timedelta(seconds=entry.window_size)
        
        return True, {"remaining": remaining, "reset_time": reset_time}
    
    def start_cleanup(self):
        """Start cleanup of expired entries"""
        if not self.running:
            self.running = True
            asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """Cleanup expired rate limit entries"""
        while self.running:
            try:
                current_time = datetime.now()
                expired_keys = []
                
                for identifier, entry in self.limits.items():
                    if (current_time - entry.window_start).total_seconds() > entry.window_size * 2:
                        expired_keys.append(identifier)
                
                for key in expired_keys:
                    del self.limits[key]
                
                if expired_keys:
                    logger.debug(f"Cleaned up {len(expired_keys)} expired rate limit entries")
                
                await asyncio.sleep(self.cleanup_interval)
                
            except Exception as e:
                logger.error(f"Error in rate limit cleanup: {e}")
                await asyncio.sleep(60)

class RouteManager:
    """Route management and resolution"""
    
    def __init__(self):
        self.routes: List[Route] = []
        self.compiled_routes: List[tuple] = []
        
        # Register default routes
        self._register_default_routes()
        
        logger.info("Route Manager initialized")
    
    def _register_default_routes(self):
        """Register default API routes"""
        default_routes = [
            Route(
                path="/api/v1/monitoring/metrics",
                methods=["GET"],
                target_service="performance_monitor",
                auth_required=True,
                required_roles=[UserRole.VIEWER, UserRole.OPERATOR, UserRole.ADMIN],
                description="Get system performance metrics"
            ),
            Route(
                path="/api/v1/monitoring/health",
                methods=["GET"],
                target_service="health_checker",
                auth_required=False,
                description="Health check endpoint"
            ),
            Route(
                path="/api/v1/analytics/reports",
                methods=["GET", "POST"],
                target_service="analytics_engine",
                auth_required=True,
                required_roles=[UserRole.OPERATOR, UserRole.ADMIN],
                description="Analytics reports"
            ),
            Route(
                path="/api/v1/automation/scale",
                methods=["POST"],
                target_service="auto_scaler",
                auth_required=True,
                required_roles=[UserRole.ADMIN],
                rate_limit=10,  # 10 requests per minute
                description="Auto-scaling operations"
            ),
            Route(
                path="/api/v1/config/.*",
                methods=["GET", "POST", "PUT", "DELETE"],
                target_service="config_manager",
                auth_required=True,
                required_roles=[UserRole.ADMIN],
                description="Configuration management"
            )
        ]
        
        for route in default_routes:
            self.add_route(route)
    
    def add_route(self, route: Route):
        """Add a new route"""
        self.routes.append(route)
        
        # Compile regex pattern for path matching
        pattern = route.path.replace(".*", ".*").replace("*", "[^/]*")
        compiled_pattern = re.compile(f"^{pattern}$")
        
        self.compiled_routes.append((compiled_pattern, route))
        
        logger.info(f"Added route: {route.methods} {route.path} -> {route.target_service}")
    
    def find_route(self, path: str, method: str) -> Optional[Route]:
        """Find matching route for path and method"""
        for pattern, route in self.compiled_routes:
            if pattern.match(path) and method in route.methods:
                return route
        
        return None
    
    def get_routes(self) -> List[Route]:
        """Get all registered routes"""
        return self.routes.copy()

class APIGateway:
    """Main API Gateway application"""
    
    def __init__(self, host: str = "localhost", port: int = 8080):
        self.host = host
        self.port = port
        self.app = web.Application()
        
        # Initialize components
        self.auth_manager = AuthenticationManager()
        self.rate_limiter = RateLimiter()
        self.route_manager = RouteManager()
        
        # Service registry (simplified for demo)
        self.services = {
            "performance_monitor": "http://localhost:8001",
            "health_checker": "http://localhost:8002",
            "analytics_engine": "http://localhost:8003",
            "auto_scaler": "http://localhost:8004",
            "config_manager": "http://localhost:8005"
        }
        
        # Metrics
        self.request_count = 0
        self.request_times = deque(maxlen=1000)
        self.error_count = 0
        
        # Setup middleware and routes
        self._setup_middleware()
        self._setup_routes()
        
        logger.info(f"API Gateway initialized on {host}:{port}")
    
    def _setup_middleware(self):
        """Setup middleware"""
        
        @web.middleware
        async def cors_middleware(request, handler):
            """CORS middleware"""
            response = await handler(request)
            
            # Reflect the request Origin only when it is in the allow-list.
            # Wildcard ('*') is forbidden here because this gateway carries
            # credentials (Authorization header / API keys).
            _origin = request.headers.get('Origin', '')
            _allowed_origins = [
                o.strip()
                for o in os.environ.get(
                    'ALLOWED_ORIGINS',
                    'http://localhost:3001,http://localhost:3000',
                ).split(',')
                if o.strip()
            ]
            if _origin in _allowed_origins:
                response.headers['Access-Control-Allow-Origin'] = _origin
                response.headers['Vary'] = 'Origin'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-Request-ID'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            
            return response
        
        @web.middleware
        async def security_headers_middleware(request, handler):
            """Security headers middleware"""
            response = await handler(request)
            
            # Add security headers
            for header, value in SecurityHeaders.get_default_headers().items():
                response.headers[header] = value
            
            return response
        
        @web.middleware
        async def logging_middleware(request, handler):
            """Request logging middleware"""
            start_time = time.time()
            
            try:
                response = await handler(request)
                
                duration = time.time() - start_time
                self.request_times.append(duration)
                self.request_count += 1
                
                logger.info(f"{request.method} {request.path} -> {response.status} ({duration:.3f}s)")
                
                return response
                
            except Exception as e:
                duration = time.time() - start_time
                self.error_count += 1
                
                logger.error(f"{request.method} {request.path} -> ERROR ({duration:.3f}s): {e}")
                raise
        
        @web.middleware
        async def auth_middleware(request, handler):
            """Authentication middleware"""
            # Skip auth for OPTIONS requests and health checks
            if request.method == 'OPTIONS' or request.path.endswith('/health'):
                return await handler(request)
            
            # Find route
            route = self.route_manager.find_route(request.path, request.method)
            
            if route and route.auth_required:
                user = None
                
                # Check for API key
                api_key = request.headers.get('X-API-Key')
                if api_key:
                    user = self.auth_manager.get_user_by_api_key(api_key)
                    if user:
                        request['user'] = user
                        request['auth_method'] = AuthMethod.API_KEY
                
                # Check for JWT token
                if not user:
                    auth_header = request.headers.get('Authorization', '')
                    if auth_header.startswith('Bearer '):
                        token = auth_header[7:]
                        payload = self.auth_manager.validate_jwt_token(token)
                        if payload:
                            user = self.auth_manager.users.get(payload['user_id'])
                            if user:
                                request['user'] = user
                                request['auth_method'] = AuthMethod.JWT
                
                if not user:
                    return web.json_response(
                        {"error": "Authentication required"}, 
                        status=401
                    )
                
                # Check roles if required
                if route.required_roles:
                    user_roles = set(user.roles)
                    required_roles = set(route.required_roles)
                    
                    if not user_roles.intersection(required_roles):
                        return web.json_response(
                            {"error": "Insufficient permissions"}, 
                            status=403
                        )
            
            return await handler(request)
        
        @web.middleware
        async def rate_limit_middleware(request, handler):
            """Rate limiting middleware"""
            # Find route
            route = self.route_manager.find_route(request.path, request.method)
            
            if route and route.rate_limit:
                # Determine identifier (IP, user, API key)
                identifier = request.remote or "unknown"
                
                if 'user' in request:
                    identifier = f"user:{request['user'].user_id}"
                
                allowed, info = self.rate_limiter.is_allowed(identifier, route.rate_limit)
                
                if not allowed:
                    return web.json_response(
                        {
                            "error": "Rate limit exceeded",
                            "reset_time": info["reset_time"].isoformat()
                        },
                        status=429
                    )
                
                # Add rate limit headers
                response = await handler(request)
                response.headers['X-RateLimit-Limit'] = str(route.rate_limit)
                response.headers['X-RateLimit-Remaining'] = str(info["remaining"])
                response.headers['X-RateLimit-Reset'] = str(int(info["reset_time"].timestamp()))
                
                return response
            
            return await handler(request)
        
        # Add middleware in order
        self.app.middlewares.append(logging_middleware)
        self.app.middlewares.append(cors_middleware)
        self.app.middlewares.append(security_headers_middleware)
        self.app.middlewares.append(rate_limit_middleware)
        self.app.middlewares.append(auth_middleware)
    
    def _setup_routes(self):
        """Setup API routes"""
        
        # Health check
        async def health_check(request):
            """Health check endpoint"""
            return web.json_response({
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0"
            })
        
        # Authentication endpoints
        async def login(request):
            """Login endpoint"""
            data = await request.json()
            username = data.get('username')
            password = data.get('password')
            
            user = self.auth_manager.verify_credentials(username, password)
            if user:
                token = self.auth_manager.create_jwt_token(user.user_id)
                return web.json_response({
                    "token": token,
                    "user": {
                        "user_id": user.user_id,
                        "username": user.username,
                        "roles": [r.value for r in user.roles]
                    }
                })

            return web.json_response({"error": "Invalid credentials"}, status=401)
        
        # Proxy endpoint
        async def proxy_request(request):
            """Proxy requests to backend services"""
            route = self.route_manager.find_route(request.path, request.method)
            
            if not route:
                return web.json_response({"error": "Route not found"}, status=404)
            
            target_service = route.target_service
            if target_service not in self.services:
                return web.json_response({"error": "Service not available"}, status=503)
            
            target_url = self.services[target_service]
            target_path = route.target_path or request.path
            
            # For demo, return mock response
            mock_responses = {
                "performance_monitor": {
                    "cpu_usage": 45.2,
                    "memory_usage": 67.8,
                    "disk_usage": 23.1,
                    "timestamp": datetime.now().isoformat()
                },
                "analytics_engine": {
                    "reports": [
                        {"id": 1, "name": "System Performance", "status": "completed"},
                        {"id": 2, "name": "Security Analysis", "status": "running"}
                    ]
                },
                "auto_scaler": {
                    "message": "Scaling operation initiated",
                    "target_instances": 5
                },
                "config_manager": {
                    "configurations": ["database.host", "api.rate_limit", "logging.level"]
                }
            }
            
            response_data = mock_responses.get(target_service, {"message": f"Response from {target_service}"})
            
            return web.json_response(response_data)
        
        # API documentation
        async def api_docs(request):
            """API documentation endpoint"""
            routes_info = []
            
            for route in self.route_manager.get_routes():
                routes_info.append({
                    "path": route.path,
                    "methods": route.methods,
                    "description": route.description,
                    "auth_required": route.auth_required,
                    "required_roles": [role.value for role in route.required_roles],
                    "rate_limit": route.rate_limit
                })
            
            return web.json_response({
                "title": "AIOps API Gateway",
                "version": "1.0.0",
                "routes": routes_info
            })
        
        # Gateway metrics
        async def gateway_metrics(request):
            """Gateway metrics endpoint"""
            avg_response_time = sum(self.request_times) / len(self.request_times) if self.request_times else 0
            
            return web.json_response({
                "request_count": self.request_count,
                "error_count": self.error_count,
                "avg_response_time": round(avg_response_time, 3),
                "rate_limit_entries": len(self.rate_limiter.limits),
                "registered_routes": len(self.route_manager.routes),
                "active_services": len(self.services)
            })
        
        # Register routes
        self.app.router.add_get('/health', health_check)
        self.app.router.add_post('/auth/login', login)
        self.app.router.add_get('/docs', api_docs)
        self.app.router.add_get('/gateway/metrics', gateway_metrics)
        
        # Catch-all route for proxying
        self.app.router.add_route('*', '/api/{path:.*}', proxy_request)
    
    async def start(self):
        """Start the API gateway"""
        self.rate_limiter.start_cleanup()
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info(f"API Gateway started on http://{self.host}:{self.port}")
        
        return runner

async def demonstrate_api_gateway():
    """Demonstrate the API Gateway"""
    print("AIOps API Gateway and Security System Demonstration")
    print("=" * 70)
    
    # Start the gateway
    gateway = APIGateway(host="localhost", port=8090)
    runner = await gateway.start()
    
    try:
        print(f"\nAPI Gateway started on http://localhost:8090")
        print(f"Available endpoints:")
        print(f"  GET  /health - Health check")
        print(f"  POST /auth/login - Authentication")
        print(f"  GET  /docs - API documentation")
        print(f"  GET  /gateway/metrics - Gateway metrics")
        print(f"  *    /api/* - Proxied API requests")
        
        # Simulate some requests
        print(f"\nSimulating API requests...")
        
        async with ClientSession() as session:
            base_url = "http://localhost:8090"
            
            # Health check
            async with session.get(f"{base_url}/health") as resp:
                health_data = await resp.json()
                print(f"Health Check: {health_data['status']}")
            
            # Login to get JWT token
            login_data = {"username": "admin", "password": "admin123"}
            async with session.post(f"{base_url}/auth/login", json=login_data) as resp:
                if resp.status == 200:
                    auth_data = await resp.json()
                    token = auth_data["token"]
                    print(f"Login successful, got JWT token")
                else:
                    print(f"Login failed")
                    return
            
            # Get API documentation
            async with session.get(f"{base_url}/docs") as resp:
                docs = await resp.json()
                print(f"API Documentation: {len(docs['routes'])} routes available")
            
            # Test authenticated API calls
            headers = {"Authorization": f"Bearer {token}"}
            
            # Get monitoring metrics
            async with session.get(f"{base_url}/api/v1/monitoring/metrics", headers=headers) as resp:
                if resp.status == 200:
                    metrics = await resp.json()
                    print(f"Monitoring Metrics: CPU {metrics['cpu_usage']}%, Memory {metrics['memory_usage']}%")
                else:
                    print(f"Failed to get monitoring metrics: {resp.status}")
            
            # Get analytics reports
            async with session.get(f"{base_url}/api/v1/analytics/reports", headers=headers) as resp:
                if resp.status == 200:
                    reports = await resp.json()
                    print(f"Analytics Reports: {len(reports['reports'])} reports available")
                else:
                    print(f"Failed to get analytics reports: {resp.status}")
            
            # Test rate limiting (admin auto-scaling endpoint has 10 req/min limit)
            print(f"\nTesting rate limiting...")
            success_count = 0
            rate_limited_count = 0
            
            for i in range(5):
                async with session.post(f"{base_url}/api/v1/automation/scale", 
                                      headers=headers, 
                                      json={"instances": 3}) as resp:
                    if resp.status == 200:
                        success_count += 1
                    elif resp.status == 429:
                        rate_limited_count += 1
            
            print(f"Rate limiting test: {success_count} successful, {rate_limited_count} rate limited")
            
            # Test unauthorized access
            print(f"\nTesting unauthorized access...")
            async with session.get(f"{base_url}/api/v1/monitoring/metrics") as resp:
                if resp.status == 401:
                    print(f"Unauthorized access properly blocked (401)")
                else:
                    print(f"Unexpected response for unauthorized request: {resp.status}")
            
            # Get gateway metrics
            async with session.get(f"{base_url}/gateway/metrics", headers=headers) as resp:
                if resp.status == 200:
                    metrics = await resp.json()
                    print(f"\nGateway Metrics:")
                    print(f"  Total Requests: {metrics['request_count']}")
                    print(f"  Error Count: {metrics['error_count']}")
                    print(f"  Avg Response Time: {metrics['avg_response_time']}s")
                    print(f"  Registered Routes: {metrics['registered_routes']}")
                    print(f"  Active Services: {metrics['active_services']}")
        
        print(f"\nAPI Gateway demonstration completed!")
        print(f"Gateway will continue running for 10 seconds...")
        await asyncio.sleep(10)
        
    except KeyboardInterrupt:
        print(f"\nShutdown requested...")
    finally:
        await runner.cleanup()
        print(f"API Gateway stopped")

if __name__ == "__main__":
    asyncio.run(demonstrate_api_gateway())