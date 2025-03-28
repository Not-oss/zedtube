import os
import time
from google.cloud import storage
from google.cloud.video import transcoder
from typing import Dict, Optional

class TranscoderError(Exception):
    """Exception personnalisée pour les erreurs de transcodage."""
    pass

def upload_to_gcs(local_file_path: str, bucket_name: str, destination_blob_name: str) -> str:
    """Upload un fichier vers Google Cloud Storage."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(local_file_path)
        return f"gs://{bucket_name}/{destination_blob_name}"
    except Exception as e:
        raise TranscoderError(f"Erreur lors de l'upload vers GCS: {str(e)}")

def download_from_gcs(bucket_name: str, source_blob_name: str, destination_file_path: str) -> None:
    """Télécharge un fichier depuis Google Cloud Storage."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)
        blob.download_to_filename(destination_file_path)
    except Exception as e:
        raise TranscoderError(f"Erreur lors du téléchargement depuis GCS: {str(e)}")

def get_video_info(file_path: str) -> Dict:
    """Analyse une vidéo pour obtenir ses caractéristiques."""
    try:
        probe = ffmpeg.probe(file_path)
        video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        audio_info = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
        
        return {
            'width': int(video_info.get('width', 1920)),
            'height': int(video_info.get('height', 1080)),
            'fps': eval(video_info.get('r_frame_rate', '30/1')),
            'bitrate': int(video_info.get('bit_rate', 2500000)),
            'audio_bitrate': int(audio_info.get('bit_rate', 64000)),
            'audio_channels': int(audio_info.get('channels', 2)),
            'audio_sample_rate': int(audio_info.get('sample_rate', 48000))
        }
    except Exception as e:
        raise TranscoderError(f"Erreur lors de l'analyse de la vidéo: {str(e)}")

def create_transcode_job(input_uri: str, output_uri: str, project_id: str, location: str = "us-central1") -> str:
    """Crée un job de transcodage avec Google Cloud Transcode."""
    try:
        client = transcoder.TranscoderServiceClient()
        parent = f"projects/{project_id}/locations/{location}"
        
        job = transcoder.Job()
        job.input_uri = input_uri
        job.output_uri = output_uri
        job.template_id = 'preset/web-hd'  # Utilisation du preset web-hd
        
        response = client.create_job(parent=parent, job=job)
        return response.name
    except Exception as e:
        raise TranscoderError(f"Erreur lors de la création du job: {str(e)}")

def get_job_status(job_name: str, project_id: str, location: str = "us-central1") -> Optional[str]:
    """Récupère le statut d'un job de transcodage."""
    try:
        client = transcoder.TranscoderServiceClient()
        job = client.get_job(name=job_name)
        return job.state
    except Exception as e:
        raise TranscoderError(f"Erreur lors de la récupération du statut: {str(e)}")

def process_video_with_transcode(input_file_path: str, output_file_path: str, project_id: str, bucket_name: str, location: str = "us-central1") -> bool:
    """Traite une vidéo en utilisant Google Cloud Transcode."""
    try:
        if not os.path.exists(input_file_path):
            raise TranscoderError(f"Fichier d'entrée non trouvé: {input_file_path}")

        input_blob_name = f"input/{os.path.basename(input_file_path)}"
        input_uri = upload_to_gcs(input_file_path, bucket_name, input_blob_name)
        
        # Création d'un dossier unique pour la sortie
        output_folder = f"output/{int(time.time())}/"
        output_uri = f"gs://{bucket_name}/{output_folder}"
        
        job_name = create_transcode_job(input_uri, output_uri, project_id, location)
        print(f"Job créé: {job_name}")  # Pour le débogage
        
        max_attempts = 30  # 5 minutes max (10s * 30)
        attempts = 0
        while attempts < max_attempts:
            status = get_job_status(job_name, project_id, location)
            
            if status == transcoder.Job.ProcessingState.SUCCEEDED:
                # Le fichier converti sera dans le dossier avec le même nom que l'entrée
                output_blob_name = f"{output_folder}{os.path.basename(output_file_path)}"
                download_from_gcs(bucket_name, output_blob_name, output_file_path)
                return True
            
            if status == transcoder.Job.ProcessingState.FAILED:
                raise TranscoderError("Le job de transcodage a échoué")
            
            time.sleep(10)
            attempts += 1
        
        raise TranscoderError("Le job de transcodage a expiré")
    
    except Exception as e:
        print(f"Erreur pendant le transcodage: {str(e)}")
        return False