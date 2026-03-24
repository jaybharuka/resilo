#!/usr/bin/env python3
"""
Dynamic Alert Rules Generator for AIOps Bot
Generates Prometheus alert rules based on real data analysis
"""

import os
import sys
import yaml
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any
import requests
import json

class DynamicAlertRulesGenerator:
    """Generate alert rules based on real data patterns"""
    
    def __init__(self, prometheus_url: str = "http://prometheus:9090"):
        self.prometheus_url = prometheus_url
        self.alert_rules = {}
        self.baseline_stats = {}
        
    def analyze_metric_patterns(self, metric_name: str, days_back: int = 7) -> Dict[str, Any]:
        """Analyze metric patterns to determine appropriate alert thresholds"""
        try:
            # Get historical data
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days_back)
            
            query = f"{metric_name}[{days_back}d]"
            params = {
                'query': query,
                'time': end_time.isoformat()
            }
            
            response = requests.get(f"{self.prometheus_url}/api/v1/query", params=params, timeout=10)
            if response.status_code != 200:
                return self._get_default_pattern(metric_name)
            
            data = response.json()
            if not data.get('data', {}).get('result'):
                return self._get_default_pattern(metric_name)
            
            # Extract values
            values = []
            for result in data['data']['result']:
                if 'values' in result:
                    for timestamp, value in result['values']:
                        try:
                            values.append(float(value))
                        except (ValueError, TypeError):
                            continue
            
            if not values:
                return self._get_default_pattern(metric_name)
            
            # Calculate statistical measures
            values_array = np.array(values)
            mean_val = np.mean(values_array)
            std_val = np.std(values_array)
            median_val = np.median(values_array)
            q95 = np.percentile(values_array, 95)
            q99 = np.percentile(values_array, 99)
            q05 = np.percentile(values_array, 5)
            q01 = np.percentile(values_array, 1)
            
            # Determine pattern type
            cv = std_val / (mean_val + 1e-8)  # Coefficient of variation
            
            if cv < 0.1:
                pattern_type = "stable"
                sensitivity = "high"
            elif cv < 0.3:
                pattern_type = "moderate_variation"
                sensitivity = "medium"
            else:
                pattern_type = "high_variation"
                sensitivity = "low"
            
            # Calculate dynamic thresholds
            if 'cpu' in metric_name.lower() or 'memory' in metric_name.lower():
                # Resource utilization metrics (0-100%)
                warning_threshold = min(85, max(70, q95))
                critical_threshold = min(95, max(85, q99))
                low_warning = max(5, min(15, q05))
                low_critical = max(1, min(5, q01))
                
            elif 'response_time' in metric_name.lower() or 'latency' in metric_name.lower():
                # Response time metrics (lower is better)
                warning_threshold = min(mean_val + 2*std_val, q95)
                critical_threshold = min(mean_val + 3*std_val, q99)
                low_warning = None  # No low threshold for response time
                low_critical = None
                
            elif 'error' in metric_name.lower():
                # Error rate metrics (lower is better)
                warning_threshold = max(1, min(mean_val + 2*std_val, q95))
                critical_threshold = max(5, min(mean_val + 3*std_val, q99))
                low_warning = None
                low_critical = None
                
            elif 'throughput' in metric_name.lower() or 'requests' in metric_name.lower():
                # Throughput metrics (can be high or low)
                warning_threshold = None  # High throughput usually good
                critical_threshold = None
                low_warning = max(0.1, min(mean_val - 2*std_val, q05))
                low_critical = max(0.01, min(mean_val - 3*std_val, q01))
                
            else:
                # Generic metrics
                warning_threshold = mean_val + 2*std_val
                critical_threshold = mean_val + 3*std_val
                low_warning = mean_val - 2*std_val if mean_val - 2*std_val > 0 else None
                low_critical = mean_val - 3*std_val if mean_val - 3*std_val > 0 else None
            
            return {
                'metric_name': metric_name,
                'pattern_type': pattern_type,
                'sensitivity': sensitivity,
                'stats': {
                    'mean': mean_val,
                    'std': std_val,
                    'median': median_val,
                    'q95': q95,
                    'q99': q99,
                    'q05': q05,
                    'q01': q01,
                    'cv': cv
                },
                'thresholds': {
                    'warning': warning_threshold,
                    'critical': critical_threshold,
                    'low_warning': low_warning,
                    'low_critical': low_critical
                },
                'data_points': len(values),
                'analysis_period': f"{days_back} days"
            }
            
        except Exception as e:
            print(f"❌ Error analyzing {metric_name}: {e}")
            return self._get_default_pattern(metric_name)
    
    def _get_default_pattern(self, metric_name: str) -> Dict[str, Any]:
        """Return default thresholds when analysis fails"""
        if 'cpu' in metric_name.lower() or 'memory' in metric_name.lower():
            thresholds = {'warning': 80, 'critical': 90, 'low_warning': 10, 'low_critical': 5}
        elif 'response_time' in metric_name.lower():
            thresholds = {'warning': 1.0, 'critical': 2.0, 'low_warning': None, 'low_critical': None}
        elif 'error' in metric_name.lower():
            thresholds = {'warning': 5, 'critical': 10, 'low_warning': None, 'low_critical': None}
        else:
            thresholds = {'warning': 80, 'critical': 90, 'low_warning': 20, 'low_critical': 10}
        
        return {
            'metric_name': metric_name,
            'pattern_type': 'unknown',
            'sensitivity': 'medium',
            'thresholds': thresholds,
            'data_points': 0,
            'analysis_period': 'default'
        }
    
    def generate_alert_rules(self, metrics: List[str]) -> Dict[str, Any]:
        """Generate dynamic alert rules for multiple metrics"""
        rules = {
            'groups': [{
                'name': 'dynamic_alerts',
                'interval': '30s',
                'rules': []
            }]
        }
        
        for metric in metrics:
            print(f"📊 Analyzing {metric}...")
            pattern = self.analyze_metric_patterns(metric)
            
            # Generate rules for this metric
            metric_rules = self._create_rules_for_metric(pattern)
            rules['groups'][0]['rules'].extend(metric_rules)
            
            # Store pattern for later use
            self.baseline_stats[metric] = pattern
        
        return rules
    
    def _create_rules_for_metric(self, pattern: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create Prometheus alert rules for a specific metric"""
        rules = []
        metric_name = pattern['metric_name']
        thresholds = pattern['thresholds']
        sensitivity = pattern['sensitivity']
        
        # Adjust evaluation duration based on sensitivity
        duration_map = {
            'high': '1m',
            'medium': '2m',
            'low': '5m'
        }
        duration = duration_map.get(sensitivity, '2m')
        
        # High threshold alerts
        if thresholds.get('warning') is not None:
            rules.append({
                'alert': f'{metric_name}_high_warning',
                'expr': f'{metric_name} > {thresholds["warning"]}',
                'for': duration,
                'labels': {
                    'severity': 'warning',
                    'metric': metric_name,
                    'threshold_type': 'dynamic'
                },
                'annotations': {
                    'summary': f'{metric_name} is above warning threshold',
                    'description': f'{metric_name} value {{{{ $value }}}} exceeds warning threshold of {thresholds["warning"]:.2f} (pattern: {pattern["pattern_type"]})',
                    'pattern_analysis': f'Based on {pattern["data_points"]} data points over {pattern["analysis_period"]}'
                }
            })
        
        if thresholds.get('critical') is not None:
            rules.append({
                'alert': f'{metric_name}_high_critical',
                'expr': f'{metric_name} > {thresholds["critical"]}',
                'for': duration,
                'labels': {
                    'severity': 'critical',
                    'metric': metric_name,
                    'threshold_type': 'dynamic'
                },
                'annotations': {
                    'summary': f'{metric_name} is critically high',
                    'description': f'{metric_name} value {{{{ $value }}}} exceeds critical threshold of {thresholds["critical"]:.2f} (pattern: {pattern["pattern_type"]})',
                    'pattern_analysis': f'Based on {pattern["data_points"]} data points over {pattern["analysis_period"]}'
                }
            })
        
        # Low threshold alerts
        if thresholds.get('low_warning') is not None:
            rules.append({
                'alert': f'{metric_name}_low_warning',
                'expr': f'{metric_name} < {thresholds["low_warning"]}',
                'for': duration,
                'labels': {
                    'severity': 'warning',
                    'metric': metric_name,
                    'threshold_type': 'dynamic'
                },
                'annotations': {
                    'summary': f'{metric_name} is below warning threshold',
                    'description': f'{metric_name} value {{{{ $value }}}} is below warning threshold of {thresholds["low_warning"]:.2f} (pattern: {pattern["pattern_type"]})',
                    'pattern_analysis': f'Based on {pattern["data_points"]} data points over {pattern["analysis_period"]}'
                }
            })
        
        if thresholds.get('low_critical') is not None:
            rules.append({
                'alert': f'{metric_name}_low_critical',
                'expr': f'{metric_name} < {thresholds["low_critical"]}',
                'for': duration,
                'labels': {
                    'severity': 'critical',
                    'metric': metric_name,
                    'threshold_type': 'dynamic'
                },
                'annotations': {
                    'summary': f'{metric_name} is critically low',
                    'description': f'{metric_name} value {{{{ $value }}}} is below critical threshold of {thresholds["low_critical"]:.2f} (pattern: {pattern["pattern_type"]})',
                    'pattern_analysis': f'Based on {pattern["data_points"]} data points over {pattern["analysis_period"]}'
                }
            })
        
        return rules
    
    def save_alert_rules(self, rules: Dict[str, Any], filename: str = "dynamic_alert_rules.yml"):
        """Save alert rules to YAML file"""
        try:
            with open(filename, 'w') as f:
                yaml.dump(rules, f, default_flow_style=False)
            print(f"✅ Dynamic alert rules saved to {filename}")
            return True
        except Exception as e:
            print(f"❌ Error saving alert rules: {e}")
            return False

def main():
    """Main function to generate dynamic alert rules"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate dynamic alert rules')
    parser.add_argument('--prometheus-url', default='http://prometheus:9090', 
                       help='Prometheus URL (default: http://prometheus:9090)')
    args = parser.parse_args()
    
    print("🎯 Dynamic Alert Rules Generator for AIOps Bot")
    print(f"📊 Using Prometheus URL: {args.prometheus_url}")
    
    # List of metrics to analyze
    metrics = [
        'system_cpu_usage_percent',
        'system_memory_usage_percent',
        'system_disk_usage_percent',
        'app_response_time_seconds',
        'app_error_rate_percent',
        'app_throughput_requests_per_sec',
        'http_requests_total',
        'user_sessions_active'
    ]
    
    generator = DynamicAlertRulesGenerator(args.prometheus_url)
    
    print("📊 Analyzing metrics and generating dynamic thresholds...")
    rules = generator.generate_alert_rules(metrics)
    
    print(f"\n📋 Generated {len(rules['groups'][0]['rules'])} alert rules")
    
    # Save rules
    if generator.save_alert_rules(rules, "dynamic_alert_rules.yml"):
        print("✅ Dynamic alert rules generated successfully!")
        
        # Print summary
        print("\n📊 Threshold Summary:")
        for metric, pattern in generator.baseline_stats.items():
            thresholds = pattern['thresholds']
            print(f"   🎯 {metric}:")
            print(f"      📈 Warning: {thresholds.get('warning', 'N/A')}")
            print(f"      🚨 Critical: {thresholds.get('critical', 'N/A')}")
            print(f"      📉 Pattern: {pattern['pattern_type']} ({pattern['sensitivity']} sensitivity)")
    
    return rules

if __name__ == "__main__":
    main()