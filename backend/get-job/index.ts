import { DynamoDBClient, GetItemCommand } from '@aws-sdk/client-dynamodb';

const ddb = new DynamoDBClient({});

const JOBS_TABLE = process.env.JOBS_TABLE!;

const CORS_HEADERS = { 'Access-Control-Allow-Origin': '*' };

export const handler = async (event: {
  pathParameters?: { jobId?: string };
}): Promise<{
  statusCode: number;
  body: string;
  headers: Record<string, string>;
}> => {
  const jobId = event.pathParameters?.jobId;
  if (!jobId) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: 'jobId required' }),
      headers: CORS_HEADERS,
    };
  }

  const res = await ddb.send(
    new GetItemCommand({
      TableName: JOBS_TABLE,
      Key: { jobId: { S: jobId } },
    })
  );

  if (!res.Item) {
    return {
      statusCode: 404,
      body: JSON.stringify({ error: 'not found' }),
      headers: CORS_HEADERS,
    };
  }

  const item = res.Item;
  const out = {
    jobId: item.jobId?.S,
    status: item.status?.S,
    step: item.step?.S ?? undefined,
    progress: item.progress ? Number(item.progress.N) : 0,
    resultUrl: item.resultUrl?.S ?? null,
    error: item.error?.S ?? null,
    updatedAt: item.updatedAt ? Number(item.updatedAt.N) : null,
  };

  return {
    statusCode: 200,
    body: JSON.stringify(out),
    headers: CORS_HEADERS,
  };
};
