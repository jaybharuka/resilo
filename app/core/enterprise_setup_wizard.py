#!/usr/bin/env python3
"""
AIOps Bot - Enterprise Setup Wizard
Interactive setup script for configuring API keys and credentials for enterprise deployment.
"""

import getpass
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

import requests
import yaml
from enterprise_config_manager import EnterpriseConfigurationManager


class SetupWizard:
    def __init__(self):
        self.config_manager = EnterpriseConfigurationManager()
        self.setup_steps = [
            ("basic_setup", "Basic System Configuration"),
            ("communication", "Communication Platforms (Slack, Teams, Discord)"),
            ("cloud_platforms", "Cloud Platform Integration (AWS, Azure, GCP)"),
            ("monitoring", "Monitoring and APM Tools"),
            ("security", "Security and Threat Intelligence"),
            ("databases", "Database Connections"),
            ("itsm", "ITSM and Ticketing Systems"),
            ("identity", "Identity and Access Management"),
            ("optional", "Optional Integrations")
        ]
        
    def run_setup(self):
        """Run the complete setup wizard"""
        print("🚀 AIOps Bot Enterprise Setup Wizard")
        print("=" * 50)
        print("This wizard will guide you through configuring API keys and credentials")
        print("for enterprise deployment of the AIOps Bot.\n")
        
        # Show current status
        self.config_manager.print_configuration_status()
        
        print("\nSetup Steps:")
        for i, (step_id, description) in enumerate(self.setup_steps, 1):
            print(f"  {i}. {description}")
        
        print("\nLet's get started!")
        
        for step_id, description in self.setup_steps:
            if self._confirm_step(description):
                getattr(self, f"setup_{step_id}")()
        
        # Final validation and generation
        self._finalize_setup()
    
    def _confirm_step(self, description: str) -> bool:
        """Ask user if they want to configure this step"""
        while True:
            response = input(f"\n📋 Configure {description}? (y/n/skip): ").lower().strip()
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no', 'skip']:
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no/skip")
    
    def _get_input(self, prompt: str, required: bool = True, secret: bool = False) -> Optional[str]:
        """Get user input with validation"""
        while True:
            if secret:
                value = getpass.getpass(f"{prompt}: ")
            else:
                value = input(f"{prompt}: ").strip()
            
            if value:
                return value
            elif not required:
                return None
            else:
                print("This field is required. Please enter a value.")
    
    def _test_api_key(self, service: str, api_key: str, base_url: str = None) -> bool:
        """Test an API key"""
        print(f"🔍 Testing {service} API key...")
        
        try:
            if service.lower() == 'slack':
                return self._test_slack_api(api_key)
            elif service.lower() == 'virustotal':
                return self._test_virustotal_api(api_key)
            elif service.lower() == 'aws':
                return self._test_aws_credentials()
            else:
                print(f"⚠️  No test available for {service} - assuming valid")
                return True
        except Exception as e:
            print(f"❌ API test failed: {e}")
            return False
    
    def _test_slack_api(self, token: str) -> bool:
        """Test Slack API token"""
        try:
            response = requests.get(
                'https://slack.com/api/auth.test',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )
            if response.json().get('ok'):
                print("✅ Slack API test successful")
                return True
            else:
                print("❌ Slack API test failed")
                return False
        except Exception as e:
            print(f"❌ Slack API test error: {e}")
            return False
    
    def _test_virustotal_api(self, api_key: str) -> bool:
        """Test VirusTotal API key"""
        try:
            response = requests.get(
                f'https://www.virustotal.com/vtapi/v2/file/report',
                params={'apikey': api_key, 'resource': 'test'},
                timeout=10
            )
            if response.status_code == 200:
                print("✅ VirusTotal API test successful")
                return True
            else:
                print("❌ VirusTotal API test failed")
                return False
        except Exception as e:
            print(f"❌ VirusTotal API test error: {e}")
            return False
    
    def _test_aws_credentials(self) -> bool:
        """Test AWS credentials"""
        try:
            import boto3
        except ImportError:
            print("⚠️ boto3 not installed - AWS features will be unavailable")
            return False
        
        try:
            client = boto3.client('sts')
            response = client.get_caller_identity()
            print("✅ AWS credentials test successful")
            return True
        except Exception as e:
            print(f"❌ AWS credentials test failed: {e}")
            return False
    
    def setup_basic_setup(self):
        """Setup basic system configuration"""
        print("\n🔧 Basic System Configuration")
        print("-" * 30)
        
        environment = self._get_input("Environment (production/staging/development)", required=False) or "production"
        log_level = self._get_input("Log Level (DEBUG/INFO/WARNING/ERROR)", required=False) or "INFO"
        
        print(f"✅ Basic setup configured: {environment} environment with {log_level} logging")
    
    def setup_communication(self):
        """Setup communication platforms"""
        print("\n💬 Communication Platform Setup")
        print("-" * 35)
        
        # Slack Setup
        if self._confirm_step("Slack Integration"):
            print("\n📱 Slack Configuration:")
            print("1. Go to https://api.slack.com/apps")
            print("2. Create a new app or select existing app")
            print("3. Go to 'OAuth & Permissions' and copy the Bot User OAuth Token")
            
            slack_token = self._get_input("Slack Bot Token (xoxb-...)", secret=True)
            if slack_token and self._test_api_key("slack", slack_token):
                self.config_manager.set_credential("communication_slack", slack_token)
                
                webhook_url = self._get_input("Slack Webhook URL (optional)", required=False)
                if webhook_url:
                    # Store webhook URL in additional params
                    pass
        
        # Microsoft Teams Setup
        if self._confirm_step("Microsoft Teams Integration"):
            print("\n🏢 Microsoft Teams Configuration:")
            print("1. Register app in Azure Active Directory")
            print("2. Configure Teams webhook")
            
            teams_webhook = self._get_input("Teams Webhook URL", secret=True)
            if teams_webhook:
                self.config_manager.set_credential("communication_teams", teams_webhook)
        
        # Discord Setup
        if self._confirm_step("Discord Integration"):
            print("\n🎮 Discord Configuration:")
            print("1. Go to https://discord.com/developers/applications")
            print("2. Create application and bot")
            print("3. Copy bot token")
            
            discord_token = self._get_input("Discord Bot Token", secret=True)
            if discord_token:
                self.config_manager.set_credential("communication_discord", discord_token)
    
    def setup_cloud_platforms(self):
        """Setup cloud platform integrations"""
        print("\n☁️  Cloud Platform Integration")
        print("-" * 32)
        
        # AWS Setup
        if self._confirm_step("AWS Integration"):
            print("\n🟧 AWS Configuration:")
            print("1. Create IAM user with appropriate permissions")
            print("2. Generate access keys")
            
            aws_access_key = self._get_input("AWS Access Key ID", secret=True)
            aws_secret_key = self._get_input("AWS Secret Access Key", secret=True)
            aws_region = self._get_input("AWS Region", required=False) or "us-east-1"
            
            if aws_access_key and aws_secret_key:
                # Set environment variables for testing
                os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key
                os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
                os.environ['AWS_DEFAULT_REGION'] = aws_region
                
                if self._test_api_key("aws", aws_access_key):
                    self.config_manager.set_credential("cloud_platforms_aws_access_key", aws_access_key)
                    self.config_manager.set_credential("cloud_platforms_aws_secret_key", aws_secret_key)
        
        # Azure Setup
        if self._confirm_step("Azure Integration"):
            print("\n🔵 Azure Configuration:")
            print("1. Register application in Azure AD")
            print("2. Create service principal")
            print("3. Note tenant ID, client ID, and client secret")
            
            tenant_id = self._get_input("Azure Tenant ID")
            client_id = self._get_input("Azure Client ID")
            client_secret = self._get_input("Azure Client Secret", secret=True)
            subscription_id = self._get_input("Azure Subscription ID")
            
            if all([tenant_id, client_id, client_secret, subscription_id]):
                self.config_manager.set_credential("cloud_platforms_azure_tenant", tenant_id)
                self.config_manager.set_credential("cloud_platforms_azure_client", client_id)
                self.config_manager.set_credential("cloud_platforms_azure_secret", client_secret)
        
        # Google Cloud Setup
        if self._confirm_step("Google Cloud Integration"):
            print("\n🟢 Google Cloud Configuration:")
            print("1. Create service account in GCP Console")
            print("2. Download JSON key file")
            print("3. Extract required fields")
            
            project_id = self._get_input("GCP Project ID")
            service_account_key = self._get_input("Service Account Key (JSON content)", secret=True)
            
            if project_id and service_account_key:
                self.config_manager.set_credential("cloud_platforms_gcp_project", project_id)
                self.config_manager.set_credential("cloud_platforms_gcp_key", service_account_key)
    
    def setup_monitoring(self):
        """Setup monitoring and APM tools"""
        print("\n📊 Monitoring and APM Tools")
        print("-" * 30)
        
        # Datadog
        if self._confirm_step("Datadog Integration"):
            print("\n🐕 Datadog Configuration:")
            datadog_api_key = self._get_input("Datadog API Key", secret=True)
            datadog_app_key = self._get_input("Datadog Application Key", secret=True)
            
            if datadog_api_key and datadog_app_key:
                self.config_manager.set_credential("monitoring_datadog_api", datadog_api_key)
                self.config_manager.set_credential("monitoring_datadog_app", datadog_app_key)
        
        # New Relic
        if self._confirm_step("New Relic Integration"):
            print("\n📈 New Relic Configuration:")
            newrelic_api_key = self._get_input("New Relic API Key", secret=True)
            
            if newrelic_api_key:
                self.config_manager.set_credential("monitoring_newrelic", newrelic_api_key)
        
        # Splunk
        if self._confirm_step("Splunk Integration"):
            print("\n🔍 Splunk Configuration:")
            splunk_host = self._get_input("Splunk Host")
            splunk_username = self._get_input("Splunk Username")
            splunk_password = self._get_input("Splunk Password", secret=True)
            
            if all([splunk_host, splunk_username, splunk_password]):
                self.config_manager.set_credential("monitoring_splunk_host", splunk_host)
                self.config_manager.set_credential("monitoring_splunk_user", splunk_username)
                self.config_manager.set_credential("monitoring_splunk_pass", splunk_password)
    
    def setup_security(self):
        """Setup security and threat intelligence"""
        print("\n🔒 Security and Threat Intelligence")
        print("-" * 38)
        
        # VirusTotal
        if self._confirm_step("VirusTotal Integration"):
            print("\n🦠 VirusTotal Configuration:")
            print("1. Sign up at https://www.virustotal.com/")
            print("2. Go to your profile and copy API key")
            
            vt_api_key = self._get_input("VirusTotal API Key", secret=True)
            if vt_api_key and self._test_api_key("virustotal", vt_api_key):
                self.config_manager.set_credential("threat_intelligence_virustotal", vt_api_key)
        
        # AbuseIPDB
        if self._confirm_step("AbuseIPDB Integration"):
            print("\n🚫 AbuseIPDB Configuration:")
            abuseipdb_key = self._get_input("AbuseIPDB API Key", secret=True)
            
            if abuseipdb_key:
                self.config_manager.set_credential("threat_intelligence_abuseipdb", abuseipdb_key)
        
        # MISP
        if self._confirm_step("MISP Integration"):
            print("\n🔗 MISP Configuration:")
            misp_url = self._get_input("MISP Instance URL")
            misp_key = self._get_input("MISP API Key", secret=True)
            
            if misp_url and misp_key:
                self.config_manager.set_credential("threat_intelligence_misp_url", misp_url)
                self.config_manager.set_credential("threat_intelligence_misp_key", misp_key)
    
    def setup_databases(self):
        """Setup database connections"""
        print("\n🗄️  Database Configuration")
        print("-" * 25)
        
        # PostgreSQL
        if self._confirm_step("PostgreSQL Database"):
            pg_host = self._get_input("PostgreSQL Host")
            pg_database = self._get_input("Database Name")
            pg_username = self._get_input("Username")
            pg_password = self._get_input("Password", secret=True)
            
            if all([pg_host, pg_database, pg_username, pg_password]):
                connection_string = f"postgresql://{pg_username}:{pg_password}@{pg_host}:5432/{pg_database}"
                self.config_manager.set_credential("databases_postgresql", connection_string)
        
        # Redis
        if self._confirm_step("Redis Cache"):
            redis_host = self._get_input("Redis Host")
            redis_password = self._get_input("Redis Password (optional)", required=False, secret=True)
            
            if redis_host:
                if redis_password:
                    redis_url = f"redis://:{redis_password}@{redis_host}:6379/0"
                else:
                    redis_url = f"redis://{redis_host}:6379/0"
                self.config_manager.set_credential("databases_redis", redis_url)
    
    def setup_itsm(self):
        """Setup ITSM and ticketing systems"""
        print("\n🎫 ITSM and Ticketing Systems")
        print("-" * 32)
        
        # ServiceNow
        if self._confirm_step("ServiceNow Integration"):
            snow_instance = self._get_input("ServiceNow Instance (e.g., dev12345)")
            snow_username = self._get_input("ServiceNow Username")
            snow_password = self._get_input("ServiceNow Password", secret=True)
            
            if all([snow_instance, snow_username, snow_password]):
                self.config_manager.set_credential("itsm_servicenow_instance", snow_instance)
                self.config_manager.set_credential("itsm_servicenow_user", snow_username)
                self.config_manager.set_credential("itsm_servicenow_pass", snow_password)
        
        # Jira
        if self._confirm_step("Jira Integration"):
            jira_server = self._get_input("Jira Server URL")
            jira_username = self._get_input("Jira Username/Email")
            jira_token = self._get_input("Jira API Token", secret=True)
            
            if all([jira_server, jira_username, jira_token]):
                self.config_manager.set_credential("itsm_jira_server", jira_server)
                self.config_manager.set_credential("itsm_jira_user", jira_username)
                self.config_manager.set_credential("itsm_jira_token", jira_token)
    
    def setup_identity(self):
        """Setup identity and access management"""
        print("\n👤 Identity and Access Management")
        print("-" * 35)
        
        # Active Directory
        if self._confirm_step("Active Directory Integration"):
            ad_domain = self._get_input("AD Domain")
            ad_server = self._get_input("AD Server")
            ad_username = self._get_input("AD Service Account Username")
            ad_password = self._get_input("AD Service Account Password", secret=True)
            
            if all([ad_domain, ad_server, ad_username, ad_password]):
                self.config_manager.set_credential("identity_ad_domain", ad_domain)
                self.config_manager.set_credential("identity_ad_server", ad_server)
                self.config_manager.set_credential("identity_ad_user", ad_username)
                self.config_manager.set_credential("identity_ad_pass", ad_password)
        
        # Okta
        if self._confirm_step("Okta Integration"):
            okta_domain = self._get_input("Okta Domain (e.g., dev-123456.okta.com)")
            okta_token = self._get_input("Okta API Token", secret=True)
            
            if okta_domain and okta_token:
                self.config_manager.set_credential("identity_okta_domain", okta_domain)
                self.config_manager.set_credential("identity_okta_token", okta_token)
    
    def setup_optional(self):
        """Setup optional integrations"""
        print("\n⚡ Optional Integrations")
        print("-" * 25)
        
        # Email/SMTP
        if self._confirm_step("Email/SMTP Configuration"):
            smtp_server = self._get_input("SMTP Server")
            smtp_username = self._get_input("SMTP Username")
            smtp_password = self._get_input("SMTP Password", secret=True)
            
            if all([smtp_server, smtp_username, smtp_password]):
                self.config_manager.set_credential("messaging_smtp_server", smtp_server)
                self.config_manager.set_credential("messaging_smtp_user", smtp_username)
                self.config_manager.set_credential("messaging_smtp_pass", smtp_password)
        
        # Twilio (SMS)
        if self._confirm_step("Twilio SMS Integration"):
            twilio_sid = self._get_input("Twilio Account SID")
            twilio_token = self._get_input("Twilio Auth Token", secret=True)
            twilio_number = self._get_input("Twilio Phone Number")
            
            if all([twilio_sid, twilio_token, twilio_number]):
                self.config_manager.set_credential("messaging_twilio_sid", twilio_sid)
                self.config_manager.set_credential("messaging_twilio_token", twilio_token)
                self.config_manager.set_credential("messaging_twilio_number", twilio_number)
    
    def _finalize_setup(self):
        """Finalize setup and generate deployment files"""
        print("\n🎯 Finalizing Setup")
        print("=" * 20)
        
        # Validate all configurations
        print("Validating configurations...")
        validation_results = self.config_manager.validate_all_credentials()
        configured_count = sum(1 for valid in validation_results.values() if valid)
        total_count = len(validation_results)
        
        print(f"✅ Configuration complete: {configured_count}/{total_count} services configured")
        
        # Generate deployment files
        print("\nGenerating deployment files...")
        
        if self._confirm_step("Generate .env file for Docker"):
            self.config_manager.generate_environment_file()
        
        if self._confirm_step("Generate Kubernetes secrets"):
            self.config_manager.generate_kubernetes_secrets()
        
        # Security recommendations
        print("\n🔒 Security Recommendations:")
        print("1. Store API keys in a secure vault (HashiCorp Vault, AWS Secrets Manager)")
        print("2. Rotate API keys regularly (every 90 days)")
        print("3. Use least-privilege access for all integrations")
        print("4. Monitor API key usage and set up alerts")
        print("5. Encrypt all configuration files in production")
        
        # Next steps
        print("\n🚀 Next Steps:")
        print("1. Review generated configuration files")
        print("2. Test API connections: python enterprise_config_manager.py")
        print("3. Deploy using Docker: docker-compose up -d")
        print("4. Or deploy to Kubernetes: kubectl apply -f k8s-secrets.yml")
        print("5. Monitor system health in the AIOps dashboard")
        
        print(f"\n🎉 Enterprise setup complete!")
        print("Your AIOps Bot is ready for production deployment!")


def main():
    """Main function to run the setup wizard"""
    try:
        wizard = SetupWizard()
        wizard.run_setup()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup interrupted by user")
        print("You can resume setup by running this script again")
    except Exception as e:
        print(f"\n❌ Setup failed with error: {e}")
        print("Please check the error and try again")


if __name__ == "__main__":
    main()