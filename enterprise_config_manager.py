"""
AIOps Bot - Enterprise Configuration Template
This file provides a comprehensive template for configuring API keys and credentials
for enterprise deployment of the AIOps Bot system.
"""

import os
import json
import yaml
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from cryptography.fernet import Fernet
import base64
import logging

@dataclass
class APICredentials:
    """Base class for API credentials"""
    service_name: str
    api_key: str
    additional_params: Dict[str, Any] = field(default_factory=dict)
    is_encrypted: bool = False
    
class EnterpriseConfigurationManager:
    """
    Manages API keys and configuration for enterprise deployment
    """
    
    def __init__(self, config_file: str = "config/enterprise_config.yml"):
        self.config_file = config_file
        self.encryption_key = self._get_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        self.credentials: Dict[str, APICredentials] = {}
        self._load_configuration()
    
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key for sensitive data"""
        key_file = "config/encryption.key"
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(key_file), exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(key)
            return key
    
    def _load_configuration(self):
        """Load configuration from file"""
        if not os.path.exists(self.config_file):
            self._create_template_config()
            return
        
        with open(self.config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Load credentials
        for section, services in config.get('credentials', {}).items():
            for service, creds in services.items():
                self.credentials[f"{section}_{service}"] = APICredentials(
                    service_name=service,
                    api_key=creds.get('api_key', ''),
                    additional_params=creds,
                    is_encrypted=creds.get('encrypted', False)
                )
    
    def _create_template_config(self):
        """Create template configuration file"""
        template_config = {
            'environment': 'production',
            'debug': False,
            'log_level': 'INFO',
            
            'credentials': {
                'threat_intelligence': {
                    'virustotal': {
                        'api_key': 'YOUR_VIRUSTOTAL_API_KEY',
                        'base_url': 'https://www.virustotal.com/vtapi/v2/',
                        'rate_limit': 4,
                        'encrypted': False
                    },
                    'threatconnect': {
                        'api_key': 'YOUR_THREATCONNECT_API_KEY',
                        'secret_key': 'YOUR_THREATCONNECT_SECRET_KEY',
                        'base_url': 'https://api.threatconnect.com',
                        'encrypted': True
                    },
                    'misp': {
                        'api_key': 'YOUR_MISP_API_KEY',
                        'base_url': 'https://your-misp-instance.com',
                        'verify_ssl': True,
                        'encrypted': True
                    },
                    'abuseipdb': {
                        'api_key': 'YOUR_ABUSEIPDB_API_KEY',
                        'base_url': 'https://api.abuseipdb.com/api/v2/',
                        'encrypted': False
                    }
                },
                
                'vulnerability_scanners': {
                    'nessus': {
                        'access_key': 'YOUR_NESSUS_ACCESS_KEY',
                        'secret_key': 'YOUR_NESSUS_SECRET_KEY',
                        'base_url': 'https://cloud.tenable.com',
                        'encrypted': True
                    },
                    'qualys': {
                        'username': 'YOUR_QUALYS_USERNAME',
                        'password': 'YOUR_QUALYS_PASSWORD',
                        'base_url': 'https://qualysapi.qualys.com',
                        'encrypted': True
                    },
                    'rapid7': {
                        'api_key': 'YOUR_RAPID7_API_KEY',
                        'base_url': 'https://us.api.insight.rapid7.com',
                        'encrypted': True
                    }
                },
                
                'cloud_platforms': {
                    'aws': {
                        'access_key_id': 'YOUR_AWS_ACCESS_KEY_ID',
                        'secret_access_key': 'YOUR_AWS_SECRET_ACCESS_KEY',
                        'region': 'us-east-1',
                        'services': ['cloudwatch', 'ec2', 's3', 'lambda'],
                        'encrypted': True
                    },
                    'azure': {
                        'tenant_id': 'YOUR_AZURE_TENANT_ID',
                        'client_id': 'YOUR_AZURE_CLIENT_ID',
                        'client_secret': 'YOUR_AZURE_CLIENT_SECRET',
                        'subscription_id': 'YOUR_AZURE_SUBSCRIPTION_ID',
                        'encrypted': True
                    },
                    'gcp': {
                        'project_id': 'YOUR_GCP_PROJECT_ID',
                        'private_key_id': 'YOUR_GCP_PRIVATE_KEY_ID',
                        'private_key': 'YOUR_GCP_PRIVATE_KEY',
                        'client_email': 'YOUR_GCP_CLIENT_EMAIL',
                        'encrypted': True
                    }
                },
                
                'monitoring_tools': {
                    'datadog': {
                        'api_key': 'YOUR_DATADOG_API_KEY',
                        'app_key': 'YOUR_DATADOG_APP_KEY',
                        'site': 'datadoghq.com',
                        'encrypted': True
                    },
                    'new_relic': {
                        'api_key': 'YOUR_NEWRELIC_API_KEY',
                        'account_id': 'YOUR_NEWRELIC_ACCOUNT_ID',
                        'encrypted': True
                    },
                    'splunk': {
                        'host': 'YOUR_SPLUNK_HOST',
                        'port': 8089,
                        'username': 'YOUR_SPLUNK_USERNAME',
                        'password': 'YOUR_SPLUNK_PASSWORD',
                        'encrypted': True
                    },
                    'elastic': {
                        'host': 'YOUR_ELASTICSEARCH_HOST',
                        'port': 9200,
                        'api_key': 'YOUR_ELASTIC_API_KEY',
                        'encrypted': True
                    }
                },
                
                'communication': {
                    'slack': {
                        'bot_token': 'xoxb-YOUR-SLACK-BOT-TOKEN',
                        'signing_secret': 'YOUR_SLACK_SIGNING_SECRET',
                        'webhook_url': 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
                        'encrypted': True
                    },
                    'microsoft_teams': {
                        'webhook_url': 'https://outlook.office.com/webhook/YOUR/WEBHOOK/URL',
                        'app_id': 'YOUR_TEAMS_APP_ID',
                        'app_password': 'YOUR_TEAMS_APP_PASSWORD',
                        'encrypted': True
                    },
                    'discord': {
                        'bot_token': 'YOUR_DISCORD_BOT_TOKEN',
                        'guild_id': 'YOUR_DISCORD_GUILD_ID',
                        'encrypted': True
                    },
                    'pagerduty': {
                        'integration_key': 'YOUR_PAGERDUTY_INTEGRATION_KEY',
                        'api_token': 'YOUR_PAGERDUTY_API_TOKEN',
                        'encrypted': True
                    }
                },
                
                'messaging': {
                    'smtp': {
                        'server': 'smtp.gmail.com',
                        'port': 587,
                        'username': 'your-email@company.com',
                        'password': 'YOUR_EMAIL_APP_PASSWORD',
                        'use_tls': True,
                        'encrypted': True
                    },
                    'twilio': {
                        'account_sid': 'YOUR_TWILIO_ACCOUNT_SID',
                        'auth_token': 'YOUR_TWILIO_AUTH_TOKEN',
                        'from_number': '+1234567890',
                        'encrypted': True
                    },
                    'sendgrid': {
                        'api_key': 'YOUR_SENDGRID_API_KEY',
                        'from_email': 'noreply@company.com',
                        'encrypted': True
                    }
                },
                
                'itsm': {
                    'servicenow': {
                        'instance': 'YOUR_SERVICENOW_INSTANCE',
                        'username': 'YOUR_SERVICENOW_USERNAME',
                        'password': 'YOUR_SERVICENOW_PASSWORD',
                        'encrypted': True
                    },
                    'jira': {
                        'server': 'https://your-company.atlassian.net',
                        'username': 'YOUR_JIRA_USERNAME',
                        'api_token': 'YOUR_JIRA_API_TOKEN',
                        'encrypted': True
                    },
                    'remedy': {
                        'server': 'YOUR_REMEDY_SERVER',
                        'username': 'YOUR_REMEDY_USERNAME',
                        'password': 'YOUR_REMEDY_PASSWORD',
                        'encrypted': True
                    }
                },
                
                'identity': {
                    'active_directory': {
                        'domain': 'YOUR_AD_DOMAIN',
                        'username': 'YOUR_AD_USERNAME',
                        'password': 'YOUR_AD_PASSWORD',
                        'server': 'YOUR_AD_SERVER',
                        'encrypted': True
                    },
                    'okta': {
                        'domain': 'YOUR_OKTA_DOMAIN',
                        'api_token': 'YOUR_OKTA_API_TOKEN',
                        'encrypted': True
                    },
                    'auth0': {
                        'domain': 'YOUR_AUTH0_DOMAIN',
                        'client_id': 'YOUR_AUTH0_CLIENT_ID',
                        'client_secret': 'YOUR_AUTH0_CLIENT_SECRET',
                        'encrypted': True
                    }
                },
                
                'databases': {
                    'postgresql': {
                        'host': 'YOUR_POSTGRES_HOST',
                        'port': 5432,
                        'database': 'aiops_production',
                        'username': 'YOUR_POSTGRES_USERNAME',
                        'password': 'YOUR_POSTGRES_PASSWORD',
                        'encrypted': True
                    },
                    'mysql': {
                        'host': 'YOUR_MYSQL_HOST',
                        'port': 3306,
                        'database': 'aiops_production',
                        'username': 'YOUR_MYSQL_USERNAME',
                        'password': 'YOUR_MYSQL_PASSWORD',
                        'encrypted': True
                    },
                    'mongodb': {
                        'connection_string': 'mongodb://username:password@host:port/database',
                        'encrypted': True
                    },
                    'redis': {
                        'host': 'YOUR_REDIS_HOST',
                        'port': 6379,
                        'password': 'YOUR_REDIS_PASSWORD',
                        'encrypted': True
                    }
                }
            },
            
            'security': {
                'encryption_key': 'YOUR_32_CHAR_ENCRYPTION_KEY',
                'jwt_secret': 'YOUR_JWT_SECRET_KEY',
                'api_rate_limit': 1000,
                'enable_2fa': True,
                'session_timeout': 3600
            },
            
            'ssl': {
                'cert_file': '/path/to/ssl/certificate.crt',
                'key_file': '/path/to/ssl/private.key',
                'ca_file': '/path/to/ssl/ca-bundle.crt'
            },
            
            'external_apis': {
                'timeout': 30,
                'retry_attempts': 3,
                'retry_delay': 5,
                'max_concurrent_requests': 100
            },
            
            'ml': {
                'model_storage_path': '/data/models/',
                'training_schedule': '0 2 * * *',
                'max_training_time': 3600,
                'model_backup_retention': 30
            },
            
            'logging': {
                'level': 'INFO',
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'file': '/var/log/aiops/aiops.log',
                'max_size': '100MB',
                'backup_count': 10
            }
        }
        
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as f:
            yaml.dump(template_config, f, default_flow_style=False, indent=2)
        
        print(f"Template configuration created at: {self.config_file}")
        print("Please update the API keys and credentials before deployment!")
    
    def encrypt_credential(self, credential_value: str) -> str:
        """Encrypt a credential value"""
        return self.cipher_suite.encrypt(credential_value.encode()).decode()
    
    def decrypt_credential(self, encrypted_value: str) -> str:
        """Decrypt a credential value"""
        return self.cipher_suite.decrypt(encrypted_value.encode()).decode()
    
    def get_credential(self, service_path: str, decrypt: bool = True) -> Optional[str]:
        """
        Get credential by service path (e.g., 'threat_intelligence_virustotal')
        """
        if service_path not in self.credentials:
            return None
        
        credential = self.credentials[service_path]
        api_key = credential.api_key
        
        if credential.is_encrypted and decrypt:
            try:
                api_key = self.decrypt_credential(api_key)
            except Exception as e:
                logging.error(f"Failed to decrypt credential for {service_path}: {e}")
                return None
        
        return api_key
    
    def set_credential(self, service_path: str, api_key: str, encrypt: bool = True):
        """Set or update a credential"""
        encrypted_key = self.encrypt_credential(api_key) if encrypt else api_key
        
        if service_path in self.credentials:
            self.credentials[service_path].api_key = encrypted_key
            self.credentials[service_path].is_encrypted = encrypt
        else:
            self.credentials[service_path] = APICredentials(
                service_name=service_path,
                api_key=encrypted_key,
                is_encrypted=encrypt
            )
    
    def validate_all_credentials(self) -> Dict[str, bool]:
        """Validate all configured credentials"""
        validation_results = {}
        
        for service_path, credential in self.credentials.items():
            try:
                # Basic validation - check if credential is not placeholder
                api_key = self.get_credential(service_path)
                is_valid = (api_key and 
                           not api_key.startswith('YOUR_') and 
                           len(api_key) > 10)
                validation_results[service_path] = is_valid
            except Exception as e:
                validation_results[service_path] = False
                logging.error(f"Validation failed for {service_path}: {e}")
        
        return validation_results
    
    def generate_environment_file(self, output_file: str = ".env"):
        """Generate environment file for Docker/container deployment"""
        env_vars = []
        
        for service_path, credential in self.credentials.items():
            env_name = service_path.upper().replace('_', '_')
            api_key = self.get_credential(service_path)
            if api_key and not api_key.startswith('YOUR_'):
                env_vars.append(f"{env_name}_API_KEY={api_key}")
        
        with open(output_file, 'w') as f:
            f.write("# AIOps Bot Environment Variables\n")
            f.write("# Generated automatically - do not edit manually\n\n")
            for var in env_vars:
                f.write(f"{var}\n")
        
        print(f"Environment file generated: {output_file}")
    
    def generate_kubernetes_secrets(self, output_file: str = "k8s-secrets.yml"):
        """Generate Kubernetes secrets YAML"""
        secrets_data = {}
        
        for service_path, credential in self.credentials.items():
            api_key = self.get_credential(service_path)
            if api_key and not api_key.startswith('YOUR_'):
                key_name = service_path.replace('_', '-')
                secrets_data[key_name] = base64.b64encode(api_key.encode()).decode()
        
        k8s_secret = {
            'apiVersion': 'v1',
            'kind': 'Secret',
            'metadata': {
                'name': 'aiops-secrets',
                'namespace': 'default'
            },
            'type': 'Opaque',
            'data': secrets_data
        }
        
        with open(output_file, 'w') as f:
            yaml.dump(k8s_secret, f, default_flow_style=False, indent=2)
        
        print(f"Kubernetes secrets file generated: {output_file}")
    
    def test_api_connections(self) -> Dict[str, Dict[str, Any]]:
        """Test connections to configured APIs"""
        test_results = {}
        
        # Test Slack connection
        slack_token = self.get_credential('communication_slack')
        if slack_token and not slack_token.startswith('YOUR_'):
            test_results['slack'] = self._test_slack_connection(slack_token)
        
        # Test AWS connection
        aws_key = self.get_credential('cloud_platforms_aws')
        if aws_key and not aws_key.startswith('YOUR_'):
            test_results['aws'] = self._test_aws_connection()
        
        # Add more API tests as needed
        
        return test_results
    
    def _test_slack_connection(self, token: str) -> Dict[str, Any]:
        """Test Slack API connection"""
        try:
            import requests
            response = requests.get(
                'https://slack.com/api/auth.test',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )
            return {
                'status': 'success' if response.json().get('ok') else 'failed',
                'response': response.json()
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def _test_aws_connection(self) -> Dict[str, Any]:
        """Test AWS API connection"""
        try:
            import boto3
        except ImportError:
            return {
                "status": "error",
                "message": "boto3 not installed - AWS features unavailable",
                "timestamp": datetime.now().isoformat()
            }
        
        try:
            client = boto3.client('sts')
            response = client.get_caller_identity()
            return {'status': 'success', 'account': response.get('Account')}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def print_configuration_status(self):
        """Print current configuration status"""
        print("\n" + "="*60)
        print("AIOps Bot - Enterprise Configuration Status")
        print("="*60)
        
        validation_results = self.validate_all_credentials()
        configured_count = sum(1 for valid in validation_results.values() if valid)
        total_count = len(validation_results)
        
        print(f"Configuration Progress: {configured_count}/{total_count} services configured")
        completion_rate = (configured_count/total_count)*100 if total_count > 0 else 0
        print(f"Completion: {completion_rate:.1f}%")
        
        print("\nService Status:")
        for service, is_valid in validation_results.items():
            status = "✅ Configured" if is_valid else "❌ Not Configured"
            print(f"  {service:40} {status}")
        
        if configured_count < total_count:
            print(f"\n⚠️  {total_count - configured_count} services need configuration")
            print("Please update the configuration file with valid API keys.")
        else:
            print("\n🎉 All services are configured!")


def main():
    """Main function to demonstrate configuration management"""
    print("AIOps Bot - Enterprise Configuration Manager")
    print("=" * 50)
    
    # Initialize configuration manager
    config_manager = EnterpriseConfigurationManager()
    
    # Print configuration status
    config_manager.print_configuration_status()
    
    # Generate deployment files
    print("\nGenerating deployment files...")
    config_manager.generate_environment_file()
    config_manager.generate_kubernetes_secrets()
    
    # Test API connections (if credentials are configured)
    print("\nTesting API connections...")
    test_results = config_manager.test_api_connections()
    for service, result in test_results.items():
        status = result.get('status', 'unknown')
        print(f"  {service}: {status}")
    
    print("\n✅ Configuration management complete!")
    print("\nNext steps:")
    print("1. Update config/enterprise_config.yml with your API keys")
    print("2. Run this script again to validate configurations")
    print("3. Deploy using generated .env or k8s-secrets.yml files")


if __name__ == "__main__":
    main()