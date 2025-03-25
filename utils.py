import os
import uuid
import ffmpeg
from PIL import Image
import math

def estimate_processing_time(input_path):
    """
    Estimate video processing time based on file size.
    
    Parameters:
    input_path (str): Path to the input video file
    
    Returns:
    dict: Estimated processing details
    """
    try:
        # Get file size in MB
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        
        # Estimation assumptions:
        # - 50 MB/minute processing rate
        # - Minimum 10 seconds, maximum 5 minutes
        processing_rate = 50  # MB per minute
        
        # Calculate estimated time
        estimated_minutes = file_size_mb / processing_rate
        
        # Bound the estimation
        estimated_time = max(10, min(estimated_minutes * 60, 300))  # 10 sec to 5 min
        
        return {
            'file_size_mb': round(file_size_mb, 2),
            'estimated_seconds': round(estimated_time),
            'estimated_human_readable': format_time(round(estimated_time))
        }
    except Exception as e:
        print(f"Error estimating processing time: {e}")
        return {
            'file_size_mb': 0,
            'estimated_seconds': 30,  # Default estimation
            'estimated_human_readable': '30 secondes'
        }

def format_time(seconds):
    """
    Convert seconds to human-readable format.
    
    Parameters:
    seconds (int): Number of seconds
    
    Returns:
    str: Formatted time string
    """
    if seconds < 60:
        return f"{seconds} secondes"
    elif seconds < 3600:
        minutes = math.floor(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''}"
    else:
        hours = math.floor(seconds / 3600)
        return f"{hours} heure{'s' if hours > 1 else ''}"

def process_video(input_path, output_dir):
    filename = str(uuid.uuid4())
    output_path = os.path.join(output_dir, f"{filename}.mp4")
    thumbnail_path = os.path.join(output_dir, f"{filename}_thumb.jpg")
    
    try:
        # Estimation avant le traitement
        processing_estimate = estimate_processing_time(input_path)
        
        # Conversion vidéo
        stream = ffmpeg.input(input_path)
        stream = ffmpeg.output(stream, output_path, vcodec='libx264', acodec='aac')
        ffmpeg.run(stream, overwrite_output=True)
        
        # Génération de la miniature
        probe = ffmpeg.probe(output_path)
        video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        
        # Capture de la première image à 1 seconde
        (
            ffmpeg
            .input(output_path, ss=1)
            .output(thumbnail_path, vframes=1)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        
        return {
            'video_path': output_path,
            'thumbnail_path': thumbnail_path,
            'width': int(video_info['width']),
            'height': int(video_info['height']),
            'processing_estimate': processing_estimate
        }
    except ffmpeg.Error as e:
        print(f"Erreur de conversion: {e}")
        return None
