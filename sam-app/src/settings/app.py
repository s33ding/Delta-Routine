import json
import os
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['SETTINGS_TABLE'])

DEFAULT_COLORS = {
    'health': '#e94560',
    'work': '#1b4965',
    'personal': '#f58a07',
    'learning': '#5b8c5a',
    'other': '#7b6d8d'
}


def cors_headers():
    return {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type,Authorization', 'Access-Control-Allow-Methods': 'GET,PUT,OPTIONS'}


def handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers(), 'body': ''}

    try:
        claims = event['requestContext']['authorizer']['claims']
        user_id = claims['sub']
    except (KeyError, TypeError):
        return {'statusCode': 401, 'headers': cors_headers(), 'body': json.dumps({'error': 'Unauthorized'})}

    try:
        if event.get('httpMethod') == 'GET':
            resp = table.get_item(Key={'user_id': user_id})
            colors = resp.get('Item', {}).get('colors', DEFAULT_COLORS)
            return {'statusCode': 200, 'headers': cors_headers(), 'body': json.dumps({'colors': colors})}

        if event.get('httpMethod') == 'PUT':
            body = json.loads(event.get('body', '{}'))
            colors = body.get('colors', {})
            # Merge with defaults
            merged = {**DEFAULT_COLORS, **colors}
            table.put_item(Item={'user_id': user_id, 'colors': merged})
            return {'statusCode': 200, 'headers': cors_headers(), 'body': json.dumps({'colors': merged})}
    except Exception as e:
        return {'statusCode': 500, 'headers': cors_headers(), 'body': json.dumps({'error': str(e)})}
