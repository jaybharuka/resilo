#!/usr/bin/env python3
"""
Advanced Predictive Analytics System for AIOps Bot
Predicts system failures, capacity planning, and proactive alerting
"""

import json
import logging
import pickle
import threading
import time
import warnings
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ML imports
try:
    import scipy.stats as stats
    from sklearn.ensemble import IsolationForest, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("⚠️ ML libraries not available - using fallback predictions")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Prediction:
    """Prediction result with metadata"""
    metric: str
    predicted_value: float
    prediction_time: datetime
    target_time: datetime
    confidence: float
    model_type: str
    trend: str  # 'increasing', 'decreasing', 'stable'
    risk_level: str  # 'low', 'medium', 'high', 'critical'
    time_to_threshold: Optional[int] = None  # minutes until threshold breach
    seasonal_component: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            'metric': self.metric,
            'predicted_value': self.predicted_value,
            'prediction_time': self.prediction_time.isoformat(),
            'target_time': self.target_time.isoformat(),
            'confidence': self.confidence,
            'model_type': self.model_type,
            'trend': self.trend,
            'risk_level': self.risk_level,
            'time_to_threshold': self.time_to_threshold,
            'seasonal_component': self.seasonal_component
        }

@dataclass
class CapacityForecast:
    """Capacity planning forecast"""
    metric: str
    current_usage: float
    predicted_usage_7d: float
    predicted_usage_30d: float
    predicted_usage_90d: float
    growth_rate_daily: float
    capacity_exhaustion_date: Optional[datetime]
    recommended_action: str
    confidence: float
    
    def to_dict(self) -> dict:
        return {
            'metric': self.metric,
            'current_usage': self.current_usage,
            'predicted_usage_7d': self.predicted_usage_7d,
            'predicted_usage_30d': self.predicted_usage_30d,
            'predicted_usage_90d': self.predicted_usage_90d,
            'growth_rate_daily': self.growth_rate_daily,
            'capacity_exhaustion_date': self.capacity_exhaustion_date.isoformat() if self.capacity_exhaustion_date else None,
            'recommended_action': self.recommended_action,
            'confidence': self.confidence
        }

