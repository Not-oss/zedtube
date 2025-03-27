from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import ForeignKey
from sqlalchemy.sql import func
from flask import url_for  # Ajout de cette importation

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    can_upload = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    upload_requested = db.Column(db.Boolean, default=False)
    upload_requested_date = db.Column(db.DateTime, nullable=True)
    
    # Relations
    folders = db.relationship('Folder', backref='user', lazy=True)
    uploaded_videos = db.relationship('Video', backref='uploader', lazy=True)

    def set_password(self, password):
        """Hash et stocke le mot de passe"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Vérifie le mot de passe contre le hash stocké"""
        return check_password_hash(self.password_hash, password)

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    custom_thumbnail = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now())
    
    # Relation avec les vidéos
    videos = db.relationship('Video', backref='folder', lazy=True, 
                           cascade='all, delete-orphan',
                           order_by='Video.upload_date.desc()')
    def get_thumbnail(self):
        """Retourne le chemin de la miniature du dossier"""
        if self.custom_thumbnail:
            return url_for('serve_uploaded_file', filename=self.custom_thumbnail)
        elif self.videos:
            return url_for('serve_thumbnail', filename=self.videos[0].filename)
        return url_for('static', filename='default_folder.png')

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

class VideoView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, ForeignKey('video.id'), nullable=False)
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=True)
    fingerprint = db.Column(db.String(64), index=True)
    viewed_at = db.Column(db.DateTime, server_default=func.now())
    
    # Relations
    video = db.relationship('Video', backref='view_records')
    user = db.relationship('User', backref='view_history')