#!/usr/bin/env sh
# Vault initialisation script — run once after first `docker-compose up`
# Populates all AIOps Bot secrets into Vault so they can be removed from
# enterprise_config.yaml / .env files.
#
# Usage:
#   docker exec -it aiops-vault sh /vault/init/init-vault.sh
#
# Requirements:
#   - Vault is running in dev mode (VAULT_DEV_ROOT_TOKEN_ID=aiops-root-token)

set -e

export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="aiops-root-token"

echo "==> Enabling KV v2 secrets engine..."
vault secrets enable -version=2 -path=secret kv 2>/dev/null || echo "  (already enabled)"

echo "==> Writing AIOps secrets..."

# Notification credentials
vault kv put secret/aiops/discord \
  webhook_url="${DISCORD_WEBHOOK_URL:-changeme}" \
  bot_token="${DISCORD_BOT_TOKEN:-changeme}" \
  guild_id="${DISCORD_GUILD_ID:-changeme}" \
  alert_channel="${DISCORD_ALERT_CHANNEL:-changeme}"

vault kv put secret/aiops/slack \
  webhook_url="${SLACK_WEBHOOK_URL:-changeme}" \
  bot_token="${SLACK_BOT_TOKEN:-changeme}"

vault kv put secret/aiops/email \
  smtp_server="${EMAIL_SMTP_SERVER:-smtp.gmail.com}" \
  smtp_port="${EMAIL_SMTP_PORT:-587}" \
  username="${EMAIL_USERNAME:-changeme}" \
  password="${EMAIL_PASSWORD:-changeme}"

# AI API keys
vault kv put secret/aiops/ai \
  gemini_api_key="${GEMINI_API_KEY:-changeme}" \
  huggingface_token="${HUGGINGFACE_TOKEN:-changeme}"

# Database credentials
vault kv put secret/aiops/database \
  postgres_url="${POSTGRES_URL:-changeme}" \
  redis_url="${REDIS_URL:-redis://localhost:6379}"

# Application security
vault kv put secret/aiops/app \
  jwt_secret="${JWT_SECRET:-changeme-use-a-strong-random-value}" \
  encryption_key="${ENCRYPTION_KEY:-changeme-32-bytes}"

echo ""
echo "==> Writing AIOps application policy..."
vault policy write aiops-policy /vault/init/../policies/aiops-policy.hcl

echo ""
echo "==> Creating AppRole for aiops-bot service..."
vault auth enable approle 2>/dev/null || echo "  (approle already enabled)"
vault write auth/approle/role/aiops-bot \
  token_policies="aiops-policy" \
  token_ttl=1h \
  token_max_ttl=4h

ROLE_ID=$(vault read -field=role_id auth/approle/role/aiops-bot/role-id)
SECRET_ID=$(vault write -field=secret_id -f auth/approle/role/aiops-bot/secret-id)

echo ""
echo "==> Done! Save these credentials for the aiops-bot service:"
echo "    VAULT_ROLE_ID=${ROLE_ID}"
echo "    VAULT_SECRET_ID=${SECRET_ID}"
echo "    VAULT_ADDR=http://vault:8200"
echo ""
echo "==> Vault UI: http://localhost:8200 (token: aiops-root-token)"
