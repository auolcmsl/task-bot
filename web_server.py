from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from jinja2 import Template
import os
import secrets

from config import config
from models import Base, User, Task

# Initialize FastAPI app
app = FastAPI(title="Task Analytics")

# Setup HTTP Basic Auth
security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "admin")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные учетные данные",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Database setup
engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Create templates directory if it doesn't exist
os.makedirs("templates", exist_ok=True)

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# HTML template for the dashboard
dashboard_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Панель аналитики задач</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            color: #333;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            padding: 30px;
            margin-top: 30px;
            margin-bottom: 30px;
        }
        h1 {
            color: #1e3c72;
            font-weight: 600;
            margin-bottom: 30px;
            text-align: center;
        }
        .card {
            margin-bottom: 20px;
            border: none;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s ease-in-out;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .stat-card {
            text-align: center;
            padding: 25px;
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #1e3c72;
            margin-bottom: 10px;
        }
        .stat-label {
            color: #666;
            font-size: 16px;
            font-weight: 500;
        }
        .card-title {
            color: #1e3c72;
            font-weight: 600;
            margin-bottom: 20px;
        }
        .table {
            background: white;
            border-radius: 10px;
            overflow: hidden;
        }
        .table thead th {
            background: #1e3c72;
            color: white;
            font-weight: 500;
            border: none;
        }
        .table tbody tr:hover {
            background-color: rgba(30, 60, 114, 0.05);
        }
        .table td {
            vertical-align: middle;
        }
    </style>
</head>
<body>
    <div class="container mt-4">
        <h1 class="mb-4">Панель аналитики задач</h1>
        
        <!-- Statistics Cards -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="card stat-card">
                    <div class="stat-value">{{ total_tasks }}</div>
                    <div class="stat-label">Всего задач</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stat-card">
                    <div class="stat-value">{{ completed_tasks }}</div>
                    <div class="stat-label">Выполнено задач</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stat-card">
                    <div class="stat-value">{{ active_users }}</div>
                    <div class="stat-label">Активных пользователей</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stat-card">
                    <div class="stat-value">{{ completion_rate }}%</div>
                    <div class="stat-label">Процент выполнения</div>
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div class="row">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Задачи по приоритетам</h5>
                        <div id="priorityChart"></div>
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Динамика создания задач</h5>
                        <div id="timelineChart"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- User Activity -->
        <div class="row mt-4">
            <div class="col-md-12">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">Активность пользователей</h5>
                        <div class="table-responsive">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>Пользователь</th>
                                        <th>Создано задач</th>
                                        <th>Назначено задач</th>
                                        <th>Выполнено задач</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for user in user_stats %}
                                    <tr>
                                        <td>@{{ user.username }}</td>
                                        <td>{{ user.created_tasks }}</td>
                                        <td>{{ user.assigned_tasks }}</td>
                                        <td>{{ user.completed_tasks }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Priority Chart
        var priorityData = {{ priority_chart | safe }};
        Plotly.newPlot('priorityChart', priorityData.data, priorityData.layout);

        // Timeline Chart
        var timelineData = {{ timeline_chart | safe }};
        Plotly.newPlot('timelineChart', timelineData.data, timelineData.layout);
    </script>
</body>
</html>
"""

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def dashboard(username: str = Depends(get_current_username)):
    db = next(get_db())
    
    # Get basic statistics
    total_tasks = db.query(func.count(Task.id)).scalar()
    completed_tasks = db.query(func.count(Task.id)).filter(Task.is_completed == True).scalar()
    active_users = db.query(func.count(User.id)).scalar()
    completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)

    # Get tasks by priority
    priority_stats = db.query(
        Task.priority,
        func.count(Task.id).label('count')
    ).group_by(Task.priority).all()
    
    priority_chart = {
        'data': [{
            'values': [stat.count for stat in priority_stats],
            'labels': [stat.priority for stat in priority_stats],
            'type': 'pie',
            'name': 'Задачи по приоритетам'
        }],
        'layout': {
            'title': 'Задачи по приоритетам',
            'height': 400
        }
    }

    # Get tasks over time
    tasks_over_time = db.query(
        func.date(Task.created_at).label('date'),
        func.count(Task.id).label('count')
    ).group_by('date').order_by('date').all()
    
    timeline_chart = {
        'data': [{
            'x': [str(stat.date) for stat in tasks_over_time],
            'y': [stat.count for stat in tasks_over_time],
            'type': 'scatter',
            'mode': 'lines+markers',
            'name': 'Созданные задачи'
        }],
        'layout': {
            'title': 'Динамика создания задач',
            'height': 400,
            'xaxis': {'title': 'Дата'},
            'yaxis': {'title': 'Количество задач'}
        }
    }

    # Get user statistics
    user_stats = []
    users = db.query(User).all()
    for user in users:
        created_tasks = db.query(func.count(Task.id)).filter(Task.creator_id == user.id).scalar()
        assigned_tasks = db.query(func.count(Task.id)).filter(Task.assignee_id == user.id).scalar()
        completed_tasks = db.query(func.count(Task.id)).filter(
            Task.assignee_id == user.id,
            Task.is_completed == True
        ).scalar()
        
        user_stats.append({
            'username': user.username,
            'created_tasks': created_tasks,
            'assigned_tasks': assigned_tasks,
            'completed_tasks': completed_tasks
        })

    # Render template
    template = Template(dashboard_template)
    return template.render(
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        active_users=active_users,
        completion_rate=completion_rate,
        priority_chart=priority_chart,
        timeline_chart=timeline_chart,
        user_stats=user_stats
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000) 