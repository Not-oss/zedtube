from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import ForeignKey
from sqlalchemy.sql import func

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    can_upload = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    # Relation modifiée avec backref personnalisé
    created_folders = db.relationship('Folder', back_populates='creator', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now())
    # Relation modifiée
    creator = db.relationship('User', back_populates='created_folders')
    videos = db.relationship('Video', back_populates='parent_folder', lazy=True)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255), nullable=True, default='')
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    upload_date = db.Column(db.DateTime, server_default=func.now())
    processed_path = db.Column(db.String(255), nullable=True)
    is_converted = db.Column(db.Boolean, default=True)
    views = db.Column(db.Integer, default=0)
    folder_id = db.Column(db.Integer, ForeignKey('folder.id'), nullable=True)
    # Relation modifiée
    parent_folder = db.relationship('Folder', back_populates='videos')
    uploader = db.relationship('User', backref='uploaded_videos')
    
class VideoView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, ForeignKey('video.id'), nullable=False)
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=True)  # Nullable pour les visiteurs anonymes
    fingerprint = db.Column(db.String(64), index=True)
    viewed_at = db.Column(db.DateTime, server_default=func.now())
    
    # Relations
    video = db.relationship('Video', backref='views_relations')
    user = db.relationship('User', backref='viewed_videos')