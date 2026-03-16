#!/usr/bin/env python3
"""
Real-time Data Streaming Service for AIOps Bot
Provides WebSocket-based real-time metrics streaming and alerts
"""

import asyncio
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("⚠️ websockets package not installed. Real-time streaming features will be limited.")
import json
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
import requests
import numpy as np
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high" 
    CRITICAL = "critical"

@dataclass
class MetricData:
    name: str
    value: float
    timestamp: datetime
    labels: Dict[str, str] = None
    
@dataclass
class Alert:
    metric_name: str
    severity: AlertSeverity
    message: str
    value: float
    threshold: float
    timestamp: datetime
    correlation_id: str = None

class RealTimeMetricsStreamer:
    """Real-time metrics streaming and alerting service"""
    
    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        self.prometheus_url = prometheus_url
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.metrics_cache: Dict[str, List[MetricData]] = {}
        self.alert_history: List[Alert] = []
        self.streaming_active = False
        self.stream_interval = 5  # seconds
        
        # Metrics to stream
        self.streaming_metrics = [
            'system_cpu_usage_percent',
            'system_memory_usage_percent', 
            'system_disk_usage_percent',
            'app_response_time_seconds',
            'app_error_rate_percent',
            'app_throughput_requests_per_sec',
            'http_requests_total',
            'user_sessions_active'
        ]
        
        # Load analytics service with adaptive ML
        try:
            import sys
            sys.path.append('./bot')
            from bot.analytics_service import analytics_service
            self.analytics = analytics_service
            logger.info("🧠 Analytics service with adaptive ML loaded")
        except Exception as e:
            logger.error(f"⚠️ Could not load analytics service: {e}")
            self.analytics = None
        
        # Dynamic thresholds (calculated from real data via analytics service)
        self.dynamic_thresholds = {}
        self._load_dynamic_thresholds()
        
        logger.info("🔄 Real-time Metrics Streamer initialized")
        logger.info(f"📊 Streaming {len(self.streaming_metrics)} metrics every {self.stream_interval}s")
    
    def _load_dynamic_thresholds(self):
        """Load dynamic thresholds from analytics service or use intelligent defaults"""
        try:
            if self.analytics:
                logger.info("🎯 Loading dynamic thresholds from analytics service")
                # Get sample data to calculate thresholds
                for metric in self.streaming_metrics:
                    try:
                        # Get dynamic threshold from analytics service
                        threshold = self.analytics.get_metric_threshold(metric, 'alert')
                        if threshold:
                            warning_threshold = threshold.get('warning', self._get_intelligent_default(metric, 'warning'))
                            critical_threshold = threshold.get('critical', self._get_intelligent_default(metric, 'critical'))
                            
                            self.dynamic_thresholds[metric] = {
                                'warning': warning_threshold,
                                'critical': critical_threshold
                            }
                            logger.info(f"   ✅ {metric}: Warning={warning_threshold:.1f}, Critical={critical_threshold:.1f}")
                        else:
                            # Use intelligent defaults
                            self.dynamic_thresholds[metric] = self._get_intelligent_default_thresholds(metric)
                            logger.info(f"   🔧 {metric}: Using intelligent defaults")
                    except Exception as e:
                        logger.debug(f"   ⚠️ Could not get threshold for {metric}: {e}")
                        self.dynamic_thresholds[metric] = self._get_intelligent_default_thresholds(metric)
                        
                logger.info(f"🎯 Loaded dynamic thresholds for {len(self.dynamic_thresholds)} metrics")
            else:
                logger.warning("⚠️ Analytics service not available, using intelligent defaults")
                for metric in self.streaming_metrics:
                    self.dynamic_thresholds[metric] = self._get_intelligent_default_thresholds(metric)
                    
        except Exception as e:
            logger.error(f"❌ Error loading dynamic thresholds: {e}")
            # Fallback to intelligent defaults
            for metric in self.streaming_metrics:
                self.dynamic_thresholds[metric] = self._get_intelligent_default_thresholds(metric)
    
    def _get_intelligent_default_thresholds(self, metric_name: str) -> dict:
        """Get intelligent default thresholds based on metric type"""
        if 'cpu' in metric_name.lower():
            return {'warning': 75.0, 'critical': 85.0}  # Conservative CPU thresholds
        elif 'memory' in metric_name.lower():
            return {'warning': 80.0, 'critical': 90.0}  # Memory thresholds
        elif 'disk' in metric_name.lower():
            return {'warning': 85.0, 'critical': 95.0}  # Disk space thresholds
        elif 'response_time' in metric_name.lower():
            return {'warning': 0.5, 'critical': 1.0}    # Response time in seconds
        elif 'error_rate' in metric_name.lower():
            return {'warning': 2.0, 'critical': 5.0}    # Error rate percentage
        elif 'throughput' in metric_name.lower():
            return {'low_warning': 50, 'low_critical': 20}  # Requests per second
        elif 'sessions' in metric_name.lower():
            return {'low_warning': 10, 'low_critical': 5}   # Active sessions
        else:
            return {'warning': 80.0, 'critical': 90.0}  # Generic percentage thresholds
    
    def _get_intelligent_default(self, metric_name: str, level: str) -> float:
        """Get individual threshold value"""
        thresholds = self._get_intelligent_default_thresholds(metric_name)
        return thresholds.get(level, thresholds.get('warning', 80.0))
    
    def update_dynamic_thresholds(self):
        """Update thresholds from analytics service periodically"""
        try:
            if self.analytics:
                logger.info("🔄 Updating dynamic thresholds from analytics service")
                updated_count = 0
                
                for metric in self.streaming_metrics:
                    try:
                        # Get latest threshold from analytics
                        threshold = self.analytics.get_metric_threshold(metric, 'alert')
                        if threshold:
                            old_warning = self.dynamic_thresholds.get(metric, {}).get('warning', 0)
                            new_warning = threshold.get('warning', old_warning)
                            
                            if abs(new_warning - old_warning) > 0.1:  # Significant change
                                self.dynamic_thresholds[metric] = {
                                    'warning': threshold.get('warning', new_warning),
                                    'critical': threshold.get('critical', new_warning * 1.2)
                                }
                                updated_count += 1
                                logger.info(f"   🎯 Updated {metric}: {old_warning:.1f} -> {new_warning:.1f}")
                                
                    except Exception as e:
                        logger.debug(f"   ⚠️ Could not update threshold for {metric}: {e}")
                
                if updated_count > 0:
                    logger.info(f"✅ Updated {updated_count} dynamic thresholds")
                else:
                    logger.info("✅ All thresholds are current")
                    
        except Exception as e:
            logger.error(f"❌ Error updating dynamic thresholds: {e}")
    
    async def register_client(self, websocket, path):
        """Register a new WebSocket client"""
        self.connected_clients.add(websocket)
        client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"📱 Client connected: {client_info} (total: {len(self.connected_clients)})")
        
        try:
            # Send initial data
            await self.send_initial_data(websocket)
            
            # Handle client messages
            async for message in websocket:
                await self.handle_client_message(websocket, message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"📱 Client disconnected: {client_info}")
        except Exception as e:
            logger.error(f"❌ Error handling client {client_info}: {e}")
        finally:
            self.connected_clients.discard(websocket)
    
    async def send_initial_data(self, websocket: websockets.WebSocketServerProtocol):
        """Send initial data to newly connected client"""
        try:
            # Send current metrics
            current_metrics = await self.get_current_metrics()
            await websocket.send(json.dumps({
                'type': 'initial_metrics',
                'data': current_metrics,
                'timestamp': datetime.now().isoformat()
            }))
            
            # Send recent alerts
            recent_alerts = self.get_recent_alerts(hours=1)
            await websocket.send(json.dumps({
                'type': 'recent_alerts',
                'data': [self.alert_to_dict(alert) for alert in recent_alerts],
                'timestamp': datetime.now().isoformat()
            }))
            
            # Send streaming configuration
            await websocket.send(json.dumps({
                'type': 'config',
                'data': {
                    'stream_interval': self.stream_interval,
                    'metrics': self.streaming_metrics,
                    'thresholds': self.dynamic_thresholds
                },
                'timestamp': datetime.now().isoformat()
            }))
            
        except Exception as e:
            logger.error(f"❌ Error sending initial data: {e}")
    
    async def handle_client_message(self, websocket: websockets.WebSocketServerProtocol, message: str):
        """Handle messages from WebSocket clients"""
        try:
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type == 'subscribe_metric':
                metric_name = data.get('metric_name')
                if metric_name and metric_name not in self.streaming_metrics:
                    self.streaming_metrics.append(metric_name)
                    logger.info(f"📊 Added metric to stream: {metric_name}")
                    
            elif message_type == 'unsubscribe_metric':
                metric_name = data.get('metric_name')
                if metric_name in self.streaming_metrics:
                    self.streaming_metrics.remove(metric_name)
                    logger.info(f"📊 Removed metric from stream: {metric_name}")
                    
            elif message_type == 'update_threshold':
                metric_name = data.get('metric_name')
                threshold_type = data.get('threshold_type')
                value = data.get('value')
                
                if metric_name and threshold_type and value is not None:
                    if metric_name not in self.dynamic_thresholds:
                        self.dynamic_thresholds[metric_name] = {}
                    self.dynamic_thresholds[metric_name][threshold_type] = value
                    logger.info(f"🎯 Updated threshold: {metric_name}.{threshold_type} = {value}")
                    
            elif message_type == 'get_metric_history':
                metric_name = data.get('metric_name')
                hours = data.get('hours', 1)
                history = await self.get_metric_history(metric_name, hours)
                
                await websocket.send(json.dumps({
                    'type': 'metric_history',
                    'metric_name': metric_name,
                    'data': history,
                    'timestamp': datetime.now().isoformat()
                }))
                
        except json.JSONDecodeError:
            logger.error("❌ Invalid JSON message from client")
        except Exception as e:
            logger.error(f"❌ Error handling client message: {e}")
    
    async def get_current_metrics(self) -> Dict[str, Any]:
        """Get current values for all streaming metrics"""
        current_metrics = {}
        
        for metric_name in self.streaming_metrics:
            try:
                # Query Prometheus for current value
                response = requests.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={'query': metric_name},
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('data', {}).get('result'):
                        result = data['data']['result'][0]
                        value = float(result['value'][1])
                        
                        current_metrics[metric_name] = {
                            'value': value,
                            'timestamp': datetime.now().isoformat(),
                            'labels': result.get('metric', {})
                        }
                        
                        # Store in cache
                        if metric_name not in self.metrics_cache:
                            self.metrics_cache[metric_name] = []
                        
                        self.metrics_cache[metric_name].append(
                            MetricData(metric_name, value, datetime.now())
                        )
                        
                        # Keep only last 1000 points per metric
                        if len(self.metrics_cache[metric_name]) > 1000:
                            self.metrics_cache[metric_name] = self.metrics_cache[metric_name][-1000:]
                            
            except Exception as e:
                logger.error(f"❌ Error getting metric {metric_name}: {e}")
                # Use cached value if available
                if metric_name in self.metrics_cache and self.metrics_cache[metric_name]:
                    last_value = self.metrics_cache[metric_name][-1]
                    current_metrics[metric_name] = {
                        'value': last_value.value,
                        'timestamp': last_value.timestamp.isoformat(),
                        'labels': {},
                        'cached': True
                    }
        
        return current_metrics
    
    async def get_metric_history(self, metric_name: str, hours: int = 1) -> List[Dict[str, Any]]:
        """Get historical data for a specific metric"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query_range",
                params={
                    'query': metric_name,
                    'start': start_time.timestamp(),
                    'end': end_time.timestamp(),
                    'step': '30s'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data', {}).get('result'):
                    result = data['data']['result'][0]
                    return [
                        {
                            'timestamp': datetime.fromtimestamp(float(ts)).isoformat(),
                            'value': float(val)
                        }
                        for ts, val in result.get('values', [])
                    ]
            
            # Fallback to cached data
            if metric_name in self.metrics_cache:
                cutoff = datetime.now() - timedelta(hours=hours)
                return [
                    {
                        'timestamp': point.timestamp.isoformat(),
                        'value': point.value
                    }
                    for point in self.metrics_cache[metric_name]
                    if point.timestamp >= cutoff
                ]
                
        except Exception as e:
            logger.error(f"❌ Error getting history for {metric_name}: {e}")
        
        return []
    
    def check_alerts(self, metric_name: str, value: float) -> Optional[Alert]:
        """Check if a metric value triggers an alert"""
        thresholds = self.dynamic_thresholds.get(metric_name, {})
        
        # Check critical thresholds first
        if 'critical' in thresholds and value > thresholds['critical']:
            return Alert(
                metric_name=metric_name,
                severity=AlertSeverity.CRITICAL,
                message=f"{metric_name} is critically high",
                value=value,
                threshold=thresholds['critical'],
                timestamp=datetime.now()
            )
        
        if 'low_critical' in thresholds and value < thresholds['low_critical']:
            return Alert(
                metric_name=metric_name,
                severity=AlertSeverity.CRITICAL,
                message=f"{metric_name} is critically low",
                value=value,
                threshold=thresholds['low_critical'],
                timestamp=datetime.now()
            )
        
        # Check warning thresholds
        if 'warning' in thresholds and value > thresholds['warning']:
            return Alert(
                metric_name=metric_name,
                severity=AlertSeverity.HIGH,
                message=f"{metric_name} is above warning threshold",
                value=value,
                threshold=thresholds['warning'],
                timestamp=datetime.now()
            )
        
        if 'low_warning' in thresholds and value < thresholds['low_warning']:
            return Alert(
                metric_name=metric_name,
                severity=AlertSeverity.MEDIUM,
                message=f"{metric_name} is below warning threshold",
                value=value,
                threshold=thresholds['low_warning'],
                timestamp=datetime.now()
            )
        
        return None
    
    def alert_to_dict(self, alert: Alert) -> Dict[str, Any]:
        """Convert Alert object to dictionary"""
        return {
            'metric_name': alert.metric_name,
            'severity': alert.severity.value,
            'message': alert.message,
            'value': alert.value,
            'threshold': alert.threshold,
            'timestamp': alert.timestamp.isoformat(),
            'correlation_id': alert.correlation_id
        }
    
    def get_recent_alerts(self, hours: int = 1) -> List[Alert]:
        """Get recent alerts within specified time window"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [alert for alert in self.alert_history if alert.timestamp >= cutoff]
    
    async def broadcast_metrics(self):
        """Broadcast current metrics to all connected clients"""
        if not self.connected_clients:
            return
        
        try:
            current_metrics = await self.get_current_metrics()
            alerts = []
            ml_status = None
            insights = []
            
            # Check for alerts and get ML insights
            for metric_name, metric_data in current_metrics.items():
                value = metric_data['value']
                alert = self.check_alerts(metric_name, value)
                if alert:
                    self.alert_history.append(alert)
                    alerts.append(self.alert_to_dict(alert))
                    
                    # Keep alert history under control
                    if len(self.alert_history) > 1000:
                        self.alert_history = self.alert_history[-500:]
                
                # Get ML insights if analytics service is available
                if self.analytics and len(current_metrics) >= 3:  # Have enough data
                    try:
                        # Create DataFrame for analytics
                        import pandas as pd
                        recent_data = pd.DataFrame([{
                            'timestamp': pd.to_datetime(metric_data['timestamp']),
                            'value': value
                        }])
                        
                        # Get anomaly detection result
                        anomaly_result = self.analytics.detect_anomalies(metric_name, recent_data)
                        if anomaly_result.get('anomaly_detected'):
                            ml_alert = {
                                'metric': metric_name,
                                'message': f"ML detected anomaly in {metric_name}",
                                'severity': anomaly_result.get('severity', 'medium'),
                                'confidence': anomaly_result.get('confidence', 0),
                                'details': f"Anomaly score: {anomaly_result.get('avg_anomaly_score', 0):.3f}"
                            }
                            alerts.append(ml_alert)
                        
                        # Add ML activity flag to metric
                        metric_data['ml_active'] = True
                        metric_data['ml_confidence'] = anomaly_result.get('confidence', 0)
                        
                    except Exception as e:
                        logger.debug(f"ML analysis error for {metric_name}: {e}")
            
            # Get ML status
            if self.analytics:
                try:
                    ml_status = self.analytics.get_adaptive_ml_status()
                except Exception as e:
                    logger.debug(f"Error getting ML status: {e}")
            
            # Send metrics update
            metrics_message = {
                'type': 'metrics',
                'data': current_metrics,
                'timestamp': datetime.now().isoformat()
            }
            
            # Send alerts if any
            if alerts:
                alerts_message = {
                    'type': 'alert',
                    'data': alerts[-1] if alerts else None,  # Send latest alert
                    'timestamp': datetime.now().isoformat()
                }
            
            # Send ML status periodically (every 10th call)
            if ml_status and hasattr(self, '_broadcast_count'):
                self._broadcast_count = getattr(self, '_broadcast_count', 0) + 1
                if self._broadcast_count % 10 == 0:
                    ml_message = {
                        'type': 'ml_status',
                        'data': ml_status,
                        'timestamp': datetime.now().isoformat()
                    }
            else:
                self._broadcast_count = 1
            
            # Broadcast to all clients
            disconnected = set()
            messages_to_send = [metrics_message]
            if alerts:
                messages_to_send.append(alerts_message)
            if ml_status and hasattr(self, '_broadcast_count') and self._broadcast_count % 10 == 0:
                messages_to_send.append(ml_message)
            
            for client in self.connected_clients:
                try:
                    for message in messages_to_send:
                        await client.send(json.dumps(message))
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(client)
                except Exception as e:
                    logger.error(f"❌ Error broadcasting to client: {e}")
                    disconnected.add(client)
            
            # Remove disconnected clients
            self.connected_clients -= disconnected
            
            if alerts:
                logger.info(f"🚨 Broadcasted {len(alerts)} alerts to {len(self.connected_clients)} clients")
                
        except Exception as e:
            logger.error(f"❌ Error broadcasting metrics: {e}")
            logger.error(f"❌ Error broadcasting metrics: {e}")
    
    async def streaming_loop(self):
        """Main streaming loop with periodic threshold updates"""
        self.streaming_active = True
        logger.info("🔄 Starting metrics streaming loop")
        
        loop_count = 0
        threshold_update_interval = 60  # Update thresholds every 60 loops (5 minutes if 5s interval)
        
        while self.streaming_active:
            try:
                # Broadcast metrics
                await self.broadcast_metrics()
                
                # Periodically update dynamic thresholds
                loop_count += 1
                if loop_count % threshold_update_interval == 0:
                    self.update_dynamic_thresholds()
                    loop_count = 0  # Reset counter
                
                await asyncio.sleep(self.stream_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in streaming loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
        
        logger.info("⏹️ Metrics streaming loop stopped")
    
    def start_streaming(self):
        """Start streaming in a separate thread"""
        def run_streaming():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.streaming_loop())
        
        streaming_thread = threading.Thread(target=run_streaming, daemon=True)
        streaming_thread.start()
        logger.info("🚀 Metrics streaming started in background thread")
    
    def stop_streaming(self):
        """Stop the streaming loop"""
        self.streaming_active = False
        logger.info("⏹️ Stopping metrics streaming")