class PredictiveAnalyticsEngine:
    """Advanced predictive analytics for AIOps"""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.historical_data = {}
        self.predictions = {}
        self.capacity_forecasts = {}
        
        # Prediction parameters
        self.prediction_horizon_hours = 48  # Predict 48 hours ahead
        self.min_data_points = 20
        self.retrain_interval_hours = 6
        
        # Model performance tracking
        self.model_performance = {}
        
        # Background processing
        self.running = False
        self.prediction_thread = None
        
        # Data storage
        self.max_history_points = 1000
        
        logger.info("🔮 Predictive Analytics Engine initialized")
    
    def add_historical_data(self, metric: str, timestamp: datetime, value: float):
        """Add historical data point"""
        try:
            if metric not in self.historical_data:
                self.historical_data[metric] = deque(maxlen=self.max_history_points)
            
            self.historical_data[metric].append({
                'timestamp': timestamp,
                'value': value
            })
            
            # Auto-train if we have enough data
            if len(self.historical_data[metric]) >= self.min_data_points:
                if metric not in self.models or self._should_retrain(metric):
                    self._train_prediction_model(metric)
            
        except Exception as e:
            logger.error(f"❌ Error adding historical data for {metric}: {e}")
    
    def _should_retrain(self, metric: str) -> bool:
        """Check if model should be retrained"""
        try:
            if metric not in self.model_performance:
                return True
            
            last_train = self.model_performance[metric].get('last_trained')
            if not last_train:
                return True
            
            hours_since_train = (datetime.now() - last_train).total_seconds() / 3600
            return hours_since_train >= self.retrain_interval_hours
            
        except Exception:
            return True
    
    def _prepare_training_data(self, metric: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Prepare data for training"""
        try:
            if metric not in self.historical_data:
                return None
            
            data = list(self.historical_data[metric])
            if len(data) < self.min_data_points:
                return None
            
            # Convert to pandas DataFrame
            df = pd.DataFrame(data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            # Feature engineering
            df['hour'] = df['timestamp'].dt.hour
            df['day_of_week'] = df['timestamp'].dt.dayofweek
            df['minute_of_hour'] = df['timestamp'].dt.minute
            
            # Time-based features
            df['time_numeric'] = (df['timestamp'] - df['timestamp'].min()).dt.total_seconds()
            
            # Rolling statistics
            window_size = min(10, len(df) // 4)
            if window_size > 1:
                df['rolling_mean'] = df['value'].rolling(window=window_size).mean()
                df['rolling_std'] = df['value'].rolling(window=window_size).std()
                df = df.fillna(method='bfill')
            else:
                df['rolling_mean'] = df['value']
                df['rolling_std'] = 0
            
            # Lag features
            for lag in [1, 2, 3]:
                if len(df) > lag:
                    df[f'lag_{lag}'] = df['value'].shift(lag)
            
            df = df.fillna(method='bfill').fillna(0)
            
            # Select features
            feature_columns = ['hour', 'day_of_week', 'minute_of_hour', 'time_numeric', 
                             'rolling_mean', 'rolling_std']
            
            # Add lag features if available
            for lag in [1, 2, 3]:
                if f'lag_{lag}' in df.columns:
                    feature_columns.append(f'lag_{lag}')
            
            X = df[feature_columns].values
            y = df['value'].values
            
            return X, y
            
        except Exception as e:
            logger.error(f"❌ Error preparing training data for {metric}: {e}")
            return None
    
    def _train_prediction_model(self, metric: str):
        """Train prediction model for a metric"""
        try:
            data = self._prepare_training_data(metric)
            if data is None:
                return
            
            X, y = data
            
            if len(X) < self.min_data_points:
                return
            
            # Split data
            test_size = min(0.3, max(0.1, len(X) * 0.2 / len(X)))
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
            
            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train multiple models and select best
            models = {}
            
            if ML_AVAILABLE:
                # Random Forest
                rf = RandomForestRegressor(n_estimators=50, random_state=42, max_depth=10)
                rf.fit(X_train_scaled, y_train)
                models['random_forest'] = rf
                
                # Ridge Regression
                ridge = Ridge(alpha=1.0)
                ridge.fit(X_train_scaled, y_train)
                models['ridge'] = ridge
                
                # Linear Regression
                lr = LinearRegression()
                lr.fit(X_train_scaled, y_train)
                models['linear'] = lr
            
            # Simple fallback model
            mean_model = lambda x: np.full(len(x), np.mean(y_train))
            models['mean'] = mean_model
            
            # Evaluate models
            best_model = None
            best_score = float('-inf')
            best_model_name = 'mean'
            
            for name, model in models.items():
                try:
                    if name == 'mean':
                        y_pred = model(X_test_scaled)
                    else:
                        y_pred = model.predict(X_test_scaled)
                    
                    score = r2_score(y_test, y_pred)
                    
                    if score > best_score:
                        best_score = score
                        best_model = model
                        best_model_name = name
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error evaluating model {name}: {e}")
                    continue
            
            # Store best model
            self.models[metric] = best_model
            self.scalers[metric] = scaler
            
            # Track performance
            self.model_performance[metric] = {
                'model_type': best_model_name,
                'r2_score': best_score,
                'last_trained': datetime.now(),
                'training_samples': len(X_train)
            }
            
            logger.info(f"🎯 Trained {best_model_name} model for {metric} (R²: {best_score:.3f})")
            
        except Exception as e:
            logger.error(f"❌ Error training model for {metric}: {e}")
    
    def predict_metric(self, metric: str, hours_ahead: int = 24) -> Optional[Prediction]:
        """Predict metric value for future time"""
        try:
            if metric not in self.models or metric not in self.historical_data:
                return None
            
            # Get latest data point
            latest_data = list(self.historical_data[metric])[-1]
            target_time = latest_data['timestamp'] + timedelta(hours=hours_ahead)
            
            # Prepare features for prediction
            hour = target_time.hour
            day_of_week = target_time.weekday()
            minute_of_hour = target_time.minute
            
            # Time numeric (extrapolated)
            base_time = pd.to_datetime([d['timestamp'] for d in self.historical_data[metric]]).min()
            time_numeric = (target_time - base_time).total_seconds()
            
            # Rolling statistics (use recent values)
            recent_values = [d['value'] for d in list(self.historical_data[metric])[-10:]]
            rolling_mean = np.mean(recent_values)
            rolling_std = np.std(recent_values) if len(recent_values) > 1 else 0
            
            # Lag features
            lag_1 = latest_data['value']
            lag_2 = list(self.historical_data[metric])[-2]['value'] if len(self.historical_data[metric]) > 1 else lag_1
            lag_3 = list(self.historical_data[metric])[-3]['value'] if len(self.historical_data[metric]) > 2 else lag_2
            
            # Create feature vector
            features = np.array([[hour, day_of_week, minute_of_hour, time_numeric, 
                                rolling_mean, rolling_std, lag_1, lag_2, lag_3]])
            
            # Scale features
            if metric in self.scalers:
                features_scaled = self.scalers[metric].transform(features)
            else:
                features_scaled = features
            
            # Make prediction
            model = self.models[metric]
            model_type = self.model_performance[metric]['model_type']
            
            if model_type == 'mean':
                predicted_value = model(features_scaled)[0]
            else:
                predicted_value = model.predict(features_scaled)[0]
            
            # Calculate confidence
            r2_score = self.model_performance[metric]['r2_score']
            confidence = max(0.1, min(0.95, r2_score)) if r2_score > 0 else 0.5
            
            # Determine trend
            recent_trend = self._calculate_trend(metric)
            
            # Determine risk level
            risk_level = self._assess_risk_level(metric, predicted_value)
            
            # Calculate time to threshold
            time_to_threshold = self._calculate_time_to_threshold(metric, predicted_value, recent_trend)
            
            prediction = Prediction(
                metric=metric,
                predicted_value=float(predicted_value),
                prediction_time=datetime.now(),
                target_time=target_time,
                confidence=confidence,
                model_type=model_type,
                trend=recent_trend,
                risk_level=risk_level,
                time_to_threshold=time_to_threshold
            )
            
            # Store prediction
            if metric not in self.predictions:
                self.predictions[metric] = deque(maxlen=100)
            self.predictions[metric].append(prediction)
            
            return prediction
            
        except Exception as e:
            logger.error(f"❌ Error predicting {metric}: {e}")
            return None
    
    def _calculate_trend(self, metric: str) -> str:
        """Calculate trend direction for metric"""
        try:
            if metric not in self.historical_data:
                return 'stable'
            
            recent_data = list(self.historical_data[metric])[-10:]  # Last 10 points
            if len(recent_data) < 3:
                return 'stable'
            
            values = [d['value'] for d in recent_data]
            
            # Simple linear regression for trend
            x = np.arange(len(values))
            slope, _, r_value, _, _ = stats.linregress(x, values)
            
            # Determine trend based on slope and correlation
            if abs(r_value) < 0.3:  # Low correlation
                return 'stable'
            elif slope > 0.1:
                return 'increasing'
            elif slope < -0.1:
                return 'decreasing'
            else:
                return 'stable'
                
        except Exception:
            return 'stable'
    
    def _assess_risk_level(self, metric: str, predicted_value: float) -> str:
        """Assess risk level based on predicted value"""
        try:
            # Get threshold or estimate from historical data
            if metric not in self.historical_data:
                return 'low'
            
            values = [d['value'] for d in self.historical_data[metric]]
            max_value = max(values)
            p95_value = np.percentile(values, 95)
            
            # Define thresholds based on metric type
            if 'cpu' in metric.lower() or 'memory' in metric.lower():
                critical_threshold = 95.0
                high_threshold = 85.0
                medium_threshold = 70.0
            elif 'disk' in metric.lower():
                critical_threshold = 90.0
                high_threshold = 80.0
                medium_threshold = 70.0
            elif 'error' in metric.lower():
                critical_threshold = 10.0
                high_threshold = 5.0
                medium_threshold = 2.0
            else:
                # Use percentiles for unknown metrics
                critical_threshold = p95_value * 1.1
                high_threshold = p95_value
                medium_threshold = p95_value * 0.8
            
            if predicted_value >= critical_threshold:
                return 'critical'
            elif predicted_value >= high_threshold:
                return 'high'
            elif predicted_value >= medium_threshold:
                return 'medium'
            else:
                return 'low'
                
        except Exception:
            return 'low'
    
    def _calculate_time_to_threshold(self, metric: str, predicted_value: float, trend: str) -> Optional[int]:
        """Calculate time until threshold breach"""
        try:
            if trend not in ['increasing']:
                return None
            
            # Get current value
            if metric not in self.historical_data:
                return None
            
            current_value = list(self.historical_data[metric])[-1]['value']
            
            # Estimate threshold
            values = [d['value'] for d in self.historical_data[metric]]
            
            if 'cpu' in metric.lower() or 'memory' in metric.lower():
                threshold = 85.0
            elif 'disk' in metric.lower():
                threshold = 80.0
            else:
                threshold = np.percentile(values, 90)
            
            if current_value >= threshold:
                return 0  # Already at threshold
            
            # Calculate rate of increase
            recent_data = list(self.historical_data[metric])[-5:]
            if len(recent_data) < 2:
                return None
            
            time_diffs = []
            value_diffs = []
            
            for i in range(1, len(recent_data)):
                time_diff = (recent_data[i]['timestamp'] - recent_data[i-1]['timestamp']).total_seconds() / 60  # minutes
                value_diff = recent_data[i]['value'] - recent_data[i-1]['value']
                
                if time_diff > 0:
                    time_diffs.append(time_diff)
                    value_diffs.append(value_diff)
            
            if not time_diffs:
                return None
            
            # Calculate average rate per minute
            avg_rate_per_minute = np.mean(value_diffs) / np.mean(time_diffs)
            
            if avg_rate_per_minute <= 0:
                return None
            
            # Calculate time to threshold
            value_to_threshold = threshold - current_value
            minutes_to_threshold = value_to_threshold / avg_rate_per_minute
            
            return max(0, int(minutes_to_threshold))
            
        except Exception:
            return None
    
    def generate_capacity_forecast(self, metric: str) -> Optional[CapacityForecast]:
        """Generate capacity planning forecast"""
        try:
            if metric not in self.historical_data:
                return None
            
            current_value = list(self.historical_data[metric])[-1]['value']
            
            # Get predictions for different time horizons
            pred_7d = self.predict_metric(metric, hours_ahead=24*7)
            pred_30d = self.predict_metric(metric, hours_ahead=24*30)
            pred_90d = self.predict_metric(metric, hours_ahead=24*90)
            
            if not pred_7d:
                return None
            
            # Calculate growth rate
            values = [d['value'] for d in self.historical_data[metric]]
            recent_values = values[-7:] if len(values) >= 7 else values
            
            if len(recent_values) > 1:
                growth_rate = (recent_values[-1] - recent_values[0]) / len(recent_values)
            else:
                growth_rate = 0
            
            # Estimate capacity exhaustion
            capacity_limit = self._estimate_capacity_limit(metric)
            exhaustion_date = None
            
            if growth_rate > 0 and current_value < capacity_limit:
                days_to_exhaustion = (capacity_limit - current_value) / growth_rate
                if days_to_exhaustion > 0:
                    exhaustion_date = datetime.now() + timedelta(days=days_to_exhaustion)
            
            # Generate recommendation
            recommendation = self._generate_capacity_recommendation(
                metric, current_value, pred_30d.predicted_value if pred_30d else current_value, 
                growth_rate, exhaustion_date
            )
            
            forecast = CapacityForecast(
                metric=metric,
                current_usage=current_value,
                predicted_usage_7d=pred_7d.predicted_value,
                predicted_usage_30d=pred_30d.predicted_value if pred_30d else current_value,
                predicted_usage_90d=pred_90d.predicted_value if pred_90d else current_value,
                growth_rate_daily=growth_rate,
                capacity_exhaustion_date=exhaustion_date,
                recommended_action=recommendation,
                confidence=pred_7d.confidence
            )
            
            # Store forecast
            self.capacity_forecasts[metric] = forecast
            
            return forecast
            
        except Exception as e:
            logger.error(f"❌ Error generating capacity forecast for {metric}: {e}")
            return None
    
    def _estimate_capacity_limit(self, metric: str) -> float:
        """Estimate capacity limit for metric"""
        if 'cpu' in metric.lower() or 'memory' in metric.lower() or 'disk' in metric.lower():
            return 100.0  # Percentage metrics
        elif 'bytes' in metric.lower():
            return 1e12  # 1TB default
        elif 'connections' in metric.lower():
            return 1000  # Default connection limit
        else:
            # Use max observed value * 1.5 as capacity
            values = [d['value'] for d in self.historical_data[metric]]
            return max(values) * 1.5
    
    def _generate_capacity_recommendation(self, metric: str, current: float, predicted_30d: float, 
                                        growth_rate: float, exhaustion_date: Optional[datetime]) -> str:
        """Generate capacity planning recommendation"""
        try:
            if exhaustion_date and exhaustion_date < datetime.now() + timedelta(days=30):
                return f"URGENT: Capacity exhaustion predicted in {(exhaustion_date - datetime.now()).days} days. Immediate scaling required."
            
            if predicted_30d > current * 1.5:
                return "High growth predicted. Consider scaling resources within 30 days."
            
            if growth_rate > 1.0:  # Growing by more than 1 unit per day
                return "Steady growth observed. Monitor usage and plan capacity expansion."
            
            if predicted_30d < current * 0.8:
                return "Usage declining. Consider resource optimization and cost reduction."
            
            return "Usage stable. Continue monitoring for changes in trend."
            
        except Exception:
            return "Monitor usage patterns and plan accordingly."
    
    def get_failure_predictions(self, hours_ahead: int = 24) -> List[Dict]:
        """Get failure predictions for all monitored metrics"""
        predictions = []
        
        for metric in self.historical_data.keys():
            try:
                pred = self.predict_metric(metric, hours_ahead)
                if pred and pred.risk_level in ['high', 'critical']:
                    predictions.append({
                        'metric': metric,
                        'prediction': pred.to_dict(),
                        'failure_probability': self._calculate_failure_probability(pred),
                        'recommended_actions': self._get_failure_recommendations(metric, pred)
                    })
            except Exception as e:
                logger.error(f"❌ Error getting failure prediction for {metric}: {e}")
        
        # Sort by failure probability
        predictions.sort(key=lambda x: x['failure_probability'], reverse=True)
        return predictions
    
    def _calculate_failure_probability(self, prediction: Prediction) -> float:
        """Calculate probability of failure based on prediction"""
        try:
            base_prob = {
                'critical': 0.8,
                'high': 0.6,
                'medium': 0.3,
                'low': 0.1
            }.get(prediction.risk_level, 0.1)
            
            # Adjust by confidence
            adjusted_prob = base_prob * prediction.confidence
            
            # Adjust by trend
            if prediction.trend == 'increasing':
                adjusted_prob *= 1.2
            elif prediction.trend == 'decreasing':
                adjusted_prob *= 0.8
            
            return min(0.95, max(0.05, adjusted_prob))
            
        except Exception:
            return 0.5
    
    def _get_failure_recommendations(self, metric: str, prediction: Prediction) -> List[str]:
        """Get recommendations for preventing failure"""
        recommendations = []
        
        try:
            if 'cpu' in metric.lower():
                recommendations.extend([
                    "Scale CPU resources or optimize CPU-intensive processes",
                    "Check for CPU-hungry applications and optimize",
                    "Consider load balancing across multiple instances"
                ])
            elif 'memory' in metric.lower():
                recommendations.extend([
                    "Increase memory allocation or identify memory leaks",
                    "Optimize memory usage in applications",
                    "Consider memory cleanup and garbage collection tuning"
                ])
            elif 'disk' in metric.lower():
                recommendations.extend([
                    "Add storage capacity or clean up disk space",
                    "Archive old files and logs",
                    "Implement disk space monitoring and cleanup automation"
                ])
            elif 'error' in metric.lower():
                recommendations.extend([
                    "Investigate error causes and fix underlying issues",
                    "Review application logs for error patterns",
                    "Implement error handling improvements"
                ])
            else:
                recommendations.append(f"Monitor {metric} closely and investigate trending patterns")
            
            # Add time-sensitive recommendations
            if prediction.time_to_threshold and prediction.time_to_threshold < 60:
                recommendations.insert(0, f"URGENT: Take action within {prediction.time_to_threshold} minutes")
            
        except Exception:
            recommendations.append("Monitor metric and investigate unusual patterns")
        
        return recommendations
    
    def start_continuous_prediction(self):
        """Start continuous prediction processing"""
        if self.running:
            return
        
        self.running = True
        self.prediction_thread = threading.Thread(target=self._continuous_prediction, daemon=True)
        self.prediction_thread.start()
        logger.info("🔄 Continuous prediction started")
    
    def stop_continuous_prediction(self):
        """Stop continuous prediction"""
        self.running = False
        if self.prediction_thread:
            self.prediction_thread.join()
        logger.info("⏹️ Continuous prediction stopped")
    
    def _continuous_prediction(self):
        """Main loop for continuous prediction"""
        while self.running:
            try:
                # Generate predictions for all metrics
                for metric in list(self.historical_data.keys()):
                    self.predict_metric(metric, hours_ahead=24)
                    self.generate_capacity_forecast(metric)
                
                time.sleep(300)  # Run every 5 minutes
                
            except Exception as e:
                logger.error(f"❌ Error in continuous prediction: {e}")
                time.sleep(60)
    
    def get_analytics_summary(self) -> Dict:
        """Get summary of predictive analytics"""
        try:
            total_metrics = len(self.historical_data)
            trained_models = len(self.models)
            recent_predictions = len([p for predictions in self.predictions.values() 
                                   for p in predictions if (datetime.now() - p.prediction_time).total_seconds() < 3600])
            
            # Count predictions by risk level
            risk_counts = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
            for predictions in self.predictions.values():
                for pred in predictions:
                    if (datetime.now() - pred.prediction_time).total_seconds() < 3600:
                        risk_counts[pred.risk_level] += 1
            
            return {
                'total_metrics_monitored': total_metrics,
                'trained_models': trained_models,
                'recent_predictions': recent_predictions,
                'risk_distribution': risk_counts,
                'capacity_forecasts': len(self.capacity_forecasts),
                'model_performance': dict(self.model_performance),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting analytics summary: {e}")
            return {'error': str(e)}

def main():
    """Test the predictive analytics system"""
    print("🔮 Predictive Analytics System Test")
    print("=" * 40)
    
    # Create engine
    engine = PredictiveAnalyticsEngine()
    
    # Simulate historical data
    print("\n📊 Simulating historical data...")
    base_time = datetime.now() - timedelta(hours=48)
    
    # CPU usage with trend
    for i in range(100):
        timestamp = base_time + timedelta(minutes=i*30)
        # Simulate increasing CPU usage with noise
        base_cpu = 45 + (i * 0.3) + np.random.normal(0, 5)
        base_cpu = max(0, min(100, base_cpu))
        
        engine.add_historical_data("system_cpu_usage_percent", timestamp, base_cpu)
    
    # Memory usage with pattern
    for i in range(100):
        timestamp = base_time + timedelta(minutes=i*30)
        # Simulate cyclical memory pattern
        base_memory = 60 + 15 * np.sin(i * 0.1) + np.random.normal(0, 3)
        base_memory = max(0, min(100, base_memory))
        
        engine.add_historical_data("system_memory_usage_percent", timestamp, base_memory)
    
    # Response time with occasional spikes
    for i in range(100):
        timestamp = base_time + timedelta(minutes=i*30)
        base_response = 0.2 + np.random.exponential(0.1)
        if i % 20 == 0:  # Occasional spikes
            base_response *= 3
        
        engine.add_historical_data("app_response_time_seconds", timestamp, base_response)
    
    print("✅ Added historical data for 3 metrics")
    
    # Test predictions
    print(f"\n🔮 Testing predictions...")
    metrics = ["system_cpu_usage_percent", "system_memory_usage_percent", "app_response_time_seconds"]
    
    for metric in metrics:
        pred = engine.predict_metric(metric, hours_ahead=24)
        if pred:
            print(f"   {metric}:")
            print(f"      Predicted: {pred.predicted_value:.2f}")
            print(f"      Trend: {pred.trend}")
            print(f"      Risk: {pred.risk_level}")
            print(f"      Confidence: {pred.confidence:.1%}")
            if pred.time_to_threshold:
                print(f"      Time to threshold: {pred.time_to_threshold} minutes")
    
    # Test capacity forecasting
    print(f"\n📈 Testing capacity forecasting...")
    for metric in metrics:
        forecast = engine.generate_capacity_forecast(metric)
        if forecast:
            print(f"   {metric}:")
            print(f"      Current: {forecast.current_usage:.1f}")
            print(f"      30-day: {forecast.predicted_usage_30d:.1f}")
            print(f"      Growth rate: {forecast.growth_rate_daily:.2f}/day")
            print(f"      Recommendation: {forecast.recommended_action}")
    
    # Test failure predictions
    print(f"\n⚠️ Testing failure predictions...")
    failures = engine.get_failure_predictions(hours_ahead=24)
    if failures:
        for failure in failures[:3]:  # Show top 3
            print(f"   Risk: {failure['metric']}")
            print(f"      Failure probability: {failure['failure_probability']:.1%}")
            print(f"      Actions: {failure['recommended_actions'][0]}")
    else:
        print("   No high-risk failures predicted")
    
    # Show summary
    print(f"\n📊 Analytics Summary:")
    summary = engine.get_analytics_summary()
    for key, value in summary.items():
        if key != 'model_performance':
            print(f"   {key}: {value}")
    
    print(f"\n✅ Predictive analytics test completed!")

if __name__ == "__main__":
    main()