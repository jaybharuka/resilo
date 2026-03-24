# AIOps Bot application policy
# Grants read-only access to all secrets under the aiops/ path

path "secret/data/aiops/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/aiops/*" {
  capabilities = ["list"]
}
