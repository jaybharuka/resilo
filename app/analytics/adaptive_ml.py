#!/usr/bin/env python3
"""
Adaptive ML Models for AIOps Bot
Self-learning models that continuously adapt to changing system patterns
"""

import json
import logging
import os
import pickle
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import IsolationForest
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdaptiveMLModel:
    """Base class for adaptive ML models"""
    
    def __init__(self, model_name: str, retrain_interval: int = 3600):
        self.model_name = model_name
        self.retrain_interval = retrain_interval  # seconds
        self.model = None
        self.scaler = StandardScaler()
        self.last_training = None
        self.performance_history = []
        self.data_buffer = []
        self.adaptation_threshold = 0.1  # Performance drop threshold for retraining
        self.model_path = f"models/{model_name}.pkl"
        self.scaler_path = f"models/{model_name}_scaler.pkl"
        
        # Create models directory
        os.makedirs("models", exist_ok=True)
        
        # Load existing model if available
        self.load_model()
    
    def save_model(self):
        """Save model and scaler to disk"""
        try:
            with open(self.model_path, 'wb') as f:
                pickle.dump(self.model, f)
            with open(self.scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            logger.info(f"💾 Saved model: {self.model_name}")
        except Exception as e:
            logger.error(f"❌ Error saving model {self.model_name}: {e}")
    
    def load_model(self):
        """Load model and scaler from disk"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                with open(self.model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(self.scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info(f"📚 Loaded existing model: {self.model_name}")
                return True
        except Exception as e:
            logger.error(f"❌ Error loading model {self.model_name}: {e}")
        return False
    
    def should_retrain(self) -> bool:
        """Determine if model should be retrained"""
        if self.model is None:
            return True
        
        if self.last_training is None:
            return True
        
        # Time-based retraining
        time_since_training = (datetime.now() - self.last_training).total_seconds()
        if time_since_training > self.retrain_interval:
            return True
        
        # Performance-based retraining
        if len(self.performance_history) > 5:
            recent_performance = np.mean(self.performance_history[-3:])
            baseline_performance = np.mean(self.performance_history[:-3])
            
            if baseline_performance - recent_performance > self.adaptation_threshold:
                logger.info(f"🔄 Performance drop detected for {self.model_name}: {baseline_performance:.3f} -> {recent_performance:.3f}")
                return True
        
        return False
    
    def add_training_data(self, features: np.ndarray, labels: np.ndarray = None):
        """Add new training data to buffer"""
        self.data_buffer.append({
            'features': features,
            'labels': labels,
            'timestamp': datetime.now()
        })
        
        # Keep buffer manageable
        if len(self.data_buffer) > 1000:
            self.data_buffer = self.data_buffer[-500:]

class AdaptiveAnomalyDetector(AdaptiveMLModel):
    """Adaptive anomaly detection model"""
    
    def __init__(self, contamination: float = 0.1):
        super().__init__("adaptive_anomaly_detector", retrain_interval=1800)  # 30 minutes
        self.contamination = contamination
        self.baseline_contamination = contamination
        
    def train(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Train the anomaly detection model"""
        try:
            if data.empty or len(data) < 20:  # Reduced from 50 to 20
                return {"success": False, "reason": "Insufficient data"}
            
            # Prepare features
            features = self._extract_features(data)
            if features.empty:
                return {"success": False, "reason": "Feature extraction failed"}
            
            # Scale features
            scaled_features = self.scaler.fit_transform(features)
            
            # Adaptive contamination based on recent data patterns
            self._adapt_contamination(data)
            
            # Train model
            self.model = IsolationForest(
                contamination=self.contamination,
                random_state=42,
                n_estimators=200,
                max_samples='auto'
            )
            
            self.model.fit(scaled_features)
            self.last_training = datetime.now()
            
            # Evaluate on training data for performance tracking
            predictions = self.model.predict(scaled_features)
            anomaly_rate = (predictions == -1).mean()
            
            performance = {
                'anomaly_rate': anomaly_rate,
                'contamination': self.contamination,
                'features_count': len(features.columns),
                'training_samples': len(scaled_features)
            }
            
            self.performance_history.append(anomaly_rate)
            self.save_model()
            
            logger.info(f"🎯 Trained {self.model_name}: {performance}")
            return {"success": True, "performance": performance}
            
        except Exception as e:
            logger.error(f"❌ Error training {self.model_name}: {e}")
            return {"success": False, "reason": str(e)}
    
    def _adapt_contamination(self, data: pd.DataFrame):
        """Adapt contamination parameter based on data characteristics"""
        try:
            values = data['value'].values
            cv = np.std(values) / (np.mean(values) + 1e-8)  # Coefficient of variation
            
            # Adjust contamination based on data stability
            if cv < 0.1:  # Very stable data
                self.contamination = max(0.05, self.baseline_contamination * 0.5)
            elif cv > 0.5:  # Very variable data
                self.contamination = min(0.2, self.baseline_contamination * 2)
            else:
                self.contamination = self.baseline_contamination
                
            logger.info(f"🎯 Adapted contamination for {self.model_name}: {self.contamination:.3f} (CV: {cv:.3f})")
            
        except Exception as e:
            logger.error(f"❌ Error adapting contamination: {e}")
    
    def _extract_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Extract features for anomaly detection"""
        try:
            features = pd.DataFrame()
            values = data['value'].values
            
            # Basic statistical features
            features['value'] = values
            features['rolling_mean_5'] = pd.Series(values).rolling(5, min_periods=1).mean()
            features['rolling_std_5'] = pd.Series(values).rolling(5, min_periods=1).std().fillna(0)
            features['rolling_mean_20'] = pd.Series(values).rolling(20, min_periods=1).mean()
            features['rolling_std_20'] = pd.Series(values).rolling(20, min_periods=1).std().fillna(0)
            
            # Trend features
            features['diff_1'] = np.diff(values, prepend=values[0])
            features['diff_2'] = np.diff(values, n=2, prepend=[values[0], values[1]])
            
            # Relative features
            features['value_normalized'] = (values - np.mean(values)) / (np.std(values) + 1e-8)
            features['percentile_rank'] = pd.Series(values).rank(pct=True)
            
            # Time-based features (if timestamp available)
            if 'timestamp' in data.columns:
                timestamps = pd.to_datetime(data['timestamp'])
                features['hour'] = timestamps.dt.hour
                features['day_of_week'] = timestamps.dt.dayofweek
                features['is_weekend'] = (timestamps.dt.dayofweek >= 5).astype(int)
            
            # Fill any remaining NaN values
            features = features.fillna(0)
            
            return features
            
        except Exception as e:
            logger.error(f"❌ Error extracting features: {e}")
            return pd.DataFrame()
    
    def predict(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Predict anomalies in new data"""
        try:
            if self.model is None:
                return {"success": False, "reason": "Model not trained"}
            
            features = self._extract_features(data)
            if features.empty:
                return {"success": False, "reason": "Feature extraction failed"}
            
            scaled_features = self.scaler.transform(features)
            predictions = self.model.predict(scaled_features)
            scores = self.model.decision_function(scaled_features)
            
            anomalies = predictions == -1
            anomaly_count = np.sum(anomalies)
            confidence = np.mean(np.abs(scores))
            
            result = {
                "success": True,
                "anomaly_detected": bool(anomaly_count > 0),
                "anomaly_count": int(anomaly_count),
                "total_points": len(predictions),
                "anomaly_percentage": float(anomaly_count / len(predictions) * 100),
                "confidence": float(confidence),
                "anomaly_indices": np.where(anomalies)[0].tolist(),
                "scores": scores.tolist()
            }
            
            # Store performance for adaptation
            self.add_training_data(scaled_features)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error predicting with {self.model_name}: {e}")
            return {"success": False, "reason": str(e)}

class AdaptiveMLManager:
    """Manager for all adaptive ML models"""
    
    def __init__(self, prometheus_url: str = "http://localhost:9090"):
        self.prometheus_url = prometheus_url
        self.models: Dict[str, AdaptiveMLModel] = {}
        self.active = False
        self.adaptation_thread = None
        
        # Metrics to monitor
        self.monitored_metrics = [
            'system_cpu_usage_percent',
            'system_memory_usage_percent',
            'app_response_time_seconds',
            'app_error_rate_percent'
        ]
        
        # Initialize models
        self._initialize_models()
        
        logger.info("🧠 Adaptive ML Manager initialized")
    
    def _initialize_models(self):
        """Initialize adaptive models for each metric"""
        for metric in self.monitored_metrics:
            model = AdaptiveAnomalyDetector()
            model.model_name = f"anomaly_detector_{metric}"
            self.models[metric] = model
            logger.info(f"🎯 Initialized adaptive model for {metric}")
    
    def start_adaptation(self):
        """Start the continuous adaptation process"""
        if self.active:
            return
        
        self.active = True
        self.adaptation_thread = threading.Thread(target=self._adaptation_loop, daemon=True)
        self.adaptation_thread.start()
        logger.info("🔄 Started adaptive ML continuous learning")
    
    def stop_adaptation(self):
        """Stop the adaptation process"""
        self.active = False
        if self.adaptation_thread:
            self.adaptation_thread.join()
        logger.info("⏹️ Stopped adaptive ML learning")
    
    def _adaptation_loop(self):
        """Main adaptation loop"""
        while self.active:
            try:
                for metric_name, model in self.models.items():
                    self._adapt_model(metric_name, model)
                
                # Sleep for a shorter interval to check for adaptation needs
                time.sleep(300)  # 5 minutes
                
            except Exception as e:
                logger.error(f"❌ Error in adaptation loop: {e}")
                time.sleep(60)  # Wait before retrying
    
    def _adapt_model(self, metric_name: str, model: AdaptiveMLModel):
        """Adapt a specific model if needed"""
        try:
            if model.should_retrain():
                logger.info(f"🔄 Retraining model for {metric_name}")
                
                # Get fresh training data
                training_data = self._get_training_data(metric_name)
                
                if not training_data.empty:
                    result = model.train(training_data)
                    if result.get("success"):
                        logger.info(f"✅ Successfully retrained {metric_name} model")
                    else:
                        logger.warning(f"⚠️ Failed to retrain {metric_name}: {result.get('reason')}")
                else:
                    logger.warning(f"⚠️ No training data available for {metric_name}")
                    
        except Exception as e:
            logger.error(f"❌ Error adapting model for {metric_name}: {e}")
    
    def _get_training_data(self, metric_name: str, hours_back: int = 24) -> pd.DataFrame:
        """Get training data for a metric"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_back)
            
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query_range",
                params={
                    'query': metric_name,
                    'start': start_time.timestamp(),
                    'end': end_time.timestamp(),
                    'step': '60s'  # 1-minute intervals
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data', {}).get('result'):
                    result = data['data']['result'][0]
                    values = result.get('values', [])
                    
                    df = pd.DataFrame([
                        {
                            'timestamp': datetime.fromtimestamp(float(ts)),
                            'value': float(val)
                        }
                        for ts, val in values
                    ])
                    
                    logger.info(f"📊 Retrieved {len(df)} training samples for {metric_name}")
                    return df
            
        except Exception as e:
            logger.error(f"❌ Error getting training data for {metric_name}: {e}")
        
        return pd.DataFrame()
    
    def predict_anomaly(self, metric_name: str, data: pd.DataFrame) -> Dict[str, Any]:
        """Get anomaly prediction for a metric"""
        if metric_name not in self.models:
            return {"success": False, "reason": "Model not found"}
        
        return self.models[metric_name].predict(data)
    
    def get_model_status(self) -> Dict[str, Any]:
        """Get status of all adaptive models"""
        status = {
            'active': self.active,
            'models': {}
        }
        
        for metric_name, model in self.models.items():
            status['models'][metric_name] = {
                'last_training': model.last_training.isoformat() if model.last_training else None,
                'performance_history_length': len(model.performance_history),
                'data_buffer_size': len(model.data_buffer),
                'model_exists': model.model is not None,
                'contamination': getattr(model, 'contamination', None)
            }
        
        return status
    
    def force_retrain_all(self):
        """Force retrain all models"""
        logger.info("🔄 Force retraining all adaptive models")
        
        for metric_name, model in self.models.items():
            training_data = self._get_training_data(metric_name)
            if not training_data.empty:
                result = model.train(training_data)
                logger.info(f"🎯 Force retrained {metric_name}: {result.get('success', False)}")

def main():
    """Main function to test adaptive ML models"""
    print("🧠 Adaptive ML Models for AIOps Bot")
    
    # Create manager
    manager = AdaptiveMLManager()
    
    # Start adaptation
    manager.start_adaptation()
    
    print("🔄 Adaptive learning started")
    print("📊 Models will continuously adapt to new data patterns")
    print("⏹️ Press Ctrl+C to stop")
    
    try:
        # Keep running
        while True:
            time.sleep(10)
            
            # Print status every minute
            status = manager.get_model_status()
            print(f"\n📈 Active models: {len(status['models'])}")
            
            for metric, model_status in status['models'].items():
                last_training = model_status['last_training']
                if last_training:
                    last_training = datetime.fromisoformat(last_training).strftime('%H:%M:%S')
                else:
                    last_training = "Never"
                
                print(f"   🎯 {metric}: Last trained {last_training}, Buffer: {model_status['data_buffer_size']}")
            
            time.sleep(50)  # Total 60 seconds
            
    except KeyboardInterrupt:
        print("\n⏹️ Stopping adaptive ML learning...")
        manager.stop_adaptation()

if __name__ == "__main__":
    main()