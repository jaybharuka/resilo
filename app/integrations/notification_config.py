#!/usr/bin/env python3
"""
Notification Configuration and Setup Guide
This file shows how to configure Discord and Slack integrations with real API keys
"""

import os
from typing import Dict, Optional

class NotificationConfig:
    """Configuration management for notification services"""
    
    def __init__(self):
        self.config = self.load_config()
    
    def load_config(self) -> Dict:
        """Load configuration from environment variables"""
        return {
            # Discord Configuration
            'discord': {
                'bot_token': os.getenv('DISCORD_BOT_TOKEN'),
                'guild_id': os.getenv('DISCORD_GUILD_ID'),  # Server ID
                'alert_channel_id': os.getenv('DISCORD_ALERT_CHANNEL', 'general'),
                'admin_channel_id': os.getenv('DISCORD_ADMIN_CHANNEL', 'admin'),
                'enabled': os.getenv('DISCORD_ENABLED', 'false').lower() == 'true'
            },
            
            # Slack Configuration
            'slack': {
                'webhook_url': os.getenv('SLACK_WEBHOOK_URL'),
                'bot_token': os.getenv('SLACK_BOT_TOKEN'),  # For advanced features
                'default_channel': os.getenv('SLACK_DEFAULT_CHANNEL', '#alerts'),
                'admin_channel': os.getenv('SLACK_ADMIN_CHANNEL', '#admin'),
                'enabled': os.getenv('SLACK_ENABLED', 'false').lower() == 'true'
            },
            
            # Email Configuration
            'email': {
                'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
                'smtp_port': int(os.getenv('SMTP_PORT', '587')),
                'username': os.getenv('EMAIL_USERNAME'),
                'password': os.getenv('EMAIL_PASSWORD'),
                'from_address': os.getenv('EMAIL_FROM'),
                'enabled': os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
            },
            
            # General Settings
            'demo_mode': os.getenv('NOTIFICATION_DEMO_MODE', 'true').lower() == 'true',
            'log_level': os.getenv('LOG_LEVEL', 'INFO')
        }
    
    def is_discord_enabled(self) -> bool:
        """Check if Discord is properly configured"""
        discord_config = self.config['discord']
        if self.config['demo_mode']:
            return True  # Always enabled in demo mode
        return (discord_config['enabled'] and 
                discord_config['bot_token'] is not None)
    
    def is_slack_enabled(self) -> bool:
        """Check if Slack is properly configured"""
        slack_config = self.config['slack']
        if self.config['demo_mode']:
            return True  # Always enabled in demo mode
        return (slack_config['enabled'] and 
                slack_config['webhook_url'] is not None)
    
    def get_discord_token(self) -> Optional[str]:
        """Get Discord bot token"""
        if self.config['demo_mode']:
            return "DEMO_TOKEN_123456789"
        return self.config['discord']['bot_token']
    
    def get_slack_webhook(self) -> Optional[str]:
        """Get Slack webhook URL"""
        if self.config['demo_mode']:
            return "https://hooks.slack.com/services/DEMO/WEBHOOK/URL"
        return self.config['slack']['webhook_url']
    
    def print_setup_guide(self):
        """Print setup instructions for production"""
        print("🔧 AIOps Notification Setup Guide")
        print("=" * 50)
        print()
        
        print("📱 DISCORD SETUP:")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Create a new application")
        print("3. Go to 'Bot' section and create a bot")
        print("4. Copy the bot token")
        print("5. Set environment variable:")
        print("   Windows: set DISCORD_BOT_TOKEN=your_bot_token")
        print("   Linux/Mac: export DISCORD_BOT_TOKEN=your_bot_token")
        print("6. Invite bot to your server with proper permissions")
        print()
        
        print("💬 SLACK SETUP:")
        print("1. Go to https://api.slack.com/apps")
        print("2. Create a new app")
        print("3. Enable 'Incoming Webhooks'")
        print("4. Create webhook for your channel")
        print("5. Copy the webhook URL")
        print("6. Set environment variable:")
        print("   Windows: set SLACK_WEBHOOK_URL=your_webhook_url")
        print("   Linux/Mac: export SLACK_WEBHOOK_URL=your_webhook_url")
        print()
        
        print("🎯 ENABLE PRODUCTION MODE:")
        print("Windows:")
        print("  set NOTIFICATION_DEMO_MODE=false")
        print("  set DISCORD_ENABLED=true")
        print("  set SLACK_ENABLED=true")
        print()
        print("Linux/Mac:")
        print("  export NOTIFICATION_DEMO_MODE=false")
        print("  export DISCORD_ENABLED=true")
        print("  export SLACK_ENABLED=true")
        print()
        
        print("📋 CURRENT STATUS:")
        print(f"  Demo Mode: {self.config['demo_mode']}")
        print(f"  Discord Enabled: {self.is_discord_enabled()}")
        print(f"  Slack Enabled: {self.is_slack_enabled()}")
        print(f"  Discord Token: {'✅ Set' if self.get_discord_token() else '❌ Missing'}")
        print(f"  Slack Webhook: {'✅ Set' if self.get_slack_webhook() else '❌ Missing'}")

def create_env_file():
    """Create a sample .env file for configuration"""
    env_content = """# AIOps Notification Configuration
# Copy this to .env and fill in your actual values

# Demo Mode (set to false for production)
NOTIFICATION_DEMO_MODE=true

# Discord Configuration
DISCORD_ENABLED=true
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_GUILD_ID=your_server_id
DISCORD_ALERT_CHANNEL=alerts
DISCORD_ADMIN_CHANNEL=admin

# Slack Configuration  
SLACK_ENABLED=true
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_DEFAULT_CHANNEL=#alerts
SLACK_ADMIN_CHANNEL=#admin

# Email Configuration
EMAIL_ENABLED=false
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USERNAME=your_email@company.com
EMAIL_PASSWORD=your_app_password
EMAIL_FROM=aiops@company.com

# Logging
LOG_LEVEL=INFO
"""
    
    with open('.env.example', 'w') as f:
        f.write(env_content)
    
    print("📝 Created .env.example file")
    print("Copy it to .env and fill in your actual values")

if __name__ == "__main__":
    config = NotificationConfig()
    config.print_setup_guide()
    
    print("\n" + "="*50)
    create_env_file()