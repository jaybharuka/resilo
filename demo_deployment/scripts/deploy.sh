#!/bin/bash
set -e

ENVIRONMENT=${1:-staging}
NAMESPACE=$ENVIRONMENT

echo "Deploying AIOps platform to $ENVIRONMENT environment..."

# Create namespace if it doesn't exist
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Apply all manifests
kubectl apply -f k8s/$ENVIRONMENT/ --namespace=$NAMESPACE

# Wait for deployments to be ready
echo "Waiting for deployments to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment --all --namespace=$NAMESPACE

# Show deployment status
kubectl get pods --namespace=$NAMESPACE
kubectl get services --namespace=$NAMESPACE

echo "Deployment to $ENVIRONMENT completed successfully!"
