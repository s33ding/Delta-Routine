# Delta-Routine

Precision time-budgeting engine powered by AI. Manage your weekly routine, custom events, and todos through a conversational assistant.

🔗 **[Launch App](https://s33ding-delta-routine.s3.amazonaws.com/index.html)**

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  S3 Static Website (frontend/)                      │
│  index.html · css/style.css · js/app.js             │
└──────────────┬──────────────────────────────────────┘
               │ HTTPS
┌──────────────▼──────────────────────────────────────┐
│  API Gateway (Cognito Authorizer)                   │
├─────────────────────────────────────────────────────┤
│  POST /agent      → AgentFunction (Bedrock + CRUD)  │
│  GET  /schedules  → SchedulesFunction (read-only)   │
│  GET  /todos      → TodosFunction (read-only)       │
│  GET  /settings   → SettingsFunction (colors/prefs) │
│  PUT  /settings   → SettingsFunction                │
│  GET  /insights   → InsightsFunction (analytics)    │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  DynamoDB Tables                                    │
│  · delta-routine-schedules    (routine + custom)    │
│  · delta-routine-todos                              │
│  · delta-routine-conversations (24h TTL)            │
│  · delta-routine-settings     (colors, wake/sleep)  │
└─────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  Amazon Bedrock (Llama 3.3 70B)                     │
│  Conversational agent with session history          │
└─────────────────────────────────────────────────────┘
```

## Auth

- Cognito User Pool with Google (Gmail) sign-in
- Cognito Identity Pool for AWS credentials
- Per-user data isolation via `user_id` (Cognito `sub`)

## Features

- **Routine schedule** — recurring weekly events (Mon–Sun grid)
- **Custom schedule** — one-off events by date
- **Todo list** — prioritized tasks managed via chat
- **Insights** — time breakdown by category/task with day/week filter and "from now" mode
- **Dynamic colors** — per-user, per-category or per-activity colors, agent-managed
- **Session memory** — last 10 conversation exchanges stored with 24h TTL

## Stack

- AWS SAM (Lambda + API Gateway + DynamoDB)
- Amazon Bedrock (Llama 3.3 70B Instruct)
- Cognito (User Pool + Identity Pool + Google IdP)
- S3 static website hosting

## Deploy

```bash
cd sam-app
sam build && sam deploy --guided

# Upload frontend
aws s3 sync frontend/ s3://s33ding-delta-routine/
```
