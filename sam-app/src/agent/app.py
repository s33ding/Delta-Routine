import json
import os
import uuid
import boto3
from datetime import datetime, timedelta
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])
conv_table = dynamodb.Table(os.environ['CONVERSATION_TABLE'])
settings_table = dynamodb.Table(os.environ['SETTINGS_TABLE'])
todo_table = dynamodb.Table(os.environ['TODO_TABLE'])
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

MAX_HISTORY = 10
HISTORY_TTL_HOURS = 24
DEFAULT_COLORS = {'health': '#9e6878', 'work': '#5e7e94', 'personal': '#94705e', 'learning': '#6a946a', 'other': '#7e7494'}

SYSTEM_PROMPT = """You are Delta-Routine, a precision time-budgeting assistant. You manage the user's routine schedule, custom schedules, todos, and display settings.

There are TWO types of schedules:
- "routine": recurring weekly schedule (e.g., "I swim every Monday"). Use day names (Monday, Tuesday...).
- "custom": one-off events for specific dates (e.g., "dentist appointment on April 5th"). Use YYYY-MM-DD format.

You MUST respond with valid JSON in this exact format:
{
  "action": "query" | "add" | "update" | "delete" | "set_colors" | "add_todo" | "toggle_todo" | "delete_todo",
  "message": "your response to the user",
  "schedule_type": "routine" | "custom",
  "schedules": [
    {
      "schedule_id": "required for update/delete — use exact ID from current data",
      "title": "task title",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "day": "day name for routine OR YYYY-MM-DD for custom",
      "category": "work|personal|health|learning|other",
      "priority": "high|medium|low"
    }
  ],
  "todos": [
    {
      "todo_id": "required for toggle/delete",
      "title": "todo item text",
      "done": false,
      "priority": "high|medium|low"
    }
  ],
  "colors": {
    "category_name": "#hexcolor"
  }
}

SCHEDULE RULES:
- Default schedule_type is "routine" unless the user mentions a specific date.
- If user says "tomorrow", "next Friday", "April 5th" etc., use "custom" with YYYY-MM-DD.
- If user says "every Monday", "on Mondays", "I swim on Fridays", use "routine" with day names.

TODO RULES:
- "add_todo": add items to the todo list. Include "todos" array with title and priority.
- "toggle_todo": mark a todo as done/undone. Include todo_id and set done to true/false.
- "delete_todo": remove a todo. Include todo_id.

CRITICAL RULES FOR UNDERSTANDING USER INTENT:
1. When the user says "remove X" or "delete X" after discussing a specific day, they mean ONLY that day, not all instances.
2. When the user says "actually I have X on [day]", they want to REPLACE what's there.
3. When the user corrects themselves ("sorry", "actually", "wait", "no"), apply the correction to the most recent context.
4. "only in [day]" means the user is clarifying scope.
5. If the user gives a start time without an end time, estimate a reasonable duration.
6. Detect conflicts: if adding an event overlaps with an existing one, warn the user.
7. When deleting, always use the exact schedule_id/todo_id from the current data.

COLOR RULES:
8. Colors can be assigned by CATEGORY or by individual ACTIVITY title.
9. When the user asks to change colors, ASK if they want to color by category or by specific activity name.
10. For activity-level colors, use the exact activity title in lowercase as the key.
11. When suggesting colors, ONLY use muted, desaturated mid-tones that are dark enough for white text. Pick from: #5e7e94 (slate blue), #94705e (warm brown), #6a946a (sage green), #9e6878 (dusty rose), #7e7494 (lavender gray), #5e8e86 (muted teal), #948e5e (olive), #6e7e94 (steel), #946e6e (clay), #6e946e (fern).
12. NEVER use bright saturated colors. All colors must look soft and muted against a neutral gray UI.

SLEEP/WAKE RULES:
13. If the user hasn't set wake/sleep times and asks for insights, ASK them.
14. When the user provides wake/sleep times, use "set_colors" action but include "wake_time" and "sleep_time" in the colors object.

For "query", return empty schedules/todos arrays and put insights in "message".
For "set_colors", include only categories being changed.
Be concise and actionable."""


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def cors_headers():
    return {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type,Authorization', 'Access-Control-Allow-Methods': 'POST,OPTIONS'}


def get_schedules(user_id):
    resp = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id))
    return resp.get('Items', [])


def get_todos(user_id):
    resp = todo_table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id))
    return resp.get('Items', [])


def get_colors(user_id):
    resp = settings_table.get_item(Key={'user_id': user_id})
    return resp.get('Item', {}).get('colors', DEFAULT_COLORS)


def save_colors(user_id, colors):
    current = get_colors(user_id)
    merged = {**current, **colors}
    # Separate wake/sleep from colors
    item = {'user_id': user_id, 'colors': {k: v for k, v in merged.items() if k not in ('wake_time', 'sleep_time')}}
    if 'wake_time' in merged:
        item['wake_time'] = merged['wake_time']
    if 'sleep_time' in merged:
        item['sleep_time'] = merged['sleep_time']
    settings_table.put_item(Item=item)
    return merged


def get_history(user_id):
    resp = conv_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id),
        ScanIndexForward=False, Limit=MAX_HISTORY)
    items = resp.get('Items', [])
    items.reverse()
    messages = []
    for item in items:
        messages.append({"role": "user", "content": item['user_msg']})
        messages.append({"role": "assistant", "content": item['assistant_msg']})
    return messages


