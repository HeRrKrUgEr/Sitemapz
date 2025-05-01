import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text, JSON,
    ForeignKey, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/scans.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Website(Base):
    __tablename__ = "websites"
    id            = Column(Integer, primary_key=True, index=True)
    url           = Column(String, unique=True, nullable=False)
    cron_schedule = Column(String, nullable=False)
    api_token     = Column(String, unique=True, nullable=False)
    last_scan     = Column(DateTime)
    last_status   = Column(String)

    scans = relationship(
        "Scan", back_populates="website", cascade="all, delete-orphan"
    )

class Scan(Base):
    __tablename__ = "scans"
    id              = Column(Integer, primary_key=True, index=True)
    website_id      = Column(Integer, ForeignKey("websites.id"), nullable=False)
    timestamp       = Column(DateTime, default=datetime.utcnow)
    pages_found     = Column(Integer)
    images_found    = Column(Integer)
    videos_found    = Column(Integer)
    pages_included  = Column(Integer)
    images_included = Column(Integer)
    videos_included = Column(Integer)
    errors          = Column(Text)
    extra_info      = Column(JSON)

    website = relationship("Website", back_populates="scans")
    pages   = relationship(
        "PageScan", back_populates="scan", cascade="all, delete-orphan"
    )

class PageScan(Base):
    __tablename__ = "page_scans"
    id          = Column(Integer, primary_key=True, index=True)
    scan_id     = Column(Integer, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    url         = Column(String, nullable=False, index=True)
    status      = Column(Integer, nullable=False)   # HTTP status (200/301/404/etc.)
    lastmod     = Column(DateTime, nullable=True)    # parsed Last-Modified
    redirect_to = Column(String, nullable=True)      # final target if redirect
    content_hash  = Column(String, nullable=True)   # <— new
    scan = relationship("Scan", back_populates="pages")


def init_db():
    Base.metadata.create_all(bind=engine)
