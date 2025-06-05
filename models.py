from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Tasks where user is assignee
    assigned_tasks = relationship("Task", 
                                back_populates="assignee",
                                foreign_keys="Task.assignee_id")
    
    # Tasks created by user
    created_tasks = relationship("Task",
                               back_populates="creator",
                               foreign_keys="Task.creator_id")

class Task(Base):
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime)
    status = Column(String, default="pending")  # pending, in_progress, completed
    priority = Column(String, default="medium")  # low, medium, high
    assignee_id = Column(Integer, ForeignKey('users.id'))
    creator_id = Column(Integer, ForeignKey('users.id'))
    is_completed = Column(Boolean, default=False)
    
    assignee = relationship("User", back_populates="assigned_tasks", foreign_keys=[assignee_id])
    creator = relationship("User", back_populates="created_tasks", foreign_keys=[creator_id]) 