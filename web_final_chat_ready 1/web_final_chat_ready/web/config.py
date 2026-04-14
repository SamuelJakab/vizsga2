import os

class Config:
    SQLALCHEMY_DATABASE_URI = "sqlite:///electro.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = "your-secret-key-here"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True