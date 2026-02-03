# Slack PR Rewards - Project Specification

## Overview

A standalone Slack bot that gamifies team engagement by tracking emoji reactions and rewarding users with points. When someone reacts to a message with designated emojis, the message author earns points.

## Repository

https://github.com/eschutho/slack-pr-rewards

## Tech Stack

- **Runtime**: Node.js 18+
- **Language**: TypeScript
- **Slack SDK**: @slack/bolt (Socket Mode)
- **Database**: SQLite (better-sqlite3)
- **Configuration**: dotenv

## Architecture

```
src/
├── index.ts              # App entry point, initializes Slack Bolt
├── types/index.ts        # TypeScript interfaces
├── db/
│   ├── schema.ts         # SQLite table definitions
│   ├── database.ts       # CRUD operations
│   └── migrate.ts        # Migration runner
├── handlers/
│   ├── reactions.ts      # reaction_added/removed events
│   └── commands.ts       # Slash command handlers
└── utils/
    └── config.ts         # Environment parsing, emoji mappings
```

## Features

### Core Functionality
- Listen for `reaction_added` and `reaction_removed` Slack events
- Map specific emojis to point values (configurable)
- Track user balances and transaction history
- Prevent self-reactions from earning points
- Rate limit daily point giving

### Slash Commands
| Command | Description |
|---------|-------------|
| `/rewards` | View your point balance |
| `/rewards leaderboard` | See top 10 earners |
| `/rewards history` | Recent rewards received |
| `/rewards help` | Show help and emoji values |
| `/leaderboard` | Shortcut to leaderboard |

### Default Emoji Point Values
| Emoji | Points |
|-------|--------|
| ⭐ `:star:` | 5 |
| 👍 `:thumbsup:` | 1 |
| ❤️ `:heart:` | 3 |
| 🎉 `:tada:` | 10 |
| 💯 `:100:` | 10 |
| 🚀 `:rocket:` | 5 |
| 🔥 `:fire:` | 3 |

## Database Schema

### users
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| slack_id | TEXT | Unique Slack user ID |
| username | TEXT | Slack username |
| display_name | TEXT | Display name |
| total_points_received | INTEGER | Lifetime points earned |
| total_points_given | INTEGER | Lifetime points given |
| created_at | DATETIME | First seen |
| updated_at | DATETIME | Last activity |

### transactions
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| giver_slack_id | TEXT | Who gave the reaction |
| receiver_slack_id | TEXT | Who received points |
| emoji | TEXT | Emoji used |
| points | INTEGER | Points awarded |
| message_ts | TEXT | Slack message timestamp |
| channel_id | TEXT | Channel where reaction occurred |
| created_at | DATETIME | When it happened |

## Configuration

Environment variables (`.env`):

```env
# Required - Slack credentials
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...

# Optional - Customization
PORT=3000
DATABASE_PATH=./data/rewards.db
EMOJI_POINTS=star:5,thumbsup:1,heart:3,tada:10
MAX_POINTS_PER_DAY=50
ALLOW_SELF_REACTIONS=false
```

## Slack App Setup Requirements

### Bot Token Scopes
- `channels:history`
- `groups:history`
- `im:history`
- `mpim:history`
- `reactions:read`
- `users:read`
- `commands`
- `chat:write`

### Event Subscriptions
- `reaction_added`
- `reaction_removed`

### Socket Mode
Required for real-time event handling without a public endpoint.

## Development Commands

```bash
npm install          # Install dependencies
npm run dev          # Development with hot reload
npm run build        # Compile TypeScript
npm start            # Run production build
npm run db:migrate   # Initialize database
```

## Future Enhancements

- [ ] Weekly/monthly leaderboard resets
- [ ] Slack Home tab with personal dashboard
- [ ] Admin commands to adjust points
- [ ] Channel-specific emoji configurations
- [ ] Integration with GitHub PR reviews
- [ ] Redemption system for rewards
- [ ] Scheduled leaderboard announcements
