#!/usr/bin/env python3
"""
Live Predictive Analytics Integration
Connects predictive models with real-time system monitoring
"""

import time
import threading
from datetime import datetime, timedelta
from predictive_analytics import PredictiveAnalyticsEngine
from live_computer_monitor import LiveComputerMonitor
import psutil
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LivePredictiveSystem:
    """Live predictive analytics system with real computer monitoring"""
    
    def __init__(self):
        self.predictive_engine = PredictiveAnalyticsEngine()
        self.computer_monitor = LiveComputerMonitor()
        self.running = False
        self.monitor_thread = None
        
        # Prediction settings
        self.data_collection_interval = 30  # seconds
        self.prediction_interval = 300      # 5 minutes
        self.last_prediction_time = None
        
        # Performance tracking
        self.predictions_made = 0
        self.alerts_generated = 0
        self.high_risk_predictions = 0
        
        logger.info("🔮 Live Predictive System initialized")
    
    def start_live_monitoring(self):
        """Start live monitoring and prediction"""
        if self.running:
            return
        
        print("🚀 Starting Live Predictive Analytics System")
        print("=" * 50)
        print("🔮 Real-time failure prediction and capacity planning")
        print("📊 Collecting live system metrics...")
        print("⚡ Generating predictions every 5 minutes")
        print()
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._live_monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        # Start predictive engine
        self.predictive_engine.start_continuous_prediction()
        
        logger.info("🔄 Live monitoring started")
    
    def stop_live_monitoring(self):
        """Stop live monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        
        self.predictive_engine.stop_continuous_prediction()
        logger.info("⏹️ Live monitoring stopped")
    
    def _live_monitoring_loop(self):
        """Main monitoring loop"""
        startup_time = datetime.now()
        
        while self.running:
            try:
                current_time = datetime.now()
                
                # Collect real system metrics
                self._collect_system_metrics(current_time)
                
                # Generate predictions periodically
                if self._should_generate_predictions(current_time):
                    self._generate_and_analyze_predictions(current_time)
                    self.last_prediction_time = current_time
                
                # Show periodic status
                if (current_time - startup_time).total_seconds() % 60 < self.data_collection_interval:
                    self._show_status_update(current_time)
                
                time.sleep(self.data_collection_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in monitoring loop: {e}")
                time.sleep(60)
    
    def _collect_system_metrics(self, timestamp: datetime):
        """Collect real system metrics"""
        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_info = psutil.virtual_memory()
            disk_info = psutil.disk_usage('C:')
            
            # Add to predictive engine
            self.predictive_engine.add_historical_data("system_cpu_usage_percent", timestamp, cpu_percent)
            self.predictive_engine.add_historical_data("system_memory_usage_percent", timestamp, memory_info.percent)
            self.predictive_engine.add_historical_data("system_disk_usage_percent", timestamp, disk_info.percent)
            
            # Add network metrics if available
            try:
                net_io = psutil.net_io_counters()
                self.predictive_engine.add_historical_data("network_bytes_sent", timestamp, net_io.bytes_sent)
                self.predictive_engine.add_historical_data("network_bytes_recv", timestamp, net_io.bytes_recv)
            except:
                pass
            
            # Add process count
            process_count = len(psutil.pids())
            self.predictive_engine.add_historical_data("system_process_count", timestamp, process_count)
            
        except Exception as e:
            logger.error(f"❌ Error collecting system metrics: {e}")
    
    def _should_generate_predictions(self, current_time: datetime) -> bool:
        """Check if predictions should be generated"""
        if not self.last_prediction_time:
            return True
        
        seconds_since_last = (current_time - self.last_prediction_time).total_seconds()
        return seconds_since_last >= self.prediction_interval
    
    def _generate_and_analyze_predictions(self, current_time: datetime):
        """Generate predictions and analyze results"""
        try:
            print(f"\n🔮 Generating Predictions at {current_time.strftime('%H:%M:%S')}")
            print("-" * 50)
            
            # Get available metrics
            available_metrics = list(self.predictive_engine.historical_data.keys())
            
            predictions = []
            capacity_forecasts = []
            
            # Generate predictions for each metric
            for metric in available_metrics:
                # 24-hour prediction
                pred_24h = self.predictive_engine.predict_metric(metric, hours_ahead=24)
                if pred_24h:
                    predictions.append(pred_24h)
                    print(f"📊 {metric}:")
                    print(f"   Current: {list(self.predictive_engine.historical_data[metric])[-1]['value']:.1f}")
                    print(f"   24h Prediction: {pred_24h.predicted_value:.1f}")
                    print(f"   Trend: {pred_24h.trend} | Risk: {pred_24h.risk_level} | Confidence: {pred_24h.confidence:.1%}")
                    
                    if pred_24h.time_to_threshold:
                        print(f"   ⚠️ Time to threshold: {pred_24h.time_to_threshold} minutes")
                    
                    self.predictions_made += 1
                    
                    if pred_24h.risk_level in ['high', 'critical']:
                        self.high_risk_predictions += 1
                
                # Capacity forecast
                forecast = self.predictive_engine.generate_capacity_forecast(metric)
                if forecast:
                    capacity_forecasts.append(forecast)
            
            # Get failure predictions
            failure_predictions = self.predictive_engine.get_failure_predictions(hours_ahead=24)
            
            if failure_predictions:
                print(f"\n⚠️ HIGH-RISK FAILURE PREDICTIONS:")
                for i, failure in enumerate(failure_predictions[:3], 1):
                    print(f"   {i}. {failure['metric']}")
                    print(f"      Failure Probability: {failure['failure_probability']:.1%}")
                    print(f"      Action: {failure['recommended_actions'][0]}")
                    self.alerts_generated += 1
            
            # Show capacity alerts
            capacity_alerts = [f for f in capacity_forecasts 
                             if f.capacity_exhaustion_date and 
                             f.capacity_exhaustion_date < datetime.now() + timedelta(days=30)]
            
            if capacity_alerts:
                print(f"\n📈 CAPACITY PLANNING ALERTS:")
                for alert in capacity_alerts:
                    days_to_exhaustion = (alert.capacity_exhaustion_date - datetime.now()).days
                    print(f"   📊 {alert.metric}: Capacity exhaustion in {days_to_exhaustion} days")
                    print(f"      Recommendation: {alert.recommended_action}")
            
            # Analytics summary
            summary = self.predictive_engine.get_analytics_summary()
            high_risk_count = summary.get('risk_distribution', {}).get('high', 0) + summary.get('risk_distribution', {}).get('critical', 0)
            
            if high_risk_count > 0:
                print(f"\n🚨 SUMMARY: {high_risk_count} high-risk predictions detected!")
            else:
                print(f"\n✅ SUMMARY: All systems predicted to be stable")
            
        except Exception as e:
            logger.error(f"❌ Error generating predictions: {e}")
    
    def _show_status_update(self, current_time: datetime):
        """Show periodic status update"""
        try:
            # Get current system stats
            cpu = psutil.cpu_percent()
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage('C:').percent
            
            print(f"📊 Live System Status [{current_time.strftime('%H:%M:%S')}]")
            print(f"   CPU: {cpu:.1f}% | Memory: {memory:.1f}% | Disk: {disk:.1f}%")
            print(f"   Predictions Made: {self.predictions_made} | High-Risk: {self.high_risk_predictions} | Alerts: {self.alerts_generated}")
            
        except Exception as e:
            logger.error(f"❌ Error showing status: {e}")
    
    def run_demo(self, duration_minutes: int = 10):
        """Run a demonstration of live predictive analytics"""
        print(f"🎬 Live Predictive Analytics Demo")
        print(f"Running for {duration_minutes} minutes with real system monitoring...")
        print(f"Press Ctrl+C to stop early")
        print()
        
        try:
            self.start_live_monitoring()
            
            # Run for specified duration
            end_time = datetime.now() + timedelta(minutes=duration_minutes)
            
            while datetime.now() < end_time and self.running:
                time.sleep(10)  # Check every 10 seconds
            
            self.stop_live_monitoring()
            
            # Show final results
            print(f"\n🎉 Demo Complete!")
            print(f"📈 Final Statistics:")
            print(f"   Total Predictions: {self.predictions_made}")
            print(f"   High-Risk Predictions: {self.high_risk_predictions}")
            print(f"   Alerts Generated: {self.alerts_generated}")
            
            # Show analytics summary
            summary = self.predictive_engine.get_analytics_summary()
            print(f"   Metrics Monitored: {summary.get('total_metrics_monitored', 0)}")
            print(f"   Models Trained: {summary.get('trained_models', 0)}")
            
        except KeyboardInterrupt:
            print(f"\n⏹️ Demo stopped by user")
            self.stop_live_monitoring()
        except Exception as e:
            print(f"\n❌ Demo error: {e}")
            self.stop_live_monitoring()

def main():
    """Run live predictive analytics demonstration"""
    system = LivePredictiveSystem()
    
    print("🔮 Live Predictive Analytics System")
    print("=" * 40)
    print("This system demonstrates:")
    print("  🔍 Real-time system monitoring")
    print("  🧠 ML-powered failure prediction")
    print("  📊 Capacity planning forecasts")
    print("  ⚡ Proactive alerting")
    print()
    
    # Run demo
    system.run_demo(duration_minutes=5)

if __name__ == "__main__":
    main()