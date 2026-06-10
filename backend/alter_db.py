import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres.mxilwgovfgwfcbrdrbxd:binarydecoder%40123@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres'
)

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    conn.execute(text('ALTER TABLE users ADD COLUMN reset_token VARCHAR(255) NULL;'))
    conn.execute(text('ALTER TABLE users ADD COLUMN reset_expires_at TIMESTAMP WITH TIME ZONE NULL;'))
    print('Altered table users successfully')
