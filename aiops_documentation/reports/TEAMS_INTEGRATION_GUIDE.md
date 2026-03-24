# Microsoft Teams Integration Setup Guide

## Overview
This guide shows you how to integrate Microsoft Teams with your AIOps bot for real-time notifications, alerts, and system monitoring updates.

## 🚀 Quick Start (Webhook Method - Easiest)

### 1. Set up Incoming Webhook in Teams
1. Go to your Teams channel
2. Click the "..." menu → "Connectors"
3. Search for "Incoming Webhook" → "Configure"
4. Name it "AIOps Bot" and upload a bot icon
5. Copy the webhook URL

### 2. Test Integration
```python
import asyncio
from teams_integration import send_aiops_alert, TeamsCredentials, MessageType

# Simple webhook setup (no Azure app registration needed)
webhook_url = "https://your-tenant.webhook.office.com/webhookb2/..."

# Send test alert
async def test_webhook():
    credentials = TeamsCredentials(
        tenant_id="",  # Not needed for webhook
        client_id="",  # Not needed for webhook  
        client_secret=""  # Not needed for webhook
    )
    
    await send_aiops_alert(
        credentials=credentials,
        webhook_url=webhook_url,
        title="AIOps Bot Test",
        message="Successfully connected to Microsoft Teams!",
        alert_type=MessageType.SUCCESS,
        system_data={'cpu': 45, 'memory': 60, 'disk': 30}
    )

# Run test
asyncio.run(test_webhook())
```

## 🔧 Advanced Setup (Graph API Method)

### 1. Register App in Azure AD
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to "Azure Active Directory" → "App registrations"
3. Click "New registration"
4. Name: "AIOps Teams Bot"
5. Account types: "Accounts in this organizational directory only"
6. Click "Register"

### 2. Configure API Permissions
1. Go to "API permissions" → "Add a permission"
2. Select "Microsoft Graph" → "Application permissions"
3. Add these permissions:
   - `Chat.ReadWrite.All` (for direct messages)
   - `ChannelMessage.Send` (for channel messages)
   - `Team.ReadBasic.All` (to list teams)
   - `Channel.ReadBasic.All` (to list channels)
4. Click "Grant admin consent"