def save_history(user_id, user_msg, assistant_msg):
    conv_table.put_item(Item={
        'user_id': user_id,
        'timestamp': datetime.utcnow().isoformat(),
        'user_msg': user_msg,
        'assistant_msg': assistant_msg,
        'ttl': int((datetime.utcnow() + timedelta(hours=HISTORY_TTL_HOURS)).timestamp())
    })


def apply_changes(user_id, parsed):
    action = parsed.get('action', 'query')
    schedules = parsed.get('schedules', [])
    todos = parsed.get('todos', [])
    colors = None

    if action == 'set_colors':
        colors = save_colors(user_id, parsed.get('colors', {}))
    elif action == 'add':
        for s in schedules:
            s['user_id'] = user_id
            s['schedule_id'] = s.get('schedule_id', str(uuid.uuid4()))
            s['schedule_type'] = parsed.get('schedule_type', 'routine')
            s['created_at'] = datetime.utcnow().isoformat()
            table.put_item(Item=s)
    elif action == 'update':
        for s in schedules:
            sid = s.pop('schedule_id', None)
            if not sid:
                continue
            expr_parts, values = [], {}
            for i, (k, v) in enumerate(s.items()):
                expr_parts.append(f"#{k} = :v{i}")
                values[f":v{i}"] = v
            names = {f"#{k}": k for k in s}
            table.update_item(
                Key={'user_id': user_id, 'schedule_id': sid},
                UpdateExpression="SET " + ", ".join(expr_parts),
                ExpressionAttributeNames=names, ExpressionAttributeValues=values)
    elif action == 'delete':
        for s in schedules:
            if s.get('schedule_id'):
                table.delete_item(Key={'user_id': user_id, 'schedule_id': s['schedule_id']})
    elif action == 'add_todo':
        for t in todos:
            t['user_id'] = user_id
            t['todo_id'] = t.get('todo_id', str(uuid.uuid4()))
            t['done'] = t.get('done', False)
            t['created_at'] = datetime.utcnow().isoformat()
            todo_table.put_item(Item=t)
    elif action == 'toggle_todo':
        for t in todos:
            if t.get('todo_id'):
                todo_table.update_item(
                    Key={'user_id': user_id, 'todo_id': t['todo_id']},
                    UpdateExpression="SET done = :d",
                    ExpressionAttributeValues={':d': t.get('done', True)})
    elif action == 'delete_todo':
        for t in todos:
            if t.get('todo_id'):
                todo_table.delete_item(Key={'user_id': user_id, 'todo_id': t['todo_id']})

    return get_schedules(user_id), get_todos(user_id), colors or get_colors(user_id)


def invoke_bedrock(prompt, current_schedules, current_todos, current_colors, history):
    now = datetime.utcnow()
    day_names = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    today = day_names[now.weekday()]
    user_msg = f"Today is {today}, {now.strftime('%Y-%m-%d %H:%M')} UTC.\nCurrent schedules:\n{json.dumps(current_schedules, cls=DecimalEncoder)}\nCurrent todos:\n{json.dumps(current_todos, cls=DecimalEncoder)}\nCurrent colors:\n{json.dumps(current_colors)}\n\nUser request: {prompt}"
    llama_prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{SYSTEM_PROMPT}<|eot_id|>"
    for msg in history:
        llama_prompt += f"<|start_header_id|>{msg['role']}<|end_header_id|>\n{msg['content']}<|eot_id|>"
    llama_prompt += f"<|start_header_id|>user<|end_header_id|>\n{user_msg}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
    body = json.dumps({"prompt": llama_prompt, "max_gen_len": 1024, "temperature": 0.3})
    resp = bedrock.invoke_model(modelId="us.meta.llama3-3-70b-instruct-v1:0", body=body, contentType="application/json")
    result = json.loads(resp['body'].read())
    raw = result['generation'].strip()
    start = raw.find('{')
    end = raw.rfind('}') + 1
    return json.loads(raw[start:end]), raw[start:end]


def handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers(), 'body': ''}

    try:
        claims = event['requestContext']['authorizer']['claims']
        user_id = claims['sub']
    except (KeyError, TypeError):
        return {'statusCode': 401, 'headers': cors_headers(), 'body': json.dumps({'error': 'Unauthorized'})}

    try:
        body = json.loads(event.get('body', '{}'))
        prompt = body.get('prompt', '')
        if not prompt:
            return {'statusCode': 400, 'headers': cors_headers(), 'body': json.dumps({'error': 'prompt required'})}
        current = get_schedules(user_id)
        current_todos = get_todos(user_id)
        colors = get_colors(user_id)
        history = get_history(user_id)
        parsed, raw = invoke_bedrock(prompt, current, current_todos, colors, history)
        updated, updated_todos, updated_colors = apply_changes(user_id, parsed)
        save_history(user_id, prompt, raw)
        return {'statusCode': 200, 'headers': cors_headers(), 'body': json.dumps({
            'message': parsed.get('message', ''), 'action': parsed.get('action', 'query'),
            'schedules': updated, 'todos': updated_todos, 'colors': updated_colors
        }, cls=DecimalEncoder)}
    except Exception as e:
        import traceback; traceback.print_exc()
        return {'statusCode': 500, 'headers': cors_headers(), 'body': json.dumps({'message': str(e), 'error': str(e)})}
