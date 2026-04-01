import json
import os
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def cors_headers():
    return {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type,Authorization', 'Access-Control-Allow-Methods': 'GET,OPTIONS'}


def handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers(), 'body': ''}

    try:
        claims = event['requestContext']['authorizer']['claims']
        user_id = claims['sub']
    except (KeyError, TypeError):
        return {'statusCode': 401, 'headers': cors_headers(), 'body': json.dumps({'error': 'Unauthorized'})}

    try:
        resp = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id))
        schedules = resp.get('Items', [])
        return {'statusCode': 200, 'headers': cors_headers(), 'body': json.dumps({'schedules': schedules}, cls=DecimalEncoder)}
    except Exception as e:
        return {'statusCode': 500, 'headers': cors_headers(), 'body': json.dumps({'error': str(e)})}