### 3. Create Client Secret
1. Go to "Certificates & secrets"
2. Click "New client secret"
3. Description: "AIOps Bot Secret"
4. Expires: Choose duration (recommend 12 months)
5. Copy the secret value (you won't see it again!)

### 4. Get IDs
- **Tenant ID**: Azure AD → Overview → Directory (tenant) ID
- **Client ID**: App registration → Overview → Application (client) ID

## 📊 Integration with AIOps Bot

### Add to your main bot file:
```python
from teams_integration import MicrosoftTeamsIntegrator, TeamsAlert, MessageType, TeamsCredentials

class EnhancedAIOpsBot:
    def __init__(self):
        # ... existing init code ...
        
        # Teams integration
        self.teams_credentials = TeamsCredentials(
            tenant_id=os.getenv('TEAMS_TENANT_ID'),
            client_id=os.getenv('TEAMS_CLIENT_ID'),
            client_secret=os.getenv('TEAMS_CLIENT_SECRET'),
            webhook_url=os.getenv('TEAMS_WEBHOOK_URL')
        )
    
    async def send_teams_alert(self, title: str, message: str, alert_type: MessageType = MessageType.INFO):
        """Send alert to Teams"""
        try:
            alert = TeamsAlert(
                title=title,
                message=message,
                alert_type=alert_type,
                system_data=self.system_data
            )
            
            async with MicrosoftTeamsIntegrator(self.teams_credentials) as teams:
                # Send via webhook (easier)
                if self.teams_credentials.webhook_url:
                    await teams.send_webhook_message(self.teams_credentials.webhook_url, alert)
                # Or send to specific channel
                # await teams.send_channel_message("team-id", "channel-id", alert)
                
        except Exception as e:
            logger.error(f"Teams notification failed: {e}")
    
    async def monitor_and_alert(self):
        """Enhanced monitoring with Teams alerts"""
        self.update_system_data()
        
        # Check for alerts
        cpu_usage = self.system_data.get('cpu', {}).get('usage_percent', 0)
        memory_usage = self.system_data.get('memory', {}).get('percent', 0)
        
        # Send alerts based on thresholds
        if cpu_usage > 90:
            await self.send_teams_alert(
                title="🚨 Critical: High CPU Usage",
                message=f"CPU usage is at {cpu_usage}%! Immediate attention required.",
                alert_type=MessageType.CRITICAL
            )
        elif cpu_usage > 75:
            await self.send_teams_alert(
                title="⚠️ Warning: Elevated CPU Usage", 
                message=f"CPU usage is at {cpu_usage}%. Monitor closely.",
                alert_type=MessageType.WARNING
            )
        
        if memory_usage > 95:
            await self.send_teams_alert(
                title="🚨 Critical: High Memory Usage",
                message=f"Memory usage is at {memory_usage}%! System may become unstable.",
                alert_type=MessageType.CRITICAL
            )
```

## 🎯 Environment Variables

Add to your `.env` file:
```env
# Teams Integration (Webhook method - easiest)
TEAMS_WEBHOOK_URL=https://your-tenant.webhook.office.com/webhookb2/...

# Teams Integration (Graph API method - advanced)
TEAMS_TENANT_ID=your-tenant-id-here
TEAMS_CLIENT_ID=your-client-id-here
TEAMS_CLIENT_SECRET=your-client-secret-here
```

## 📱 Message Types and Features

### Alert Types
- `MessageType.INFO` - Blue info messages
- `MessageType.WARNING` - Yellow warning messages  
- `MessageType.CRITICAL` - Red critical alerts
- `MessageType.SUCCESS` - Green success messages

### Card Types
- **Simple**: Basic title + message
- **Detailed**: Includes system metrics and facts
- **Interactive**: Adds action buttons
- **Dashboard**: Metrics display with color coding

### Example Messages
```python
# System status update
await send_system_status(
    credentials=teams_credentials,
    webhook_url=webhook_url,
    cpu_usage=75.5,
    memory_usage=68.2, 
    disk_usage=45.8
)

# Custom alert with actions
alert = TeamsAlert(
    title="Service Restart Required",
    message="Database service needs restart due to memory leak",
    alert_type=MessageType.WARNING,
    system_data={'service': 'postgresql', 'memory_usage': '95%'},
    actions=[
        {'title': 'View Logs', 'url': 'http://localhost:5000/logs'},
        {'title': 'Restart Service', 'url': 'http://localhost:5000/restart/db'}
    ]
)
```

## 🔍 Testing Your Integration

### 1. Test Webhook
```bash
python -c "
import asyncio
from teams_integration import demo_teams_integration
asyncio.run(demo_teams_integration())
"
```

### 2. Test with Real Data
```python
# Add to your AIOps bot main loop
import asyncio
from teams_integration import send_system_status, TeamsCredentials

async def test_teams_with_real_data():
    credentials = TeamsCredentials(tenant_id='', client_id='', client_secret='')
    webhook_url = 'your-webhook-url'
    
    # Get real system data
    import psutil
    cpu = psutil.cpu_percent()
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    await send_system_status(credentials, webhook_url, cpu, memory, disk)

# Run the test
asyncio.run(test_teams_with_real_data())
```

## 🏆 Hackathon Demo Ideas

### 1. Real-time System Monitoring
- Send periodic status updates to Teams
- Alert on threshold breaches
- Beautiful dashboard cards

### 2. Interactive Alerts
- Action buttons to view dashboard
- Links to fix issues
- Escalation workflows

### 3. Chatbot Integration
- Teams messages trigger AIOps responses
- User can ask questions in Teams
- Bot responds with system analysis

### 4. Incident Management
- Automatic incident creation in Teams
- Status updates and resolution tracking
- Post-incident reports

## 🚨 Troubleshooting

### Common Issues
1. **401 Unauthorized**: Check tenant ID, client ID, secret
2. **403 Forbidden**: Grant admin consent for permissions
3. **Webhook fails**: Verify webhook URL is correct
4. **Cards not showing**: Check adaptive card schema

### Debug Steps
1. Test authentication separately
2. Verify permissions in Azure AD
3. Check Teams app installation
4. Test with simple text messages first

## 🎯 Next Steps

1. **Set up webhook** (5 minutes)
2. **Test basic alerts** (10 minutes)
3. **Integrate with AIOps bot** (15 minutes)
4. **Create custom card designs** (optional)
5. **Set up automated monitoring** (optional)

Your AIOps bot can now send professional Teams notifications! Perfect for impressing hackathon judges with enterprise collaboration features. 🚀