import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String,
    DateTime, Text, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/scans.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Website(Base):
    __tablename__ = "websites"
    id         = Column(Integer, primary_key=True, index=True)
    url        = Column(String, unique=True, nullable=False)
    cron_schedule = Column(String, nullable=False)   # still stores cron internally
    api_token  = Column(String, unique=True, nullable=False)
    last_scan  = Column(DateTime)
    last_status= Column(String)

class Scan(Base):
    __tablename__ = "scans"
    id              = Column(Integer, primary_key=True, index=True)
    website_id      = Column(Integer, nullable=False)
    timestamp       = Column(DateTime, default=datetime.utcnow)
    pages_found     = Column(Integer)
    images_found    = Column(Integer)
    videos_found    = Column(Integer)
    pages_included  = Column(Integer)
    images_included = Column(Integer)
    videos_included = Column(Integer)
    errors          = Column(Text)
    extra_info      = Column(JSON)

def init_db():
    Base.metadata.create_all(bind=engine)