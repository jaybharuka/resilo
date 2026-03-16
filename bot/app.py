from flask import Flask, request, jsonify, render_template
import requests
import json
import os
from datetime import datetime
from llm_service import llm_service
from analytics_service import analytics_service

app = Flask(__name__)

# Discord webhook URL (you'll need to set this)
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/YOUR_WEBHOOK_URL')

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/', methods=['GET'])
@app.route('/dashboard', methods=['GET'])
def dashboard():
    """Serve the ML analytics dashboard"""
    return render_template('dashboard.html')

@app.route('/analytics/anomalies/<metric_name>', methods=['GET'])
def detect_anomalies_endpoint(metric_name):
    """Detect anomalies in a specific metric"""
    try:
        hours_back = request.args.get('hours', 24, type=int)
        
        print(f"🔬 Analyzing anomalies for {metric_name} (last {hours_back}h)")
        
        # Collect metrics data
        data = analytics_service.collect_metrics_data(metric_name, hours_back)
        
        if data.empty:
            return jsonify({
                "status": "error",
                "message": "No data available for analysis",
                "metric": metric_name
            }), 404
        
        # Detect anomalies
        anomaly_result = analytics_service.detect_anomalies(metric_name, data)
        
        # Predict trends
        trend_result = analytics_service.predict_trend(metric_name, data)
        
        # Generate insights
        insights = analytics_service.generate_insights(metric_name, anomaly_result, trend_result)
        
        response = {
            "status": "success",
            "metric": metric_name,
            "analysis_timestamp": datetime.now().isoformat(),
            "data_points": len(data),
            "time_range_hours": hours_back,
            "anomaly_analysis": anomaly_result,
            "trend_analysis": trend_result,
            "insights": insights
        }
        
        # Ensure JSON serialization
        from analytics_service import ensure_json_serializable
        response = ensure_json_serializable(response)
        
        print(f"✅ Anomaly analysis completed for {metric_name}")
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Error in anomaly detection endpoint: {e}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "metric": metric_name
        }), 500

