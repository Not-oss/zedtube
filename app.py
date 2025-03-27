from flask import Flask, render_template, request, redirect, url_for, send_from_directory, abort, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
from functools import wraps
from urllib.parse import quote

from werkzeug.utils import secure_filename
from models import db, User, Video, VideoView, Folder  # Ajoutez Folder ici
from datetime import datetime
from utils import process_video
from transcoder import process_video_with_transcode
import os
import sys
import traceback
import hashlib
import re


app = Flask(__name__)
app.config['SECRET_KEY'] = 'votre_clé_secrète_ici'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///youtube_clone.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1 Go
app.config['WTF_CSRF_ENABLED'] = True
app.config['GOOGLE_CLOUD_PROJECT'] = 'dogwood-actor-450221-j9'
app.config['GOOGLE_CLOUD_BUCKET'] = 'zedtube-videos'  # Remplacer par le nom de votre bucket

# Ensure uploads directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    if current_user.is_authenticated:
        folders = Folder.query.filter(
            (Folder.user_id == current_user.id) | 
            (Folder.is_public == True)
        ).order_by(Folder.name).all()
    else:
        folders = Folder.query.filter_by(is_public=True).order_by(Folder.name).all()
    
    videos = Video.query.filter_by(folder_id=None).order_by(Video.upload_date.desc()).all()
    return render_template('home.html', folders=folders, videos=videos)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Connexion réussie !', 'success')
            return redirect(url_for('home'))
        else:
            flash('Nom d\'utilisateur ou mot de passe incorrect', 'error')
    
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
    
    # Vérification des permissions
    if folder.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    try:
        # Suppression des vidéos associées
        for video in folder.videos:
            # Suppression du fichier vidéo
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
            if os.path.exists(video_path):
                os.remove(video_path)
            
            # Suppression de la thumbnail
            thumb_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                    f"{os.path.splitext(video.filename)[0]}_thumb.jpg")
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            
            # Suppression de la vidéo de la base de données
            db.session.delete(video)
        
        # Suppression de la thumbnail du dossier si elle existe
        if folder.custom_thumbnail:
            thumb_path = os.path.join(app.config['UPLOAD_FOLDER'], folder.custom_thumbnail)
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        
        # Suppression du dossier de la base de données
        db.session.delete(folder)
        db.session.commit()
        
        flash('Dossier et son contenu supprimés avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'error')
        app.logger.error(f"Erreur suppression dossier {folder_id}: {str(e)}")
    
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


@app.route('/video/<int:video_id>')
def video_page(video_id):
    video = Video.query.get_or_404(video_id)
    fingerprint = get_client_fingerprint()
    
    existing_view = VideoView.query.filter_by(
        video_id=video_id,
        fingerprint=fingerprint
    ).first()

    if not existing_view:
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
        
        if not username or not password:
            flash('Le nom d\'utilisateur et le mot de passe sont requis', 'error')
            return redirect(url_for('register'))
        
        if len(username) < 3 or len(username) > 20:
            flash('Le nom d\'utilisateur doit contenir entre 3 et 20 caractères', 'error')
            return redirect(url_for('register'))
        
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            flash('Le nom d\'utilisateur ne peut contenir que des lettres, chiffres, _ et -', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 8:
            flash('Le mot de passe doit contenir au moins 8 caractères', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Ce nom d\'utilisateur est déjà utilisé', 'error')
            return redirect(url_for('register'))
        
        new_user = User(
            username=username,
            can_upload=False,
            is_admin=False,
            upload_requested=False
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Inscription réussie ! Vous pouvez maintenant vous connecter.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if request.method == 'POST':
        admin_username = request.form['admin_username']
        admin_password = request.form['admin_password']
        username = request.form['username']
        password = request.form['password']
        
        # Vérification des identifiants admin
        admin = User.query.filter_by(username=admin_username).first()
        if not admin or not admin.is_admin or not admin.check_password(admin_password):
            flash('Identifiants administrateur incorrects', 'error')
            return redirect(url_for('add_user'))
        
        # Validation du nouveau nom d'utilisateur
        if len(username) < 3 or len(username) > 20:
            flash('Le nom d\'utilisateur doit contenir entre 3 et 20 caractères', 'error')
            return redirect(url_for('add_user'))
        
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            flash('Le nom d\'utilisateur ne peut contenir que des lettres, chiffres, _ et -', 'error')
            return redirect(url_for('add_user'))
        
        if len(password) < 8:
            flash('Le mot de passe doit contenir au moins 8 caractères', 'error')
            return redirect(url_for('add_user'))
        
        if User.query.filter_by(username=username).first():
            flash('Ce nom d\'utilisateur est déjà utilisé', 'error')
            return redirect(url_for('add_user'))
        
        new_user = User(
            username=username,
            can_upload=False,
            is_admin=False,
            upload_requested=False
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Utilisateur créé avec succès', 'success')
        return redirect(url_for('admin_panel'))
    
    return render_template('add_user.html')

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

@app.route('/delete_video/<int:video_id>', methods=['POST'])
@login_required
def delete_video(video_id):
    video = Video.query.get_or_404(video_id)
    
    # Vérification des permissions
    if video.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    try:
        # Suppression du fichier vidéo principal
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
        if os.path.exists(video_path):
            os.remove(video_path)
        
        # Suppression de la version convertie si elle existe
        if video.processed_path and video.processed_path != video.filename:
            processed_path = os.path.join(app.config['UPLOAD_FOLDER'], video.processed_path)
            if os.path.exists(processed_path):
                os.remove(processed_path)
        
        # Suppression de la thumbnail
        thumb_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                f"{os.path.splitext(video.filename)[0]}_thumb.jpg")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        # Suppression des entrées de visualisation associées
        VideoView.query.filter_by(video_id=video.id).delete()
        
        # Suppression de la vidéo de la base de données
        db.session.delete(video)
        db.session.commit()
        
        flash('Vidéo et tous ses fichiers associés supprimés avec succès', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'error')
        app.logger.error(f"Erreur suppression vidéo {video_id}: {str(e)}")

    return redirect(request.referrer or url_for('home'))


@app.route('/test_upload', methods=['POST'])
def test_upload():
    return jsonify({'status': 'success', 'method': request.method})

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_video():
    if not current_user.can_upload:
        flash('Vous n\'avez pas les droits d\'upload. Veuillez demander l\'autorisation à l\'administrateur.', 'error')
        return redirect(url_for('profile'))
    
    if request.method == 'POST':
        if 'video' not in request.files:
            flash('Aucun fichier sélectionné', 'error')
            return redirect(request.url)
        
        file = request.files['video']
        if file.filename == '':
            flash('Aucun fichier sélectionné', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            new_video = Video(
                filename=filename,
                original_filename=file.filename,
                title=request.form.get('title', ''),
                user_id=current_user.id,
                folder_id=request.form.get('folder_id') or None
            )
            
            db.session.add(new_video)
            db.session.commit()
            
            if request.form.get('convert', 'true').lower() == 'true':
                # Utiliser Google Cloud Transcode pour la conversion
                output_filename = f"converted_{filename}"
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
                
                if process_video_with_transcode(
                    file_path,
                    output_path,
                    app.config['GOOGLE_CLOUD_PROJECT'],
                    app.config['GOOGLE_CLOUD_BUCKET']
                ):
                    # Mettre à jour le nom du fichier dans la base de données
                    new_video.filename = output_filename
                    db.session.commit()
                    flash('Vidéo convertie avec succès', 'success')
                else:
                    flash('Erreur lors de la conversion de la vidéo', 'error')
            
            flash('Vidéo uploadée avec succès', 'success')
            return redirect(url_for('home'))
        
        flash('Type de fichier non autorisé', 'error')
        return redirect(request.url)
    
    return render_template('upload.html')


@app.route('/embed/<int:video_id>')
def discord_embed(video_id):
    video = Video.query.get_or_404(video_id)
    
    try:
        probe = ffmpeg.probe(os.path.join(app.config['UPLOAD_FOLDER'], video.filename))
        video_stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        width = int(video_stream.get('width', 1920))
        height = int(video_stream.get('height', 1080))
    except:
        width, height = 1920, 1080
    
    return render_template('discord_embed.html',
        video=video,
        video_url=url_for('serve_video', filename=video.filename, _external=True),
        thumbnail_url=url_for('serve_thumbnail', filename=video.filename, _external=True),
        original_url=url_for('video_page', video_id=video_id, _external=True),
        video_width=width,
        video_height=height
    )


@app.route('/video/<filename>')
def serve_video(filename):
    video = Video.query.filter_by(filename=filename).first()
    if not video:
        abort(404)
    
    user_agent = request.headers.get('User-Agent', '').lower()
    
    if 'discord' in user_agent:
        return redirect(url_for('discord_embed', video_id=video.id))
    
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
@app.route('/thumbnail/<filename>')
def serve_thumbnail(filename):
    try:
        base_filename = os.path.splitext(filename)[0]
        thumbnail_filename = f"{base_filename}_thumb.jpg"
        thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_filename)
        
        if not os.path.exists(thumbnail_path):
            # Regénérer la thumbnail si manquante
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                (
                    ffmpeg
                    .input(video_path, ss='00:00:01')
                    .output(thumbnail_path, vframes=1)
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            except Exception as e:
                print(f"Erreur regénération thumbnail: {e}")
                return send_from_directory('static', 'default_thumb.jpg')
        
        return send_from_directory(app.config['UPLOAD_FOLDER'], thumbnail_filename)
    except Exception as e:
        print(f"Erreur thumbnail: {e}")
        return send_from_directory('static', 'default_thumb.jpg')

# Upload thumbnail de dossier
@app.route('/upload_folder_thumbnail/<int:folder_id>', methods=['POST'])
@login_required
def upload_folder_thumbnail(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    if folder.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    if 'thumbnail' not in request.files:
        flash('Aucun fichier sélectionné', 'error')
        return redirect(request.referrer)
    
    file = request.files['thumbnail']
    if file.filename == '':
        flash('Aucun fichier sélectionné', 'error')
        return redirect(request.referrer)
    
    if file and allowed_file(file.filename):
        filename = f"folder_{folder_id}_thumb.{file.filename.rsplit('.', 1)[1].lower()}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Supprime l'ancienne thumbnail si elle existe
        if folder.custom_thumbnail and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], folder.custom_thumbnail)):
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], folder.custom_thumbnail))
        
        folder.custom_thumbnail = filename
        db.session.commit()
        flash('Miniature du dossier mise à jour!', 'success')
    
    return redirect(request.referrer)

@app.route('/generate_share_link/<int:video_id>')
def generate_share_link(video_id):
    video = Video.query.get_or_404(video_id)
    video_url = url_for('serve_video', filename=video.filename, _external=True)
    thumbnail_url = url_for('serve_thumbnail', filename=video.filename, _external=True)
    
    return jsonify({
        'share_link': url_for('discord_embed', video_id=video.id, _external=True),
        'direct_link': video_url
    })

# Ajoutez ces routes
@app.route('/toggle_folder_privacy/<int:folder_id>', methods=['POST'])
@login_required
def toggle_folder_privacy(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    if folder.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    folder.is_public = not folder.is_public
    db.session.commit()
    return jsonify({'status': 'success', 'is_public': folder.is_public})


if __name__ == '__main__':
    with app.app_context():
        try:
            # Suppression de toutes les tables
            db.drop_all()
            # Recréation de toutes les tables
            db.create_all()
            print("Base de données initialisée avec succès")
        except Exception as e:
            print("Erreur lors de l'initialisation de la base de données:", str(e))
            traceback.print_exc()
    
    app.run(host='0.0.0.0', port=8081, debug=True)

