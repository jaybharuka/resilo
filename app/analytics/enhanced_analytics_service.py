#!/usr/bin/env python3
"""
Enhanced Analytics Service with Alert Correlation
Provides intelligent threshold analysis and alert correlation capabilities
"""

import json
import logging
import statistics
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

# Import alert correlation system
try:
    from alert_correlation import Alert, AlertCorrelationEngine
    CORRELATION_AVAILABLE = True
except ImportError:
    CORRELATION_AVAILABLE = False
    print("⚠️ Alert correlation not available - some features disabled")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedAnalyticsService:
    """Analytics service with intelligent alert correlation"""
    
    def __init__(self, prometheus_url="http://localhost:9090"):
        self.prometheus_url = prometheus_url
        self.historical_data = {}
        self.dynamic_thresholds = {}
        self.baseline_metrics = {}
        
        # Initialize correlation engine if available
        if CORRELATION_AVAILABLE:
            self.correlation_engine = AlertCorrelationEngine()
            logger.info("🔗 Alert correlation engine initialized")
        else:
            self.correlation_engine = None
        
        # Background thread for continuous analysis
        self.analysis_thread = None
        self.running = False
        
        logger.info("📊 Enhanced Analytics Service initialized")
    
    def start_continuous_analysis(self):
        """Start continuous monitoring and analysis"""
        if self.running:
            return
        
        self.running = True
        self.analysis_thread = threading.Thread(target=self._continuous_analysis, daemon=True)
        self.analysis_thread.start()
        logger.info("🔄 Continuous analysis started")
    
    def stop_continuous_analysis(self):
        """Stop continuous analysis"""
        self.running = False
        if self.analysis_thread:
            self.analysis_thread.join()
        logger.info("⏹️ Continuous analysis stopped")
    
    def _continuous_analysis(self):
        """Main loop for continuous analysis"""
        while self.running:
            try:
                # Update dynamic thresholds
                self._update_dynamic_thresholds()
                
                # Check for alert conditions
                self._check_alert_conditions()
                
                # Clean up old correlation data
                if self.correlation_engine:
                    self.correlation_engine.cleanup_old_alerts(max_age_hours=2)
                
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"❌ Error in continuous analysis: {e}")
                time.sleep(60)  # Wait longer on error
    
    def query_prometheus(self, query: str, time_range: str = "5m") -> Optional[dict]:
        """Query Prometheus with error handling"""
        try:
            url = f"{self.prometheus_url}/api/v1/query"
            params = {
                'query': query,
                'time': datetime.now().isoformat()
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data['status'] == 'success':
                return data['data']
            else:
                logger.warning(f"⚠️ Prometheus query failed: {data.get('error', 'Unknown error')}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"❌ Failed to query Prometheus: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error parsing Prometheus response: {e}")
            return None
    
    def get_metric_statistics(self, metric: str, hours: int = 24) -> Dict:
        """Get comprehensive statistics for a metric"""
        try:
            # Query metric data
            query = f"{metric}[{hours}h]"
            data = self.query_prometheus(query)
            
            if not data or not data.get('result'):
                return self._get_fallback_stats(metric)
            
            # Extract values
            values = []
            for result in data['result']:
                if 'values' in result:
                    values.extend([float(v[1]) for v in result['values']])
                elif 'value' in result:
                    values.append(float(result['value'][1]))
            
            if not values:
                return self._get_fallback_stats(metric)
            
            # Calculate statistics
            stats = {
                'mean': np.mean(values),
                'median': np.median(values),
                'std': np.std(values),
                'min': np.min(values),
                'max': np.max(values),
                'p95': np.percentile(values, 95),
                'p99': np.percentile(values, 99),
                'count': len(values),
                'metric': metric,
                'timestamp': datetime.now().isoformat()
            }
            
            # Store for future use
            self.historical_data[metric] = stats
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting statistics for {metric}: {e}")
            return self._get_fallback_stats(metric)
    
    def _get_fallback_stats(self, metric: str) -> Dict:
        """Get fallback statistics when Prometheus is unavailable"""
        # Use stored historical data if available
        if metric in self.historical_data:
            stored = self.historical_data[metric]
            logger.info(f"📊 Using cached statistics for {metric}")
            return stored
        
        # Generate intelligent defaults based on metric type
        if "cpu" in metric.lower() or "percent" in metric.lower():
            return {
                'mean': 45.0, 'median': 42.0, 'std': 15.0,
                'min': 10.0, 'max': 85.0, 'p95': 75.0, 'p99': 80.0,
                'count': 100, 'metric': metric,
                'timestamp': datetime.now().isoformat()
            }
        elif "memory" in metric.lower():
            return {
                'mean': 65.0, 'median': 63.0, 'std': 20.0,
                'min': 30.0, 'max': 92.0, 'p95': 85.0, 'p99': 90.0,
                'count': 100, 'metric': metric,
                'timestamp': datetime.now().isoformat()
            }
        elif "response" in metric.lower() or "latency" in metric.lower():
            return {
                'mean': 0.15, 'median': 0.12, 'std': 0.08,
                'min': 0.05, 'max': 0.8, 'p95': 0.3, 'p99': 0.5,
                'count': 100, 'metric': metric,
                'timestamp': datetime.now().isoformat()
            }
        else:
            return {
                'mean': 50.0, 'median': 48.0, 'std': 12.0,
                'min': 20.0, 'max': 80.0, 'p95': 70.0, 'p99': 75.0,
                'count': 100, 'metric': metric,
                'timestamp': datetime.now().isoformat()
            }
    
    def calculate_dynamic_threshold(self, metric: str, sensitivity: float = 1.0) -> Dict:
        """Calculate dynamic threshold with enhanced intelligence"""
        try:
            stats = self.get_metric_statistics(metric)
            
            # Base threshold calculation
            base_threshold = stats['mean'] + (sensitivity * stats['std'])
            
            # Adjust based on metric type and patterns
            if "cpu" in metric.lower() or "memory" in metric.lower():
                # For resource metrics, use percentile-based approach
                threshold = min(stats['p95'], base_threshold)
                # Never go below 80% for critical resources
                if "cpu" in metric.lower():
                    threshold = max(threshold, 80.0)
                elif "memory" in metric.lower():
                    threshold = max(threshold, 85.0)
            
            elif "error" in metric.lower() or "failure" in metric.lower():
                # For error metrics, be more sensitive
                threshold = stats['mean'] + (0.5 * stats['std'])
                threshold = max(threshold, 1.0)  # At least 1%
            
            elif "response" in metric.lower() or "latency" in metric.lower():
                # For performance metrics, use p90
                threshold = max(stats['p95'], stats['mean'] + (1.5 * stats['std']))
            
            else:
                # Default calculation
                threshold = base_threshold
            
            # Ensure reasonable bounds
            threshold = max(threshold, stats['min'] * 1.1)
            threshold = min(threshold, stats['max'] * 0.9)
            
            threshold_info = {
                'value': float(threshold),
                'metric': metric,
                'sensitivity': sensitivity,
                'stats': stats,
                'calculation_method': 'dynamic_statistical',
                'confidence': self._calculate_threshold_confidence(stats),
                'last_updated': datetime.now().isoformat()
            }
            
            # Store threshold
            self.dynamic_thresholds[metric] = threshold_info
            
            logger.info(f"📊 Dynamic threshold for {metric}: {threshold:.2f}")
            return threshold_info
            
        except Exception as e:
            logger.error(f"❌ Error calculating dynamic threshold for {metric}: {e}")
            return self._get_fallback_threshold(metric)
    
    def _calculate_threshold_confidence(self, stats: Dict) -> float:
        """Calculate confidence level for threshold"""
        try:
            # Higher confidence with more data points
            data_confidence = min(stats['count'] / 100.0, 1.0)
            
            # Lower confidence with high variability
            if stats['std'] > 0:
                variability_factor = 1.0 - min(stats['std'] / stats['mean'], 0.5)
            else:
                variability_factor = 1.0
            
            # Recent data is more reliable
            recency_factor = 0.9  # Assume recent data
            
            confidence = data_confidence * variability_factor * recency_factor
            return max(0.1, min(1.0, confidence))
            
        except Exception:
            return 0.5  # Default confidence
    
    def _get_fallback_threshold(self, metric: str) -> Dict:
        """Get fallback threshold when calculation fails"""
        if "cpu" in metric.lower():
            value = 80.0
        elif "memory" in metric.lower():
            value = 85.0
        elif "disk" in metric.lower():
            value = 80.0
        elif "error" in metric.lower():
            value = 5.0
        elif "response" in metric.lower():
            value = 1.0
        else:
            value = 100.0
        
        return {
            'value': value,
            'metric': metric,
            'sensitivity': 1.0,
            'stats': self._get_fallback_stats(metric),
            'calculation_method': 'fallback',
            'confidence': 0.3,
            'last_updated': datetime.now().isoformat()
        }
    
    def _update_dynamic_thresholds(self):
        """Update all dynamic thresholds"""
        try:
            # Common metrics to monitor
            metrics = [
                "system_cpu_usage_percent",
                "system_memory_usage_percent", 
                "system_disk_usage_percent",
                "app_response_time_seconds",
                "app_error_rate_percent",
                "app_throughput_requests_per_sec"
            ]
            
            for metric in metrics:
                self.calculate_dynamic_threshold(metric)
            
            logger.info(f"🔄 Updated {len(metrics)} dynamic thresholds")
            
        except Exception as e:
            logger.error(f"❌ Error updating dynamic thresholds: {e}")
    
    def _check_alert_conditions(self):
        """Check current metrics against thresholds and generate alerts"""
        if not self.correlation_engine:
            return
        
        try:
            for metric, threshold_info in self.dynamic_thresholds.items():
                # Get current value
                current_data = self.query_prometheus(metric)
                
                if not current_data or not current_data.get('result'):
                    continue
                
                # Extract current value
                current_value = None
                for result in current_data['result']:
                    if 'value' in result:
                        current_value = float(result['value'][1])
                        break
                
                if current_value is None:
                    continue
                
                # Check if threshold is exceeded
                threshold_value = threshold_info['value']
                if current_value > threshold_value:
                    # Determine severity
                    severity = self._determine_severity(current_value, threshold_value, metric)
                    
                    # Create alert
                    alert = Alert(
                        id=f"{metric}_{int(datetime.now().timestamp())}",
                        metric=metric,
                        severity=severity,
                        value=current_value,
                        threshold=threshold_value,
                        message=f"{metric} exceeded threshold: {current_value:.2f} > {threshold_value:.2f}",
                        timestamp=datetime.now()
                    )
                    
                    # Add to correlation engine
                    self.correlation_engine.add_alert(alert)
                    
                    logger.info(f"🚨 Alert generated: {metric} = {current_value:.2f} (threshold: {threshold_value:.2f})")
            
        except Exception as e:
            logger.error(f"❌ Error checking alert conditions: {e}")
    
    def _determine_severity(self, value: float, threshold: float, metric: str) -> str:
        """Determine alert severity based on threshold exceeded"""
        try:
            ratio = value / threshold
            
            if ratio >= 1.5:  # 50% above threshold
                return "critical"
            elif ratio >= 1.2:  # 20% above threshold
                return "warning"
            else:
                return "info"
                
        except Exception:
            return "warning"
    
    def get_correlation_summary(self) -> Dict:
        """Get summary of alert correlations"""
        if not self.correlation_engine:
            return {"error": "Correlation engine not available"}
        
        try:
            return self.correlation_engine.get_correlation_summary()
        except Exception as e:
            logger.error(f"❌ Error getting correlation summary: {e}")
            return {"error": str(e)}
    
    def get_root_cause_analysis(self) -> List[Dict]:
        """Get root cause analysis"""
        if not self.correlation_engine:
            return []
        
        try:
            return self.correlation_engine.get_root_cause_analysis()
        except Exception as e:
            logger.error(f"❌ Error getting root cause analysis: {e}")
            return []
    
    def get_active_alerts(self, include_suppressed: bool = False) -> List[Dict]:
        """Get active alerts"""
        if not self.correlation_engine:
            return []
        
        try:
            alerts = self.correlation_engine.get_active_alerts(include_suppressed)
            return [alert.to_dict() for alert in alerts]
        except Exception as e:
            logger.error(f"❌ Error getting active alerts: {e}")
            return []
    
    def get_threshold_info(self, metric: str) -> Dict:
        """Get threshold information for a metric"""
        if metric in self.dynamic_thresholds:
            return self.dynamic_thresholds[metric]
        else:
            # Calculate on demand
            return self.calculate_dynamic_threshold(metric)
    
    def get_all_thresholds(self) -> Dict:
        """Get all current dynamic thresholds"""
        return dict(self.dynamic_thresholds)
    
    def health_check(self) -> Dict:
        """Health check for the analytics service"""
        try:
            # Test Prometheus connectivity
            prometheus_ok = False
            try:
                response = requests.get(f"{self.prometheus_url}/api/v1/query", 
                                      params={'query': 'up'}, timeout=5)
                prometheus_ok = response.status_code == 200
            except:
                pass
            
            # Check correlation engine
            correlation_ok = self.correlation_engine is not None
            
            # Check analysis thread
            analysis_ok = self.running and (self.analysis_thread is not None)
            
            status = {
                'service': 'analytics',
                'status': 'healthy' if all([prometheus_ok, correlation_ok]) else 'degraded',
                'prometheus_connection': prometheus_ok,
                'correlation_engine': correlation_ok,
                'continuous_analysis': analysis_ok,
                'active_thresholds': len(self.dynamic_thresholds),
                'timestamp': datetime.now().isoformat()
            }
            
            if self.correlation_engine:
                status['correlation_summary'] = self.get_correlation_summary()
            
            return status
            
        except Exception as e:
            return {
                'service': 'analytics',
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

def main():
    """Test the enhanced analytics service"""
    print("📊 Enhanced Analytics Service Test")
    print("=" * 40)
    
    # Create service
    service = EnhancedAnalyticsService()
    
    # Test threshold calculation
    print("\n🎯 Testing dynamic threshold calculation...")
    test_metrics = [
        "system_cpu_usage_percent",
        "system_memory_usage_percent",
        "app_response_time_seconds"
    ]
    
    for metric in test_metrics:
        threshold_info = service.calculate_dynamic_threshold(metric)
        print(f"   {metric}: {threshold_info['value']:.2f} (confidence: {threshold_info['confidence']:.1%})")
    
    # Test health check
    print(f"\n🏥 Health Check:")
    health = service.health_check()
    for key, value in health.items():
        print(f"   {key}: {value}")
    
    # Start continuous analysis
    print(f"\n🔄 Starting continuous analysis...")
    service.start_continuous_analysis()
    
    # Wait and show correlation data
    time.sleep(5)
    
    if service.correlation_engine:
        print(f"\n🔗 Correlation Summary:")
        summary = service.get_correlation_summary()
        for key, value in summary.items():
            print(f"   {key}: {value}")
    
    # Stop service
    service.stop_continuous_analysis()
    print(f"\n✅ Test completed")

if __name__ == "__main__":
    main()