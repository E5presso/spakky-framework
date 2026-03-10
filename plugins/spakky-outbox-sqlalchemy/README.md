# spakky-outbox-sqlalchemy

SQLAlchemy storage implementation for [spakky-outbox](../spakky-outbox/README.md) plugin.

## Installation

```bash
pip install spakky-outbox spakky-outbox-sqlalchemy
```

## Requirements

- PostgreSQL, MySQL, or any SQLAlchemy-supported database with `FOR UPDATE SKIP LOCKED` support
- `spakky-sqlalchemy` plugin configured with database connection

## Usage

### 1. Configure database connection

Set the environment variable for your database:

```bash
export SPAKKY_SQLALCHEMY__DATABASE_URL="postgresql+asyncpg://user:pass@localhost/mydb"
```

### 2. Load plugins

```python
from spakky import Spakky
from spakky.plugins.sqlalchemy import initialize as sqlalchemy_init
from spakky.plugins.outbox import initialize as outbox_init
from spakky.plugins.outbox_sqlalchemy import initialize as outbox_sqlalchemy_init

app = Spakky(...)

# Load in order: sqlalchemy → outbox → outbox-sqlalchemy
sqlalchemy_init(app)
outbox_init(app)
outbox_sqlalchemy_init(app)
```

### 3. Create the outbox table

Use Alembic or create the table manually:

```python
from spakky.plugins.outbox_sqlalchemy.persistency.table import OutboxBase

# In your Alembic env.py or startup script
async with engine.begin() as conn:
    await conn.run_sync(OutboxBase.metadata.create_all)
```

The table schema (`spakky_event_outbox`):

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `event_name` | TEXT | Event routing key |
| `payload` | BYTEA | JSON-serialized event |
| `created_at` | TIMESTAMP | Creation time |
| `published_at` | TIMESTAMP | Publication time (null if pending) |
| `retry_count` | INT | Retry attempts |
| `claimed_at` | TIMESTAMP | Claim time for atomic fetch |

## How It Works

1. **Save**: Messages are inserted via the transactional session (same TX as business data)
2. **Fetch**: Uses `UPDATE ... RETURNING` with `claimed_at` for atomic claim, preventing duplicate publishing
3. **Publish**: Relay calls external transport (Kafka/RabbitMQ) and marks as published

## License

MIT License
