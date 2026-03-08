import { DynamoDBClient, PutItemCommand } from '@aws-sdk/client-dynamodb';
import { SQSClient, SendMessageCommand } from '@aws-sdk/client-sqs';
import { ulid } from 'ulid';

const ddb = new DynamoDBClient({});
const sqs = new SQSClient({});

const JOBS_TABLE = process.env.JOBS_TABLE!;
const QUEUE_URL = process.env.QUEUE_URL!;

const CORS_HEADERS = { 'Access-Control-Allow-Origin': '*' };

export const handler = async (event: { body?: string }): Promise<{
  statusCode: number;
  body: string;
  headers: Record<string, string>;
}> => {
  const body = JSON.parse(event.body ?? '{}');
  const prompt = String(body.prompt ?? '').trim();
  if (!prompt) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: 'prompt required' }),
      headers: CORS_HEADERS,
    };
  }

  const jobId = ulid();
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = now + 60 * 60 * 24; // 24h TTL

  await ddb.send(
    new PutItemCommand({
      TableName: JOBS_TABLE,
      Item: {
        jobId: { S: jobId },
        prompt: { S: prompt },
        status: { S: 'queued' },
        step: { S: 'planning' },
        progress: { N: '0' },
        createdAt: { N: String(now) },
        updatedAt: { N: String(now) },
        expiresAt: { N: String(expiresAt) },
      },
    })
  );

  await sqs.send(
    new SendMessageCommand({
      QueueUrl: QUEUE_URL,
      MessageBody: JSON.stringify({ jobId, prompt }),
    })
  );

  return {
    statusCode: 200,
    body: JSON.stringify({ jobId }),
    headers: CORS_HEADERS,
  };
};
