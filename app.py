from flask import Flask, render_template, request, redirect, url_for, send_from_directory, abort, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from models import db, User, Video
from utils import process_video
import os
import sys
import traceback

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
        # Add some error handling and logging
        videos = Video.query.order_by(Video.upload_date.desc()).all()
        return render_template('home.html', videos=videos)
    except Exception as e:
        # Print the full traceback to console
        print("Error in home route:", str(e))
        traceback.print_exc()
        # You might want to return an error page or message
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

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_video():
    if not current_user.can_upload:
        return "Vous n'avez pas la permission d'uploader", 403
    
    if request.method == 'POST':
        video = request.files['video']
        title = request.form.get('title', '').strip()  # Get title, remove whitespace
        
        if video:
            filename = secure_filename(video.filename)
            original_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            video.save(original_path)
            
            # If no title is provided, use the original filename (without extension) as the title
            if not title:
                title = os.path.splitext(filename)[0]
            
            # Traitement de la vidéo
            processed_result = process_video(original_path, app.config['UPLOAD_FOLDER'])
            
            if processed_result:
                new_video = Video(
                    filename=os.path.basename(processed_result['video_path']),
                    original_filename=filename,
                    title=title,
                    user_id=current_user.id
                )
                db.session.add(new_video)
                db.session.commit()
                
                # Return processing estimation details
                return jsonify({
                    'message': 'Upload en cours de traitement',
                    'file_size': processed_result['processing_estimate']['file_size_mb'],
                    'estimated_time': processed_result['processing_estimate']['estimated_human_readable']
                }), 200
            
        return "Erreur d'upload", 400
    
    return render_template('upload.html')
@app.route('/video/<filename>')
def serve_video(filename):
    video = Video.query.filter_by(filename=filename).first()
    if not video:
        abort(404)
    
    user_agent = request.headers.get('User-Agent', '').lower()
    
    # Détection Discord améliorée
    if any(bot in user_agent for bot in ['discordbot', 'discord', 'telegrambot']):
        thumbnail_url = request.host_url.rstrip('/') + url_for('serve_thumbnail', filename=filename)
        video_url = request.host_url.rstrip('/') + url_for('serve_video', filename=filename)
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>ZedTube Vidéo</title>
            <meta property="og:title" content="Vidéo ZedTube" />
            <meta property="og:type" content="video.other" />
            <meta property="og:video" content="{video_url}" />
            <meta property="og:video:type" content="video/mp4" />
            <meta property="og:image" content="{thumbnail_url}" />
            <meta property="og:image:type" content="image/jpeg" />
            <meta name="twitter:card" content="player" />
            <meta name="twitter:player" content="{video_url}" />
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
    base_filename = os.path.splitext(filename)[0]
    thumbnail_filename = f"{base_filename}_thumb.jpg"
    return send_from_directory(app.config['UPLOAD_FOLDER'], thumbnail_filename)

@app.route('/generate_share_link/<int:video_id>')
@login_required
def generate_share_link(video_id):
    video = Video.query.get_or_404(video_id)
    # Correction du lien : utiliser l'URL complète
    share_link = request.host_url.rstrip('/') + url_for('serve_video', filename=video.filename)
    return share_link

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
