#!/bin/bash
set -e

echo "🚀 Deploying AuDRA-Rad to Amazon EKS"

# Configuration
CLUSTER_NAME="audra-rad-cluster"
REGION="us-east-1"
NAMESPACE="audra-rad"
ECR_REPO="YOUR_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/audra-rad"
IMAGE_TAG="latest"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Step 1: Building Docker image${NC}"
docker build -t audra-rad:$IMAGE_TAG -f deployment/docker/Dockerfile .

echo -e "${YELLOW}Step 2: Pushing to ECR${NC}"
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_REPO
docker tag audra-rad:$IMAGE_TAG $ECR_REPO:$IMAGE_TAG
docker push $ECR_REPO:$IMAGE_TAG

echo -e "${YELLOW}Step 3: Updating kubeconfig${NC}"
aws eks update-kubeconfig --name $CLUSTER_NAME --region $REGION

echo -e "${YELLOW}Step 4: Creating namespace${NC}"
kubectl apply -f deployment/kubernetes/eks/namespace.yaml

echo -e "${YELLOW}Step 5: Applying secrets and config${NC}"
kubectl apply -f deployment/kubernetes/eks/secrets.yaml

echo -e "${YELLOW}Step 6: Deploying NVIDIA NIMs${NC}"
kubectl apply -f deployment/kubernetes/eks/nim-llm-deployment.yaml
kubectl apply -f deployment/kubernetes/eks/nim-embedding-deployment.yaml

echo -e "${YELLOW}Waiting for NIMs to be ready (this may take 5-10 minutes)...${NC}"
kubectl wait --for=condition=ready pod -l app=nim-llm -n $NAMESPACE --timeout=600s
kubectl wait --for=condition=ready pod -l app=nim-embedding -n $NAMESPACE --timeout=600s

echo -e "${YELLOW}Step 7: Deploying AuDRA-Rad API${NC}"
kubectl apply -f deployment/kubernetes/eks/audra-api-deployment.yaml

echo -e "${YELLOW}Waiting for API to be ready...${NC}"
kubectl wait --for=condition=ready pod -l app=audra-api -n $NAMESPACE --timeout=300s

echo -e "${YELLOW}Step 8: Applying ingress${NC}"
kubectl apply -f deployment/kubernetes/eks/ingress.yaml

echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "Services:"
kubectl get svc -n $NAMESPACE
echo ""
echo "Pods:"
kubectl get pods -n $NAMESPACE
echo ""
echo "Ingress:"
kubectl get ingress -n $NAMESPACE

echo ""
echo "🎉 AuDRA-Rad is deployed!"
echo "Access the API at: http://$(kubectl get svc audra-api-service -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
