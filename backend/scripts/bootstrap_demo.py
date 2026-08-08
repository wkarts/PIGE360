#!/usr/bin/env python3
from pathlib import Path
import os

os.environ.setdefault("APP_DEMO_MODE","true")
os.environ.setdefault("APP_ENV","development")
from app.bootstrap.config import Settings
from app.bootstrap.demo import seed_demo
from app.shared.database.router import DataRouter

settings=Settings.from_env();result=seed_demo(DataRouter(settings),settings,Path(__file__).resolve().parents[2])
print(result)
