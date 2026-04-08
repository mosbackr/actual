from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
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

        # ECS Cluster
        cluster = ecs.Cluster(self, "AcutalCluster", vpc=vpc)

        # Backend Service
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
                },
                secrets={
                    "ACUTAL_DATABASE_URL": ecs.Secret.from_secrets_manager(db_secret),
                    "ACUTAL_JWT_SECRET": ecs.Secret.from_secrets_manager(jwt_secret),
                },
            ),
        )

        # Allow backend to connect to RDS
        db.connections.allow_default_port_from(backend_service.service)

        # Frontend Service
        frontend_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "FrontendService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../frontend"),
                container_port=3000,
                environment={
                    "NEXT_PUBLIC_API_URL": f"http://{backend_service.load_balancer.load_balancer_dns_name}",
                    "NEXTAUTH_SECRET": "REPLACE_WITH_REAL_SECRET",
                },
            ),
        )

        # Admin Service
        admin_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "AdminService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../admin"),
                container_port=3001,
                environment={
                    "NEXT_PUBLIC_API_URL": f"http://{backend_service.load_balancer.load_balancer_dns_name}",
                    "NEXTAUTH_SECRET": "REPLACE_WITH_REAL_SECRET",
                },
            ),
        )
