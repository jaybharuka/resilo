#!/bin/bash
set -e

ENVIRONMENT=${1:-staging}
NAMESPACE=$ENVIRONMENT

echo "Rolling back AIOps platform in $ENVIRONMENT environment..."

# Rollback all deployments
for deployment in $(kubectl get deployments --namespace=$NAMESPACE -o name); do
    echo "Rolling back $deployment..."
    kubectl rollout undo $deployment --namespace=$NAMESPACE
done

# Wait for rollback to complete
kubectl rollout status deployment --all --namespace=$NAMESPACE

echo "Rollback to $ENVIRONMENT completed successfully!"
