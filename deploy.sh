#!/bin/bash
set -e

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "=== Step 1: CDK Deploy (infrastructure + ECR repos) ==="
cd infra
pip install -r requirements.txt -q
npx cdk deploy --require-approval never --outputs-file ../cdk-outputs.json
cd ..

echo "=== Step 2: ECR Login ==="
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_BASE}

echo "=== Step 3: Build & Push Backend ==="
docker build -t acutal-backend ./backend
docker tag acutal-backend:latest ${ECR_BASE}/acutal-backend:latest
docker push ${ECR_BASE}/acutal-backend:latest

echo "=== Step 4: Get Backend ALB DNS ==="
BACKEND_URL=$(cat cdk-outputs.json | python3 -c "import sys,json; print(json.load(sys.stdin)['AcutalStack']['BackendUrl'])")
echo "Backend URL: ${BACKEND_URL}"

echo "=== Step 5: Build & Push Frontend ==="
docker build --build-arg NEXT_PUBLIC_API_URL=${BACKEND_URL} -t acutal-frontend ./frontend
docker tag acutal-frontend:latest ${ECR_BASE}/acutal-frontend:latest
docker push ${ECR_BASE}/acutal-frontend:latest

echo "=== Step 6: Build & Push Admin ==="
docker build --build-arg NEXT_PUBLIC_API_URL=${BACKEND_URL} -t acutal-admin ./admin
docker tag acutal-admin:latest ${ECR_BASE}/acutal-admin:latest
docker push ${ECR_BASE}/acutal-admin:latest

echo "=== Step 7: Force ECS Service Updates ==="
CLUSTER_ARN=$(aws ecs list-clusters --query "clusterArns[?contains(@,'Acutal')]" --output text)
for SERVICE in $(aws ecs list-services --cluster ${CLUSTER_ARN} --query 'serviceArns[]' --output text); do
  echo "Updating service: ${SERVICE}"
  aws ecs update-service --cluster ${CLUSTER_ARN} --service ${SERVICE} --force-new-deployment --no-cli-pager
done

echo "=== Step 8: Wait for Services to Stabilize ==="
for SERVICE in $(aws ecs list-services --cluster ${CLUSTER_ARN} --query 'serviceArns[]' --output text); do
  echo "Waiting for: $(basename ${SERVICE})..."
  aws ecs wait services-stable --cluster ${CLUSTER_ARN} --services ${SERVICE}
done

echo ""
echo "=== Deployment Complete ==="
cat cdk-outputs.json | python3 -c "
import sys, json
outputs = json.load(sys.stdin)['AcutalStack']
print(f\"Backend:  {outputs['BackendUrl']}\")
print(f\"Frontend: {outputs['FrontendUrl']}\")
print(f\"Admin:    {outputs['AdminUrl']}\")
print(f\"DB Host:  {outputs['DbEndpoint']}\")
"
