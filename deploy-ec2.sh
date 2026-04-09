#!/bin/bash
set -e

REGION="us-east-1"
INSTANCE_TYPE="t3.small"
KEY_NAME="acutal-deploy"
SG_NAME="acutal-sg"

echo "=== Acutal EC2 Deploy ==="

# Step 1: Create key pair if needed
if ! aws ec2 describe-key-pairs --key-names $KEY_NAME --region $REGION 2>/dev/null; then
  echo "Creating SSH key pair..."
  aws ec2 create-key-pair --key-name $KEY_NAME --region $REGION \
    --query 'KeyMaterial' --output text > ~/.ssh/${KEY_NAME}.pem
  chmod 600 ~/.ssh/${KEY_NAME}.pem
  echo "Key saved to ~/.ssh/${KEY_NAME}.pem"
fi

# Step 2: Create security group if needed
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region $REGION)
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
  --query "SecurityGroups[0].GroupId" --output text --region $REGION 2>/dev/null)

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  echo "Creating security group..."
  SG_ID=$(aws ec2 create-security-group --group-name $SG_NAME --description "Acutal app" \
    --vpc-id $VPC_ID --region $REGION --query 'GroupId' --output text)
  # SSH, Backend, Frontend, Admin
  aws ec2 authorize-security-group-ingress --group-id $SG_ID --region $REGION \
    --ip-permissions \
    'IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=0.0.0.0/0}]' \
    'IpProtocol=tcp,FromPort=8000,ToPort=8000,IpRanges=[{CidrIp=0.0.0.0/0}]' \
    'IpProtocol=tcp,FromPort=3000,ToPort=3000,IpRanges=[{CidrIp=0.0.0.0/0}]' \
    'IpProtocol=tcp,FromPort=3001,ToPort=3001,IpRanges=[{CidrIp=0.0.0.0/0}]'
fi
echo "Security group: $SG_ID"

# Step 3: Find or launch EC2 instance
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=acutal" "Name=instance-state-name,Values=running" \
  --query "Reservations[0].Instances[0].InstanceId" --output text --region $REGION 2>/dev/null)

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
  echo "Launching EC2 instance..."
  # Amazon Linux 2023 AMI
  AMI_ID=$(aws ec2 describe-images --owners amazon \
    --filters "Name=name,Values=al2023-ami-2023*-x86_64" "Name=state,Values=available" \
    --query "sort_by(Images,&CreationDate)[-1].ImageId" --output text --region $REGION)

  INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --instance-type $INSTANCE_TYPE \
    --key-name $KEY_NAME \
    --security-group-ids $SG_ID \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=acutal}]" \
    --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30}}]' \
    --user-data '#!/bin/bash
dnf install -y git
# Install Docker CE (includes buildx + compose plugin)
dnf install -y docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/v2.36.2/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
curl -SL "https://github.com/docker/buildx/releases/download/v0.22.0/buildx-v0.22.0.linux-amd64" -o /usr/local/lib/docker/cli-plugins/docker-buildx
chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
systemctl enable docker && systemctl start docker
usermod -aG docker ec2-user
' \
    --region $REGION \
    --query 'Instances[0].InstanceId' --output text)

  echo "Waiting for instance to be running..."
  aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION
  echo "Waiting for instance status checks..."
  aws ec2 wait instance-status-ok --instance-ids $INSTANCE_ID --region $REGION
fi

HOST_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text --region $REGION)
echo "Instance: $INSTANCE_ID ($HOST_IP)"

# Step 4: Generate secrets
DB_PASSWORD=$(openssl rand -hex 16)
JWT_SECRET=$(openssl rand -hex 32)

# Step 5: Sync code and deploy
echo "Syncing code to EC2..."
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/${KEY_NAME}.pem"

# Wait for SSH to be available
for i in $(seq 1 30); do
  ssh $SSH_OPTS ec2-user@$HOST_IP "echo ready" 2>/dev/null && break
  echo "Waiting for SSH... ($i)"
  sleep 5
done

# Sync project files (exclude unnecessary dirs)
rsync -azP --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.next' \
  --exclude '__pycache__' \
  --exclude 'infra' \
  --exclude '.worktrees' \
  --exclude 'cdk-outputs.json' \
  --exclude 'cdk.out' \
  --exclude '.venv' \
  -e "ssh $SSH_OPTS" \
  ./ ec2-user@$HOST_IP:~/acutal/

# Create .env on the server
ssh $SSH_OPTS ec2-user@$HOST_IP "cat > ~/acutal/.env << 'ENVEOF'
DB_PASSWORD=$DB_PASSWORD
JWT_SECRET=$JWT_SECRET
HOST_IP=$HOST_IP
ENVEOF"

# Build and start
echo "Building and starting services..."
ssh $SSH_OPTS ec2-user@$HOST_IP "cd ~/acutal && docker compose -f docker-compose.prod.yml --env-file .env up -d --build"

# Step 6: Run migrations
echo "Running migrations..."
ssh $SSH_OPTS ec2-user@$HOST_IP "cd ~/acutal && docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head"

# Step 7: Seed data
echo "Seeding templates..."
ssh $SSH_OPTS ec2-user@$HOST_IP "cd ~/acutal && docker compose -f docker-compose.prod.yml exec -T backend python -m app.seed_templates" 2>/dev/null || true

echo ""
echo "=== Deployment Complete ==="
echo "Backend:  http://$HOST_IP:8000"
echo "Frontend: http://$HOST_IP:3000"
echo "Admin:    http://$HOST_IP:3001"
echo "SSH:      ssh $SSH_OPTS ec2-user@$HOST_IP"