async def websocket_server(streamer: RealTimeMetricsStreamer, host: str = "0.0.0.0", port: int = 8765):
    """WebSocket server for real-time metrics"""
    logger.info(f"🌐 Starting WebSocket server on {host}:{port}")
    
    async with websockets.serve(streamer.register_client, host, port):
        logger.info("✅ WebSocket server started successfully")
        await asyncio.Future()  # Run forever

def main():
    """Main function to start the real-time streaming service"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Real-time metrics streaming service')
    parser.add_argument('--prometheus-url', default='http://localhost:9090',
                       help='Prometheus URL (default: http://localhost:9090)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='WebSocket server host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8765,
                       help='WebSocket server port (default: 8765)')
    parser.add_argument('--interval', type=int, default=5,
                       help='Streaming interval in seconds (default: 5)')
    
    args = parser.parse_args()
    
    print("🔄 AIOps Real-time Metrics Streaming Service")
    print(f"📊 Prometheus: {args.prometheus_url}")
    print(f"🌐 WebSocket: ws://{args.host}:{args.port}")
    print(f"⏱️ Interval: {args.interval}s")
    
    # Create streamer
    streamer = RealTimeMetricsStreamer(args.prometheus_url)
    streamer.stream_interval = args.interval
    
    # Start streaming
    streamer.start_streaming()
    
    try:
        # Start WebSocket server
        asyncio.run(websocket_server(streamer, args.host, args.port))
    except KeyboardInterrupt:
        print("\n⏹️ Stopping real-time streaming service...")
        streamer.stop_streaming()
    except Exception as e:
        logger.error(f"❌ Error starting server: {e}")

if __name__ == "__main__":
    main()