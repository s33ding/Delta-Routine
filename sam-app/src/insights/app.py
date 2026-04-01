import json
import os
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])
settings_table = dynamodb.Table(os.environ['SETTINGS_TABLE'])

DAY_MAP = {'sunday': 0, 'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4, 'friday': 5, 'saturday': 6}
DAY_NAMES = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
DEFAULT_WAKE = {'wake_time': '07:00', 'sleep_time': '23:00'}


def cors_headers():
    return {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type,Authorization', 'Access-Control-Allow-Methods': 'GET,OPTIONS'}


def time_to_min(t):
    try:
        h, m = t.split(':')
        return int(h) * 60 + int(m)
    except:
        return 0


def handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers(), 'body': ''}

    try:
        claims = event['requestContext']['authorizer']['claims']
        user_id = claims['sub']
    except (KeyError, TypeError):
        return {'statusCode': 401, 'headers': cors_headers(), 'body': json.dumps({'error': 'Unauthorized'})}

    try:
        params = event.get('queryStringParameters') or {}
        view = params.get('view', 'week')  # 'day' or 'week'
        day_filter = params.get('day', None)  # day name for day view
        from_now = params.get('from_now', None)  # HH:MM - filter events after this time
        from_now_min = time_to_min(from_now) if from_now else None

        # Get user settings for wake/sleep
        settings_resp = settings_table.get_item(Key={'user_id': user_id})
        settings = settings_resp.get('Item', {})
        wake_time = settings.get('wake_time', DEFAULT_WAKE['wake_time'])
        sleep_time = settings.get('sleep_time', DEFAULT_WAKE['sleep_time'])
        wake_min = time_to_min(wake_time)
        sleep_min = time_to_min(sleep_time)
        awake_min = sleep_min - wake_min if sleep_min > wake_min else (1440 - wake_min + sleep_min)

        # Get schedules
        resp = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id))
        schedules = resp.get('Items', [])

        # Filter by day if needed
        if view == 'day' and day_filter:
            day_lower = day_filter.lower()
            filtered = []
            for s in schedules:
                d = (s.get('day') or '').lower()
                if d == day_lower:
                    filtered.append(s)
                elif d and d not in DAY_MAP:
                    from datetime import datetime as dt
                    try:
                        parsed = dt.strptime(d, '%Y-%m-%d')
                        if DAY_NAMES[parsed.weekday()] == day_lower:
                            filtered.append(s)
                    except:
                        pass
            schedules = filtered
            num_days = 1
        else:
            num_days = 7

        total_awake = awake_min * num_days
        sleep_total = (1440 - awake_min) * num_days

        # Calculate time per category and per task
        by_category = {}
        by_task = {}
        scheduled_min = 0

        for s in schedules:
            start = time_to_min(s.get('start_time', '00:00'))
            end = time_to_min(s.get('end_time', '00:00'))
            duration = end - start if end > start else 0
            if duration == 0:
                continue

            # If from_now, skip past events and clip current ones
            if from_now_min is not None:
                if end <= from_now_min:
                    continue
                if start < from_now_min:
                    start = from_now_min
                    duration = end - start

            cat = (s.get('category') or 'other').lower()
            title = s.get('title', 'Untitled')

            by_category[cat] = by_category.get(cat, 0) + duration
            by_task[title] = by_task.get(title, 0) + duration
            scheduled_min += duration

        # Adjust awake time for from_now
        if from_now_min is not None and view == 'day':
            remaining_awake = max(0, sleep_min - from_now_min) if sleep_min > from_now_min else 0
            total_awake = remaining_awake
            sleep_total = (1440 - awake_min)  # sleep stays the same

        free_min = max(0, total_awake - scheduled_min)

        # Build percentages
        cat_pct = {k: round(v / total_awake * 100, 1) for k, v in sorted(by_category.items(), key=lambda x: -x[1])}
        task_pct = {k: round(v / total_awake * 100, 1) for k, v in sorted(by_task.items(), key=lambda x: -x[1])}

        result = {
            'view': view,
            'day': day_filter if view == 'day' else 'all',
            'wake_time': wake_time,
            'sleep_time': sleep_time,
            'total_awake_hours': round(total_awake / 60, 1),
            'total_scheduled_hours': round(scheduled_min / 60, 1),
            'free_hours': round(free_min / 60, 1),
            'sleep_hours': round(sleep_total / 60, 1),
            'sleep_pct': round(sleep_total / (1440 * num_days) * 100, 1),
            'scheduled_pct': round(scheduled_min / total_awake * 100, 1) if total_awake else 0,
            'free_pct': round(free_min / total_awake * 100, 1) if total_awake else 0,
            'by_category': cat_pct,
            'by_task': task_pct,
            'has_sleep_data': 'wake_time' in settings
        }

        return {'statusCode': 200, 'headers': cors_headers(), 'body': json.dumps(result)}
    except Exception as e:
        return {'statusCode': 500, 'headers': cors_headers(), 'body': json.dumps({'error': str(e)})}
