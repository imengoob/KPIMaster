import asyncio
from sqlalchemy import create_engine, text

engine = create_engine("postgresql://sprintpulse:sprintpulse@localhost/sprintpulse")
with engine.connect() as conn:
    print(conn.execute(text("SELECT count(*) FROM trello_cards WHERE board_id=49 AND is_closed = false;")).scalar())