@app.route('/analytics/summary', methods=['GET'])
def analytics_summary():
    """Get analytics summary for key metrics"""
    try:
        print("📊 Generating analytics summary...")
        
        # Key metrics to analyze
        key_metrics = [
            'sample_app_requests_total',
            'cpu_usage_percent',
            'memory_usage_percent',
            'response_time_seconds'
        ]
        
        summary = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "metrics_analyzed": 0,
            "total_anomalies_detected": 0,
            "high_risk_metrics": [],
            "insights": [],
            "metric_summaries": {}
        }
        
        for metric in key_metrics:
            try:
                # Quick analysis with 6 hours of data
                data = analytics_service.collect_metrics_data(metric, 6)
                
                if not data.empty:
                    anomaly_result = analytics_service.detect_anomalies(metric, data)
                    trend_result = analytics_service.predict_trend(metric, data)
                    
                    summary["metrics_analyzed"] += 1
                    
                    if anomaly_result.get("anomaly_detected", False):
                        summary["total_anomalies_detected"] += anomaly_result.get("anomaly_count", 0)
                        
                        if anomaly_result.get("severity") in ["high", "critical"]:
                            summary["high_risk_metrics"].append({
                                "metric": metric,
                                "severity": anomaly_result.get("severity"),
                                "anomaly_percentage": anomaly_result.get("anomaly_percentage", 0)
                            })
                    
                    # Store summary for each metric
                    summary["metric_summaries"][metric] = {
                        "anomaly_detected": anomaly_result.get("anomaly_detected", False),
                        "severity": anomaly_result.get("severity", "low"),
                        "trend": trend_result.get("trend", "unknown"),
                        "risk_level": trend_result.get("risk_level", "low"),
                        "confidence": anomaly_result.get("confidence", 0)
                    }
                    
            except Exception as e:
                print(f"⚠️ Error analyzing {metric}: {e}")
                continue
        
        # Generate overall insights
        if summary["high_risk_metrics"]:
            summary["insights"].append(f"🚨 {len(summary['high_risk_metrics'])} metrics showing high-risk anomalies")
        
        if summary["total_anomalies_detected"] > 10:
            summary["insights"].append("⚠️ Multiple anomalies detected across infrastructure")
        elif summary["total_anomalies_detected"] == 0:
            summary["insights"].append("✅ No significant anomalies detected in monitored metrics")
        
        print(f"✅ Analytics summary completed - {summary['metrics_analyzed']} metrics analyzed")
        
        # Ensure JSON serialization
        from analytics_service import ensure_json_serializable
        summary = ensure_json_serializable(summary)
        
        return jsonify(summary)
        
    except Exception as e:
        print(f"❌ Error generating analytics summary: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/alert', methods=['POST'])
def receive_alert():
    """Receive alerts from Alertmanager, analyze with AI and ML, and forward enriched data"""
    try:
        alert_data = request.json
        print(f"📥 Received alert: {json.dumps(alert_data, indent=2)}")
        
        # Get AI analysis of the alert
        print("🤖 Analyzing alert with AI...")
        ai_analysis = llm_service.analyze_alert(alert_data)
        
        # Perform ML-based anomaly detection for related metrics
        print("🔬 Performing advanced analytics...")
        ml_analysis = {}
        
        # Extract metric information from alert
        if 'alerts' in alert_data:
            for alert in alert_data['alerts']:
                alert_name = alert.get('labels', {}).get('alertname', '')
                service = alert.get('labels', {}).get('service', '')
                
                # Determine relevant metrics to analyze based on alert type
                relevant_metrics = []
                if 'request' in alert_name.lower() or 'rate' in alert_name.lower():
                    relevant_metrics = ['sample_app_requests_total', 'response_time_seconds']
                elif 'cpu' in alert_name.lower():
                    relevant_metrics = ['cpu_usage_percent']
                elif 'memory' in alert_name.lower():
                    relevant_metrics = ['memory_usage_percent']
                elif 'down' in alert_name.lower():
                    relevant_metrics = ['sample_app_requests_total', 'cpu_usage_percent', 'memory_usage_percent']
                else:
                    # Default metrics for unknown alert types
                    relevant_metrics = ['sample_app_requests_total']
                
                # Analyze each relevant metric
                for metric in relevant_metrics:
                    try:
                        # Get recent data for analysis
                        data = analytics_service.collect_metrics_data(metric, 2)  # Last 2 hours
                        
                        if not data.empty:
                            anomaly_result = analytics_service.detect_anomalies(metric, data)
                            trend_result = analytics_service.predict_trend(metric, data, 2)  # 2h forecast
                            
                            ml_analysis[metric] = {
                                "anomaly_analysis": anomaly_result,
                                "trend_analysis": trend_result,
                                "insights": analytics_service.generate_insights(metric, anomaly_result, trend_result)
                            }
                            
                    except Exception as e:
                        print(f"⚠️ Error analyzing {metric}: {e}")
                        continue
        
        # Process alerts with AI and ML insights
        if 'alerts' in alert_data:
            for alert in alert_data['alerts']:
                send_enhanced_notification(alert, ai_analysis, ml_analysis)
        
        # Store comprehensive analysis for future reference
        analysis_summary = {
            "timestamp": datetime.now().isoformat(),
            "alert_count": len(alert_data.get('alerts', [])),
            "ai_analysis": ai_analysis.get('ai_analysis', ''),
            "priority": ai_analysis.get('priority_level', 3),
            "impact": ai_analysis.get('impact_assessment', 'Unknown'),
            "ml_metrics_analyzed": len(ml_analysis),
            "anomalies_detected": sum(1 for analysis in ml_analysis.values() 
                                    if analysis.get('anomaly_analysis', {}).get('anomaly_detected', False)),
            "high_risk_trends": sum(1 for analysis in ml_analysis.values() 
                                  if analysis.get('trend_analysis', {}).get('risk_level') == 'high')
        }
        
        print(f"✅ Alert processed with AI+ML analysis. Priority: {analysis_summary['priority']}, "
              f"ML anomalies: {analysis_summary['anomalies_detected']}")
        
        response = {
            "status": "success", 
            "message": "Alert processed with AI and ML analysis",
            "analysis_summary": analysis_summary,
            "ml_analysis_summary": {
                metric: {
                    "anomaly_detected": analysis.get('anomaly_analysis', {}).get('anomaly_detected', False),
                    "trend": analysis.get('trend_analysis', {}).get('trend', 'unknown'),
                    "risk_level": analysis.get('trend_analysis', {}).get('risk_level', 'low')
                }
                for metric, analysis in ml_analysis.items()
            }
        }
        
        # Ensure JSON serialization
        from analytics_service import ensure_json_serializable
        response = ensure_json_serializable(response)
        
        return jsonify(response)
    
    except Exception as e:
        print(f"❌ Error processing alert: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def send_enhanced_notification(alert, ai_analysis, ml_analysis=None):
    """Send enhanced alert notification with AI and ML analysis to Discord"""
    try:
        # Extract alert information
        alert_name = alert.get('labels', {}).get('alertname', 'Unknown Alert')
        severity = alert.get('labels', {}).get('severity', 'unknown')
        summary = alert.get('annotations', {}).get('summary', 'No summary available')
        description = alert.get('annotations', {}).get('description', 'No description available')
        status = alert.get('status', 'unknown')
        
        # Get AI insights
        ai_text = ai_analysis.get('ai_analysis', 'AI analysis not available')
        suggestions = ai_analysis.get('suggested_actions', [])
        impact = ai_analysis.get('impact_assessment', 'Unknown impact')
        priority = ai_analysis.get('priority_level', 3)
        
        # Choose color based on priority and severity
        color_map = {
            5: 16711680,    # Critical - Red
            4: 16776960,    # High - Orange  
            3: 16776960,    # Medium - Yellow
            2: 65280,       # Low - Green
            1: 8421504      # Info - Gray
        }
        color = color_map.get(priority, 8421504)
        
        # Priority emoji mapping
        priority_emoji = {5: "🔥", 4: "⚠️", 3: "📊", 2: "ℹ️", 1: "📝"}
        emoji = priority_emoji.get(priority, "🚨")
        
        # Create enhanced Discord embed with AI and ML analysis
        embed = {
            "title": f"{emoji} {alert_name} (Priority {priority})",
            "description": f"**Alert Summary:** {summary}\n\n**🤖 AI Analysis:**\n{ai_text}",
            "color": color,
            "fields": [
                {
                    "name": "⚡ Status & Severity",
                    "value": f"**Status:** {status.upper()}\n**Severity:** {severity.upper()}\n**Impact:** {impact}",
                    "inline": True
                },
                {
                    "name": "🎯 Priority Level",
                    "value": f"**{priority}/5** {emoji}",
                    "inline": True
                }
            ],
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": "AIOps Bot with AI + ML Analysis"
            }
        }
        
        # Add detailed description
        if description and description != "No description available":
            embed["fields"].append({
                "name": "📋 Details",
                "value": description,
                "inline": False
            })
        
        # Add ML analysis results if available
        if ml_analysis:
            ml_insights = []
            anomaly_count = 0
            high_risk_trends = 0
            
            for metric, analysis in ml_analysis.items():
                anomaly_result = analysis.get('anomaly_analysis', {})
                trend_result = analysis.get('trend_analysis', {})
                
                if anomaly_result.get('anomaly_detected', False):
                    anomaly_count += 1
                    severity_level = anomaly_result.get('severity', 'low')
                    ml_insights.append(f"🔍 **{metric}**: {severity_level} anomalies ({anomaly_result.get('anomaly_percentage', 0):.1f}%)")
                
                if trend_result.get('risk_level') == 'high':
                    high_risk_trends += 1
                    trend = trend_result.get('trend', 'unknown')
                    ml_insights.append(f"📈 **{metric}**: {trend} trend (high risk)")
            
            if ml_insights:
                embed["fields"].append({
                    "name": "🔬 ML Analytics",
                    "value": "\n".join(ml_insights[:3]) + (f"\n...and {len(ml_insights)-3} more" if len(ml_insights) > 3 else ""),
                    "inline": False
                })
            
            # Add summary of ML findings
            if anomaly_count > 0 or high_risk_trends > 0:
                ml_summary = f"📊 **ML Analysis:** {anomaly_count} metrics with anomalies, {high_risk_trends} high-risk trends"
                embed["fields"].append({
                    "name": "🧠 Advanced Analytics Summary",
                    "value": ml_summary,
                    "inline": False
                })
        
        # Add AI-generated fix suggestions
        if suggestions:
            suggestions_text = "\n".join(suggestions[:4])  # Limit to 4 suggestions for Discord
            embed["fields"].append({
                "name": "🔧 AI-Suggested Actions",
                "value": suggestions_text,
                "inline": False
            })
        
        # Add labels as fields (excluding common ones already shown)
        if 'labels' in alert:
            labels_text = "\n".join([f"**{k}**: {v}" for k, v in alert['labels'].items() 
                                   if k not in ['alertname', 'severity', 'service']])
            if labels_text:
                embed["fields"].append({
                    "name": "🏷️ Labels",
                    "value": labels_text,
                    "inline": False
                })
        
        payload = {
            "embeds": [embed]
        }
        
        # Send to Discord (only if webhook URL is configured)
        if DISCORD_WEBHOOK_URL and 'YOUR_WEBHOOK_URL' not in DISCORD_WEBHOOK_URL:
            response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if response.status_code == 204:
                print(f"✅ Enhanced alert sent to Discord: {alert_name} (Priority {priority})")
            else:
                print(f"❌ Failed to send to Discord: {response.status_code}")
        else:
            print(f"📢 Discord webhook not configured. Enhanced alert ready:")
            print(f"   🎯 Alert: {alert_name} (Priority {priority})")
            print(f"   🤖 AI Analysis: {ai_text[:100]}...")
            print(f"   🔧 Suggestions: {len(suggestions)} actions recommended")
            if ml_analysis:
                anomalies = sum(1 for a in ml_analysis.values() if a.get('anomaly_analysis', {}).get('anomaly_detected', False))
                print(f"   🔬 ML Analysis: {len(ml_analysis)} metrics analyzed, {anomalies} anomalies detected")
    
    except Exception as e:
        print(f"❌ Error sending enhanced notification: {e}")

def send_discord_notification(alert):
    """Legacy function - now redirects to enhanced notification"""
    # For backward compatibility, create basic AI analysis
    mock_analysis = {
        'ai_analysis': 'Basic alert processing (legacy mode)',
        'suggested_actions': ['Review alert details and take appropriate action'],
        'impact_assessment': 'Impact assessment required',
        'priority_level': 3
    }
    send_enhanced_notification(alert, mock_analysis, None)

if __name__ == '__main__':
    print("🤖 AIOps Bot with AI + ML Analytics starting...")
    print("📝 To configure Discord notifications:")
    print("   1. Create a Discord webhook in your server")
    print("   2. Set DISCORD_WEBHOOK_URL environment variable")
    print("   3. Restart the bot")
    print("🧠 To enable full AI analysis:")
    print("   1. Set OPENAI_API_KEY environment variable")
    print("   2. Restart the bot")
    print("🔬 ML Features Available:")
    print("   ✅ Anomaly detection with Isolation Forest")
    print("   ✅ Time-series trend analysis")
    print("   ✅ Predictive alerting")
    print("   ✅ Advanced analytics endpoints")
    print("   📊 Currently running with intelligent mock data")
    print("\n🚀 Available endpoints:")
    print("   🎯 / or /dashboard - ML Analytics Dashboard")
    print("   📈 /analytics/anomalies/<metric_name> - Anomaly detection")
    print("   📊 /analytics/summary - Analytics overview")
    print("   🩺 /health - Health check")
    print("   🚨 /alert - Alert processing (webhook)")
    print("\n📊 Dashboard Access:")
    print("   🌐 Open http://localhost:5000 in your browser")
    print("   📈 Real-time charts and analytics")
    print("   🔄 Auto-refresh every 30 seconds")
    app.run(host='0.0.0.0', port=8080, debug=True)
