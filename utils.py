import os
import uuid
import ffmpeg
from PIL import Image
import math
import traceback

def estimate_processing_time(input_path):
    """
    Estimate video processing time based on file size with more robust error handling.
    """
    try:
        # Vérification explicite de l'existence du fichier
        if not os.path.exists(input_path):
            print(f"Erreur : Le fichier {input_path} n'existe pas")
            return {
                'file_size_mb': 0,
                'estimated_seconds': 30,
                'estimated_human_readable': '30 secondes'
            }

        # Utilisation de os.stat pour plus de sécurité
        file_stat = os.stat(input_path)
        file_size_mb = file_stat.st_size / (1024 * 1024)
        
        # Log détaillé
        print(f"Taille du fichier détectée : {file_size_mb:.2f} Mo")
        
        # Calcul du temps de traitement
        processing_rate = 50  # MB per minute
        estimated_minutes = max(0.1, file_size_mb / processing_rate)
        estimated_time = max(10, min(estimated_minutes * 60, 300))  # 10 sec to 5 min
        
        return {
            'file_size_mb': round(file_size_mb, 2),
            'estimated_seconds': round(estimated_time),
            'estimated_human_readable': format_time(round(estimated_time))
        }
    except Exception as e:
        print(f"Erreur lors de l'estimation du temps de traitement : {e}")
        traceback.print_exc()
        return {
            'file_size_mb': 0,
            'estimated_seconds': 30,
            'estimated_human_readable': '30 secondes'
        }

def process_video(input_path, output_dir):
    try:
        # Vérification explicite de l'existence du fichier
        if not os.path.exists(input_path):
            print(f"Erreur : Le fichier source {input_path} n'existe pas")
            return None

        # Génération de noms de fichiers uniques
        filename = str(uuid.uuid4())
        output_path = os.path.join(output_dir, f"{filename}.mp4")
        thumbnail_path = os.path.join(output_dir, f"{filename}_thumb.jpg")
        
        # Estimation avant le traitement
        processing_estimate = estimate_processing_time(input_path)
        print("Détails d'estimation de traitement :", processing_estimate)
        
        # Conversion vidéo avec gestion des erreurs
        try:
            stream = ffmpeg.input(input_path)
            stream = ffmpeg.output(stream, output_path, 
                                   vcodec='libx264', 
                                   acodec='aac')
            ffmpeg.run(stream, overwrite_output=True)
        except ffmpeg.Error as e:
            print("Erreur FFmpeg lors de la conversion :")
            #print(f"Stderr: {e.stderr.decode() if e.stderr else 'Pas de message d\'erreur'}")




            return None

        # Génération de la miniature
        try:
            probe = ffmpeg.probe(output_path)
            video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            
            (
                ffmpeg
                .input(output_path, ss=1)
                .output(thumbnail_path, vframes=1)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except Exception as thumbnail_error:
            print(f"Erreur lors de la génération de la miniature : {thumbnail_error}")
            # On continue même si la miniature échoue
        
        return {
            'video_path': output_path,
            'thumbnail_path': thumbnail_path,
            'width': int(video_info['width']) if 'width' in video_info else 0,
            'height': int(video_info['height']) if 'height' in video_info else 0,
            'processing_estimate': processing_estimate
        }
    except Exception as e:
        print(f"Erreur inattendue lors du traitement vidéo : {e}")
        traceback.print_exc()
        return None

def format_time(seconds):
    """
    Convertit des secondes en format lisible.
    """
    if seconds < 60:
        return f"{seconds} secondes"
    elif seconds < 3600:
        minutes = math.floor(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''}"
    else:
        hours = math.floor(seconds / 3600)
        return f"{hours} heure{'s' if hours > 1 else ''}"
