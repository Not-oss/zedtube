from flask import Flask, render_template, request, redirect, url_for, send_from_directory, abort, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from functools import wraps

from werkzeug.utils import secure_filename
from models import db, User, Video, VideoView, Folder  # Ajoutez Folder ici
from datetime import datetime
from utils import process_video
import os
import sys
import traceback
import hashlib


app = Flask(__name__)
app.config['SECRET_KEY'] = 'votre_clé_secrète_ici'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///youtube_clone.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1 Go

# Ensure uploads directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    try:
        # Ensure videos exist by creating a default video if none
        if Video.query.count() == 0:
            # Create a default video for demonstration
            default_video = Video(
                filename='default_video.mp4',  # Ensure this file exists in your uploads folder
                original_filename='default_video.mp4',  # Add this line
                title='Welcome to ZedTube',
                user_id=1,  # Assuming admin user exists
                upload_date=datetime.utcnow()
            )
            db.session.add(default_video)
            db.session.commit()

        videos = Video.query.order_by(Video.upload_date.desc()).all()
        return render_template('home.html', videos=videos)
    except Exception as e:
        print("Error in home route:", str(e))
        traceback.print_exc()
        return f"An error occurred: {str(e)}", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Debug print
        print(f"Login attempt: Username = {username}")
        
        user = User.query.filter_by(username=username).first()
        
        if user:
            # Debug print
            print(f"User found: {user.username}")
            
            if user.check_password(password):
                login_user(user)
                print(f"Login successful for {username}")
                return redirect(url_for('home'))
            else:
                print(f"Password incorrect for {username}")
                flash('Mot de passe incorrect', 'error')
        else:
            print(f"No user found with username {username}")
            flash('Utilisateur non trouvé', 'error')
    
    return render_template('login.html')


def get_client_fingerprint():
    """Generate unique client fingerprint"""
    user_agent = request.headers.get('User-Agent', '')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    accept_language = request.headers.get('Accept-Language', '')
    fingerprint_str = f"{user_agent}{ip}{accept_language}"
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


## Création de dossier
@app.route('/create_folder', methods=['POST'])
@login_required
def create_folder():
    if not current_user.can_upload:
        abort(403)
    
    name = request.form.get('name')
    if not name:
        flash('Le nom du dossier est requis', 'error')
        return redirect(url_for('home'))

    new_folder = Folder(
        name=name, 
        user_id=current_user.id
    )
    db.session.add(new_folder)
    db.session.commit()
    
    flash(f'Dossier "{name}" créé avec succès', 'success')
    return redirect(url_for('home'))

