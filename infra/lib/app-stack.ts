import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr_assets from 'aws-cdk-lib/aws-ecr-assets';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { NodejsFunction } from 'aws-cdk-lib/aws-lambda-nodejs';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';

export class BuildAppsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const appRoot = path.join(__dirname, '..', '..');
    const backendPath = path.join(appRoot, 'backend');
    const workerPath = path.join(appRoot, 'worker');

    // DynamoDB Jobs table
    const jobsTable = new dynamodb.Table(this, 'JobsTable', {
      tableName: 'Jobs',
      partitionKey: { name: 'jobId', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      timeToLiveAttribute: 'expiresAt',
    });

    // SQS queue + DLQ
    const dlq = new sqs.Queue(this, 'JobsDLQ', {
      queueName: 'BuildAppsJobsDLQ',
      retentionPeriod: cdk.Duration.days(14),
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const jobQueue = new sqs.Queue(this, 'JobsQueue', {
      queueName: 'BuildAppsJobsQueue',
      visibilityTimeout: cdk.Duration.minutes(15),
      deadLetterQueue: {
        queue: dlq,
        maxReceiveCount: 3,
      },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // S3 bucket for generated apps (public read on apps/* so frontend can iframe them)
    const appsBucket = new s3.Bucket(this, 'AppsBucket', {
      bucketName: undefined, // let CDK generate
      blockPublicAccess: new s3.BlockPublicAccess({
        blockPublicAcls: true,
        blockPublicPolicy: false,
        ignorePublicAcls: true,
        restrictPublicBuckets: false,
      }),
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    appsBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        actions: ['s3:GetObject'],
        resources: [appsBucket.arnForObjects('apps/*')],
        principals: [new iam.StarPrincipal()],
      })
    );

    // Base URL for generated apps (S3 virtual-hosted-style; worker uses this for resultUrl)
    const publicBaseUrl = `https://${appsBucket.bucketName}.s3.${this.region}.amazonaws.com`;

    // CreateJob Lambda (projectRoot so Docker bundling mounts app root)
    const createJobFn = new NodejsFunction(this, 'CreateJob', {
      entry: path.join(backendPath, 'create-job', 'index.ts'),
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_20_X,
      projectRoot: appRoot,
      environment: {
        JOBS_TABLE: jobsTable.tableName,
        QUEUE_URL: jobQueue.queueUrl,
      },
      timeout: cdk.Duration.seconds(30),
    });
    jobsTable.grantReadWriteData(createJobFn);
    jobQueue.grantSendMessages(createJobFn);

    // GetJob Lambda (projectRoot so Docker bundling mounts app root)
    const getJobFn = new NodejsFunction(this, 'GetJob', {
      entry: path.join(backendPath, 'get-job', 'index.ts'),
      handler: 'handler',
      runtime: lambda.Runtime.NODEJS_20_X,
      projectRoot: appRoot,
      environment: {
        JOBS_TABLE: jobsTable.tableName,
      },
      timeout: cdk.Duration.seconds(10),
    });
    jobsTable.grantReadData(getJobFn);

    // API Gateway
    const api = new apigateway.RestApi(this, 'BuildAppsApi', {
      restApiName: 'BuildAppsApi',
      deployOptions: { stageName: 'prod' },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'Authorization'],
      },
    });

    const jobsResource = api.root.addResource('jobs');
    jobsResource.addMethod(
      'POST',
      new apigateway.LambdaIntegration(createJobFn)
    );
    const jobIdResource = jobsResource.addResource('{jobId}');
    jobIdResource.addMethod(
      'GET',
      new apigateway.LambdaIntegration(getJobFn)
    );

    // ECS Fargate worker
    const vpc = new ec2.Vpc(this, 'WorkerVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    const cluster = new ecs.Cluster(this, 'WorkerCluster', {
      vpc,
      clusterName: 'BuildAppsWorkerCluster',
    });

    const workerImage = new ecr_assets.DockerImageAsset(this, 'WorkerImage', {
      directory: workerPath,
      file: 'Dockerfile',
    });

    const taskRole = new iam.Role(this, 'WorkerTaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
    });
    jobQueue.grantConsumeMessages(taskRole);
    jobsTable.grant(taskRole, 'dynamodb:UpdateItem', 'dynamodb:GetItem');
    appsBucket.grantPut(taskRole);

    const executionRole = new iam.Role(this, 'WorkerExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          'service-role/AmazonECSTaskExecutionRolePolicy'
        ),
      ],
    });

    const taskDefinition = new ecs.FargateTaskDefinition(this, 'WorkerTask', {
      memoryLimitMiB: 1024,
      cpu: 512,
      taskRole,
      executionRole,
    });

    const logGroup = new logs.LogGroup(this, 'WorkerLogGroup', {
      logGroupName: '/ecs/build-apps-worker',
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const geminiApiKey = this.node.tryGetContext('GEMINI_API_KEY') as string | undefined;
    const containerEnv: Record<string, string> = {
      QUEUE_URL: jobQueue.queueUrl,
      JOBS_TABLE: jobsTable.tableName,
      APPS_BUCKET: appsBucket.bucketName,
      PUBLIC_BASE_URL: publicBaseUrl,
    };
    if (geminiApiKey) {
      containerEnv.GEMINI_API_KEY = geminiApiKey;
    }

    taskDefinition.addContainer('Worker', {
      image: ecs.ContainerImage.fromDockerImageAsset(workerImage),
      logging: ecs.LogDrivers.awsLogs({
        streamPrefix: 'worker',
        logGroup,
      }),
      environment: containerEnv,
    });

    const workerService = new ecs.FargateService(this, 'WorkerService', {
      cluster,
      taskDefinition,
      desiredCount: 1,
      serviceName: 'BuildAppsWorker',
    });

    // Outputs
    new cdk.CfnOutput(this, 'ApiUrl', {
      value: api.url,
      description: 'API Gateway base URL (no trailing slash)',
      exportName: 'BuildAppsApiUrl',
    });
    new cdk.CfnOutput(this, 'PublicBaseUrl', {
      value: publicBaseUrl,
      description: 'S3 base URL for generated apps (PUBLIC_BASE_URL for worker)',
      exportName: 'BuildAppsPublicBaseUrl',
    });
    new cdk.CfnOutput(this, 'WorkerServiceName', {
      value: workerService.serviceName,
      description: 'ECS service name',
    });
  }
}
