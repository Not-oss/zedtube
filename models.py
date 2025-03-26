from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    can_upload = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=True, default='')
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    upload_date = db.Column(DateTime, server_default=func.now())
    processed_path = db.Column(db.String(255), nullable=True)
    is_converted = db.Column(db.Boolean, default=True)
    views = db.Column(db.Integer, default=0)
    views_relations = db.relationship('VideoView', backref='video', lazy=True)

class VideoView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, ForeignKey('video.id'), nullable=False)
    fingerprint = db.Column(db.String(64), index=True)
    created_at = db.Column(DateTime, server_default=func.now())