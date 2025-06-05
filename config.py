from dataclasses import dataclass, field
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///tasks.db")
    ADMIN_IDS: list[int] = field(default_factory=lambda: [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id])

config = Config() 