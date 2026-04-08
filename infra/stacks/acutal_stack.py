from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_rds as rds,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class AcutalStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # VPC
        vpc = ec2.Vpc(self, "AcutalVpc", max_azs=2)

        # Secrets
        db_secret = secretsmanager.Secret(self, "DbSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"acutal"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        jwt_secret = secretsmanager.Secret(self, "JwtSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_punctuation=True,
                password_length=64,
            ),
        )

        # RDS PostgreSQL
        db = rds.DatabaseInstance(self, "AcutalDb",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MICRO,
            ),
            vpc=vpc,
            credentials=rds.Credentials.from_secret(db_secret),
            database_name="acutal",
            removal_policy=RemovalPolicy.SNAPSHOT,
            deletion_protection=False,
        )

        # S3 for static assets
        assets_bucket = s3.Bucket(self, "AssetsBucket",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # ECR Repositories (for future image rebuilds)
        backend_repo = ecr.Repository(self, "BackendRepo",
            repository_name="acutal-backend",
            removal_policy=RemovalPolicy.DESTROY,
        )
        frontend_repo = ecr.Repository(self, "FrontendRepo",
            repository_name="acutal-frontend",
            removal_policy=RemovalPolicy.DESTROY,
        )
        admin_repo = ecr.Repository(self, "AdminRepo",
            repository_name="acutal-admin",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ECS Cluster
        cluster = ecs.Cluster(self, "AcutalCluster", vpc=vpc)

        # Backend Service (built from local Dockerfile via CDK)
        backend_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "BackendService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../backend"),
                container_port=8000,
                environment={
                    "ACUTAL_CORS_ORIGINS": '["*"]',
                    "DB_HOST": db.db_instance_endpoint_address,
                    "DB_PORT": db.db_instance_endpoint_port,
                    "DB_USER": "acutal",
                    "DB_NAME": "acutal",
                },
                secrets={
                    "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
                    "ACUTAL_JWT_SECRET": ecs.Secret.from_secrets_manager(jwt_secret),
                },
            ),
        )

        # Allow backend to connect to RDS
        db.connections.allow_default_port_from(backend_service.service)

        # Frontend Service (initial build with placeholder API URL)
        frontend_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "FrontendService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../frontend",
                    build_args={"NEXT_PUBLIC_API_URL": "http://placeholder"},
                ),
                container_port=3000,
                secrets={
                    "NEXTAUTH_SECRET": ecs.Secret.from_secrets_manager(jwt_secret),
                },
            ),
        )

        # Admin Service (initial build with placeholder API URL)
        admin_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "AdminService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../admin",
                    build_args={"NEXT_PUBLIC_API_URL": "http://placeholder"},
                ),
                container_port=3001,
                secrets={
                    "NEXTAUTH_SECRET": ecs.Secret.from_secrets_manager(jwt_secret),
                },
            ),
        )

        # Outputs
        CfnOutput(self, "BackendUrl",
            value=f"http://{backend_service.load_balancer.load_balancer_dns_name}")
        CfnOutput(self, "FrontendUrl",
            value=f"http://{frontend_service.load_balancer.load_balancer_dns_name}")
        CfnOutput(self, "AdminUrl",
            value=f"http://{admin_service.load_balancer.load_balancer_dns_name}")
        CfnOutput(self, "DbEndpoint", value=db.db_instance_endpoint_address)
        CfnOutput(self, "DbSecretArn", value=db_secret.secret_arn)
        CfnOutput(self, "JwtSecretArn", value=jwt_secret.secret_arn)
