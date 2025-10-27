#!/bin/bash
set -euo pipefail

NAMESPACE="audra-rad"
CLUSTER_NAME="audra-rad-cluster"
REGION="us-east-1"

echo "=== Cleaning up AuDRA-Rad deployment ==="
echo "This will delete all resources in namespace: $NAMESPACE"
read -rp "Are you sure? (y/N) " CONFIRMATION
if [[ ! "$CONFIRMATION" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
fi

echo "Deleting Kubernetes resources..."
kubectl delete namespace "$NAMESPACE" --wait=true

echo "Waiting for LoadBalancers to be deleted..."
sleep 30

echo "Checking for remaining resources..."
if ! kubectl get all -n "$NAMESPACE"; then
    echo "Namespace deleted successfully."
fi

echo
echo "Cleanup complete."
echo
echo "To delete the EKS cluster entirely:"
echo "  eksctl delete cluster --name $CLUSTER_NAME --region $REGION"
echo
echo "To delete ECR images:"
echo "  aws ecr batch-delete-image --repository-name audra-rad --region $REGION --image-ids imageTag=latest"
