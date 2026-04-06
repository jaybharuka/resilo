#!/usr/bin/env python3
"""
Email Notification Integration
Universal email alerts using Gmail SMTP for 100% notification coverage
"""

import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

import yaml
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

class EmailNotificationService:
    """Email notification service for AIOps alerts"""
    
    def __init__(self):
        self.config = self.load_config()
        self.smtp_config = self.get_smtp_config()
        self.enabled = self.smtp_config is not None
        
        if self.enabled:
            logger.info("✅ Email notifications enabled")
        else:
            logger.warning("⚠️ Email notifications disabled - configure SMTP settings")
    
    def load_config(self) -> Dict:
        """Load configuration"""
        try:
            with open('config/enterprise_config.yml', 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            return {}
    
    def get_smtp_config(self) -> Optional[Dict]:
        """Get SMTP configuration"""
        try:
            smtp_config = self.config.get('credentials', {}).get('messaging', {}).get('smtp', {})
            
            if smtp_config.get('username') and smtp_config.get('password'):
                return {
                    'server': smtp_config.get('server', 'smtp.gmail.com'),
                    'port': smtp_config.get('port', 587),
                    'username': smtp_config.get('username'),
                    'password': smtp_config.get('password'),
                    'use_tls': smtp_config.get('use_tls', True)
                }
        except Exception as e:
            logger.error(f"❌ Error getting SMTP config: {e}")
        
        return None
    
    def send_intelligent_email_alert(self, analysis: Dict, recipients: List[str] = None) -> bool:
        """Send intelligent email alert"""
        if not self.enabled:
            logger.warning("⚠️ Email notifications disabled")
            return False
        
        if not recipients:
            recipients = ['admin@company.com']  # Default recipient
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = self.create_subject(analysis)
            msg['From'] = self.smtp_config['username']
            msg['To'] = ', '.join(recipients)
            
            # Create HTML and text content
            html_content = self.create_html_content(analysis)
            text_content = self.create_text_content(analysis)
            
            # Attach content
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_config['server'], self.smtp_config['port']) as server:
                if self.smtp_config['use_tls']:
                    server.starttls(context=context)
                server.login(self.smtp_config['username'], self.smtp_config['password'])
                server.send_message(msg)
            
            logger.info(f"✅ Intelligent email alert sent to {len(recipients)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send email: {e}")
            return False
    
    def create_subject(self, analysis: Dict) -> str:
        """Create email subject"""
        anomalies = analysis.get('anomalies', [])
        
        if not anomalies:
            return "🟢 AIOps: System Healthy - All Clear"
        
        severity_levels = [a.get('severity', 'medium') for a in anomalies]
        
        if 'critical' in severity_levels:
            status = "🔴 CRITICAL"
        elif 'high' in severity_levels:
            status = "🟠 HIGH PRIORITY"
        else:
            status = "🟡 MEDIUM PRIORITY"
        
        issue_count = len(anomalies)
        return f"{status} AIOps Alert: {issue_count} Issues Detected & Analyzed"
    
    def create_html_content(self, analysis: Dict) -> str:
        """Create HTML email content"""
        metrics = analysis.get('metrics', {})
        anomalies = analysis.get('anomalies', [])
        ai_analysis = analysis.get('ai_analysis', '')
        recommendations = analysis.get('recommendations', [])
        resolution_results = analysis.get('resolution_results', [])
        
        # Color coding
        if not anomalies:
            color = "#28a745"  # Green
            status = "System Healthy"
        elif any(a.get('severity') == 'critical' for a in anomalies):
            color = "#dc3545"  # Red
            status = "Critical Issues"
        elif any(a.get('severity') == 'high' for a in anomalies):
            color = "#fd7e14"  # Orange
            status = "High Priority Issues"
        else:
            color = "#ffc107"  # Yellow
            status = "Medium Priority Issues"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px;">
                
                <!-- Header -->
                <div style="background: {color}; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 24px;">🤖 Intelligent AIOps Alert</h1>
                    <p style="margin: 5px 0 0 0; font-size: 16px;">{status} - AI Analysis Complete</p>
                </div>
                
                <!-- System Metrics -->
                <div style="padding: 20px; border-bottom: 1px solid #eee;">
                    <h2 style="color: {color}; margin-top: 0;">📊 System Metrics</h2>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; background: #f8f9fa;"><strong>CPU Usage</strong></td>
                            <td style="padding: 8px; border: 1px solid #ddd;">{metrics.get('cpu_percent', 0):.1f}%</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; background: #f8f9fa;"><strong>Memory Usage</strong></td>
                            <td style="padding: 8px; border: 1px solid #ddd;">{metrics.get('memory_percent', 0):.1f}%</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; background: #f8f9fa;"><strong>Disk Usage</strong></td>
                            <td style="padding: 8px; border: 1px solid #ddd;">{metrics.get('disk_percent', 0):.1f}%</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; background: #f8f9fa;"><strong>Active Processes</strong></td>
                            <td style="padding: 8px; border: 1px solid #ddd;">{metrics.get('process_count', 0)}</td>
                        </tr>
                    </table>
                </div>
        """
        
        # Detected Issues
        if anomalies:
            html += f"""
                <div style="padding: 20px; border-bottom: 1px solid #eee;">
                    <h2 style="color: {color}; margin-top: 0;">🚨 Detected Issues</h2>
                    <ul style="margin: 0; padding-left: 20px;">
            """
            
            for anomaly in anomalies:
                severity_color = "#dc3545" if anomaly.get('severity') == 'critical' else "#fd7e14" if anomaly.get('severity') == 'high' else "#ffc107"
                html += f"""
                        <li style="margin-bottom: 10px;">
                            <strong>{anomaly.get('type', '').replace('_', ' ').title()}</strong>: 
                            {anomaly.get('current_value', 0):.1f}% 
                            <span style="color: {severity_color}; font-weight: bold;">({anomaly.get('severity', 'medium').upper()})</span>
                        </li>
                """
            
            html += """
                    </ul>
                </div>
            """
        
        # AI Analysis
        if ai_analysis:
            html += f"""
                <div style="padding: 20px; border-bottom: 1px solid #eee;">
                    <h2 style="color: {color}; margin-top: 0;">🧠 AI Analysis</h2>
                    <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid {color}; border-radius: 4px;">
                        <pre style="white-space: pre-wrap; font-family: monospace; margin: 0;">{ai_analysis[:800]}{'...' if len(ai_analysis) > 800 else ''}</pre>
                    </div>
                </div>
            """
        
        # Resolution Results
        if resolution_results:
            html += f"""
                <div style="padding: 20px; border-bottom: 1px solid #eee;">
                    <h2 style="color: {color}; margin-top: 0;">🎯 Resolution Results</h2>
                    <ul style="margin: 0; padding-left: 20px;">
            """
            
            for result in resolution_results:
                if result.get('success'):
                    actions = ', '.join(result.get('actions_taken', [])[:2])
                    improvement = result.get('improvement', 0)
                    html += f"""
                            <li style="margin-bottom: 10px; color: #28a745;">
                                ✅ <strong>{result.get('anomaly_type', '').replace('_', ' ').title()}</strong>: 
                                {actions} (Improvement: {improvement:+.1f}%)
                            </li>
                    """
                else:
                    html += f"""
                            <li style="margin-bottom: 10px; color: #ffc107;">
                                ⚠️ <strong>{result.get('anomaly_type', '').replace('_', ' ').title()}</strong>: 
                                Manual intervention required
                            </li>
                    """
            
            html += """
                    </ul>
                </div>
            """
        
        # Recommendations
        if recommendations:
            html += f"""
                <div style="padding: 20px; border-bottom: 1px solid #eee;">
                    <h2 style="color: {color}; margin-top: 0;">💡 Recommendations</h2>
                    <ul style="margin: 0; padding-left: 20px;">
            """
            
            for rec in recommendations[:3]:
                html += f"""
                        <li style="margin-bottom: 10px;">
                            <strong>{rec.get('title', 'Recommendation')}</strong> 
                            <span style="color: {color};">({rec.get('priority', 'medium')} priority)</span>
                        </li>
                """
            
            html += """
                    </ul>
                </div>
            """
        
        # Footer
        html += f"""
                <div style="padding: 20px; background: #f8f9fa; border-radius: 0 0 8px 8px; text-align: center;">
                    <p style="margin: 0; color: #666; font-size: 14px;">
                        🤖 Intelligent AIOps Monitor • Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    </p>
                    <p style="margin: 5px 0 0 0; color: #666; font-size: 12px;">
                        Powered by AI • Enterprise-Grade Monitoring
                    </p>
                </div>
                
            </div>
        </body>
        </html>
        """
        
        return html
    
    def create_text_content(self, analysis: Dict) -> str:
        """Create plain text email content"""
        metrics = analysis.get('metrics', {})
        anomalies = analysis.get('anomalies', [])
        ai_analysis = analysis.get('ai_analysis', '')
        
        text = "🤖 INTELLIGENT AIOPS ALERT\n"
        text += "=" * 50 + "\n\n"
        
        # Status
        if not anomalies:
            text += "✅ STATUS: System Healthy - All Clear\n\n"
        else:
            text += f"🚨 STATUS: {len(anomalies)} Issues Detected\n\n"
        
        # Metrics
        text += "📊 SYSTEM METRICS:\n"
        text += f"   CPU Usage: {metrics.get('cpu_percent', 0):.1f}%\n"
        text += f"   Memory Usage: {metrics.get('memory_percent', 0):.1f}%\n"
        text += f"   Disk Usage: {metrics.get('disk_percent', 0):.1f}%\n"
        text += f"   Active Processes: {metrics.get('process_count', 0)}\n\n"
        
        # Issues
        if anomalies:
            text += "🚨 DETECTED ISSUES:\n"
            for anomaly in anomalies:
                text += f"   • {anomaly.get('type', '').replace('_', ' ').title()}: "
                text += f"{anomaly.get('current_value', 0):.1f}% ({anomaly.get('severity', 'medium').upper()})\n"
            text += "\n"
        
        # AI Analysis
        if ai_analysis:
            text += "🧠 AI ANALYSIS:\n"
            text += ai_analysis[:500] + ("..." if len(ai_analysis) > 500 else "")
            text += "\n\n"
        
        text += f"⏰ Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += "🤖 Intelligent AIOps Monitor\n"
        
        return text
    
    def test_email_notification(self, test_email: str = None) -> bool:
        """Test email notification"""
        if not test_email:
            test_email = self.smtp_config.get('username', 'admin@company.com')
        
        # Create test analysis
        test_analysis = {
            'metrics': {
                'cpu_percent': 45.2,
                'memory_percent': 78.5,
                'disk_percent': 65.1,
                'process_count': 142
            },
            'anomalies': [],
            'ai_analysis': "✅ System operating normally. All metrics within healthy ranges. No issues detected.",
            'recommendations': [],
            'resolution_results': []
        }
        
        print(f"📧 Sending test email to: {test_email}")
        success = self.send_intelligent_email_alert(test_analysis, [test_email])
        
        if success:
            print("✅ Test email sent successfully!")
            print("🔍 Check your inbox for the intelligent AIOps alert")
        else:
            print("❌ Test email failed")
        
        return success

def setup_email_notifications():
    """Setup email notifications"""
    print("📧 Email Notification Setup")
    print("=" * 40)
    
    service = EmailNotificationService()
    
    if service.enabled:
        print("✅ Email service configured")
        print("📧 Ready to send intelligent email alerts")
        
        # Test email
        test = input("\n🧪 Send test email? (y/n): ").strip().lower()
        if test in ['y', 'yes']:
            email = input("📧 Enter test email address: ").strip()
            if email:
                service.test_email_notification(email)
    else:
        print("⚠️ Email service not configured")
        print("\n📋 To enable email notifications:")
        print("1. Update config/enterprise_config.yml")
        print("2. Add your Gmail credentials to messaging.smtp section")
        print("3. Use app password for Gmail (not regular password)")
    
    return service

if __name__ == "__main__":
    setup_email_notifications()