# Suppression de dossier
@app.route('/delete_folder/<int:folder_id>', methods=['POST'])
@login_required
def delete_folder(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    if folder.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    # Réaffecter les vidéos à aucun dossier
    Video.query.filter_by(folder_id=folder.id).update({'folder_id': None})
    
    db.session.delete(folder)
    db.session.commit()
    
    flash('Dossier supprimé avec succès', 'success')
    return redirect(url_for('home'))

# Vue d'un dossier spécifique
@app.route('/folder/<int:folder_id>')
@login_required
def folder_view(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    videos = Video.query.filter_by(folder_id=folder.id).order_by(Video.upload_date.desc()).all()
    return render_template('home.html', videos=videos, selected_folder=folder)
# Déplacer une vidéo
@app.route('/move_video/<int:video_id>', methods=['POST'])
@login_required
def move_video(video_id):
    video = Video.query.get_or_404(video_id)
    if video.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    folder_id = request.form.get('folder_id')
    video.folder_id = folder_id if folder_id else None
    db.session.commit()
    
    flash('Vidéo déplacée avec succès', 'success')
    return redirect(request.referrer or url_for('home'))

@app.route('/folder/<int:folder_id>')
def folder_view(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    videos = Video.query.filter_by(folder_id=folder_id).order_by(Video.upload_date.desc()).all()
    return render_template('home.html', videos=videos, selected_folder=folder)

@app.route('/video/<int:video_id>')
def video_page(video_id):
    video = Video.query.get_or_404(video_id)
    fingerprint = get_client_fingerprint()
    
    # Vérifie si cette vue existe déjà
    existing_view = VideoView.query.filter_by(
        video_id=video_id,
        fingerprint=fingerprint
    ).first()

    if not existing_view:
        # Nouvelle vue
        video.views += 1
        new_view = VideoView(
            video_id=video_id,
            fingerprint=fingerprint,
            user_id=current_user.id if current_user.is_authenticated else None
        )
        db.session.add(new_view)
        db.session.commit()

    return render_template('video_player.html', video=video)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Validation simple
        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        # Création du user
        new_user = User(username=username)
        new_user.set_password(password)
        
        # Par défaut, les nouveaux users ne peuvent pas upload
        new_user.can_upload = False
        new_user.is_admin = False
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Route pour demander les droits d'upload
@app.route('/request_upload', methods=['POST'])
@login_required
def request_upload():
    current_user.upload_requested = True
    db.session.commit()
    flash('Your upload request has been submitted to admin', 'info')
    return redirect(url_for('profile'))

# Route admin pour gérer les demandes
@app.route('/admin/requests')
@login_required
@admin_required  # À créer ou remplacer par une vérification is_admin
def manage_requests():
    pending_users = User.query.filter_by(upload_requested=True, can_upload=False).all()
    return render_template('admin_requests.html', users=pending_users)

# Accepter/refuser une demande
@app.route('/admin/request_action/<int:user_id>/<action>')
@login_required
@admin_required
def request_action(user_id, action):
    user = User.query.get_or_404(user_id)
    if action == 'approve':
        user.can_upload = True
        flash(f'Upload rights granted to {user.username}', 'success')
    user.upload_requested = False
    db.session.commit()
    return redirect(url_for('manage_requests'))





@app.route('/create_admin')
def create_admin():
    with app.app_context():
        # Check if admin already exists
        existing_user = User.query.filter_by(username='Zed').first()
        if existing_user:
            return "Admin user already exists"
        
        # Create admin user
        admin_user = User(
            username='Zed', 
            can_upload=True, 
            is_admin=True
        )
        admin_user.set_password('Zed123')
        
        db.session.add(admin_user)
        db.session.commit()
        
        return "Admin user created successfully"
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))
@app.route('/admin/panel')
@login_required
def admin_panel():
    if not current_user.is_admin:
        abort(403)  # Forbidden
    
    videos = Video.query.order_by(Video.upload_date.desc()).all()
    users = User.query.all()
    return render_template('admin_panel.html', videos=videos, users=users)

@app.route('/admin/delete_video/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    if not current_user.is_admin:
        abort(403)  # Forbidden
    
    video = Video.query.get_or_404(video_id)
    
    # Supprimer le fichier vidéo
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
    thumb_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{os.path.splitext(video.filename)[0]}_thumb.jpg")
    
    try:
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        # Supprimer de la base de données
        db.session.delete(video)
        db.session.commit()
        
        flash('Vidéo supprimée avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'error')
    
    return redirect(url_for('admin_panel'))


@app.route('/test_upload', methods=['POST'])
def test_upload():
    return jsonify({'status': 'success', 'method': request.method})

@app.route('/upload', methods=['GET', 'POST'])  # Les deux méthodes si nécessaire
@login_required
def upload_video():
    if request.method == 'GET':
        return render_template('upload.html')
    if not current_user.can_upload:
        return jsonify({'error': "Vous n'avez pas la permission d'uploader"}), 403
    
    if 'video' not in request.files:
        return jsonify({'error': 'Aucun fichier vidéo fourni'}), 400
    
    video = request.files['video']
    title = request.form.get('title', '').strip()
    convert = request.form.get('convert', 'true') == 'true'
    
    if video.filename == '':
        return jsonify({'error': 'Aucun fichier sélectionné'}), 400
    
    try:
        filename = secure_filename(video.filename)
        original_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        video.save(original_path)
        
        processed_result = process_video(original_path, app.config['UPLOAD_FOLDER'], convert)
        
        if processed_result:
            new_video = Video(
                filename=os.path.basename(processed_result['video_path']),
                original_filename=filename,
                title=title or os.path.splitext(filename)[0],
                user_id=current_user.id,
                is_converted=convert
            )
            db.session.add(new_video)
            db.session.commit()
            
            return jsonify({
                'message': 'Upload réussi',
                'file_size': processed_result['processing_estimate']['file_size_mb'],
                'estimated_time': processed_result['processing_estimate']['estimated_human_readable']
            }), 200
        
        return jsonify({'error': 'Erreur de traitement vidéo'}), 500
    
    except Exception as e:
        return jsonify({'error': f'Erreur: {str(e)}'}), 500

@app.route('/video/<filename>')
def serve_video(filename):
    video = Video.query.filter_by(filename=filename).first()
    if not video:
        abort(404)
    
    user_agent = request.headers.get('User-Agent', '').lower()
    
    # Improved Discord bot detection
    if any(bot in user_agent for bot in ['discordbot', 'discord', 'telegrambot']):
        thumbnail_url = request.host_url.rstrip('/') + url_for('serve_thumbnail', filename=filename)
        video_url = request.host_url.rstrip('/') + url_for('serve_video', filename=filename)[1:]
        
        return f'''
        <!DOCTYPE html>
        <html prefix="og: https://ogp.me/ns#">
        <head>
            <title>ZedTube Vidéo</title>
            <meta property="og:title" content="{video.title or 'Vidéo ZedTube'}" />
            <meta property="og:type" content="video.other" />
            <meta property="og:video" content="{video_url}" />
            <meta property="og:video:type" content="video/mp4" />
            <meta property="og:video:width" content="640" />
            <meta property="og:video:height" content="360" />
            <meta property="og:image" content="{thumbnail_url}" />
            <meta property="og:image:type" content="image/jpeg" />
            <meta name="twitter:card" content="player" />
            <meta name="twitter:player" content="{video_url}" />
            <meta name="twitter:player:width" content="640" />
            <meta name="twitter:player:height" content="360" />
            <meta name="twitter:image" content="{thumbnail_url}" />
        </head>
        <body>
            <video width="100%" controls autoplay>
                <source src="{video_url}" type="video/mp4">
                Votre navigateur ne supporte pas la vidéo.
            </video>
        </body>
        </html>
        '''
    
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
@app.route('/thumbnail/<filename>')
def serve_thumbnail(filename):
    try:
        base_filename = os.path.splitext(filename)[0]
        thumbnail_filename = f"{base_filename}_thumb.jpg"
        return send_from_directory(app.config['UPLOAD_FOLDER'], thumbnail_filename)
    except FileNotFoundError:
        # Retourner une image par défaut si la miniature n'existe pas
        return send_from_directory('static', 'default_thumb.jpg')

@app.route('/generate_share_link/<int:video_id>')
def generate_share_link(video_id):
    video = Video.query.get_or_404(video_id)
    share_link = request.host_url.rstrip('/') + url_for('video_page', video_id=video.id)
    return jsonify({'share_link': share_link})

if __name__ == '__main__':
    with app.app_context():
        try:
            # Drop all tables (be careful in production!)
            # Recreate all tables
            db.create_all()
            print("Database initialized successfully")
        except Exception as e:
            print("Error initializing database:", str(e))
            traceback.print_exc()
    
    app.run(host='0.0.0.0', port=8081, debug=True)

