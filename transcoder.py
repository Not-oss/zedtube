from google.cloud import videointelligence_v1
from google.cloud import storage
import os
import time

def upload_to_gcs(local_file_path, bucket_name, destination_blob_name):
    """Upload un fichier vers Google Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(local_file_path)
    return f"gs://{bucket_name}/{destination_blob_name}"

def download_from_gcs(bucket_name, source_blob_name, destination_file_path):
    """Télécharge un fichier depuis Google Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_path)

def create_transcode_job(input_uri, output_uri, project_id, location="us-central1"):
    """Crée un job de transcodage avec Google Cloud Transcode."""
    from google.cloud import video_transcoder_v1
    client = video_transcoder_v1.TranscoderServiceClient()
    parent = f"projects/{project_id}/locations/{location}"
    
    job_config = {
        "input_uri": input_uri,
        "output_uri": output_uri,
        "elementary_streams": [
            {
                "key": "video-stream0",
                "video_stream": {
                    "codec": "h264",
                    "bitrate_bps": 2500000,
                    "frame_rate": 30,
                    "height_pixels": 720,
                    "width_pixels": 1280,
                }
            },
            {
                "key": "audio-stream0",
                "audio_stream": {
                    "codec": "aac",
                    "bitrate_bps": 64000,
                    "sample_rate_hertz": 48000,
                    "channel_count": 2,
                }
            }
        ],
        "mux_streams": [
            {
                "key": "sd",
                "container": "mp4",
                "elementary_streams": ["video-stream0", "audio-stream0"],
            }
        ]
    }
    
    response = client.create_job(
        request={
            "parent": parent,
            "job": job_config,
            "job_id": f"job-{int(time.time())}"
        }
    )
    return response.name

def get_job_status(job_name):
    """Récupère l'état d'un job de transcodage."""
    from google.cloud import video_transcoder_v1
    client = video_transcoder_v1.TranscoderServiceClient()
    response = client.get_job(name=job_name)
    return response.state

def process_video_with_transcode(input_file_path, output_file_path, project_id, bucket_name):
    """Traite une vidéo en utilisant Google Cloud Transcode."""
    try:
        # Upload de la vidéo vers GCS
        input_blob_name = f"input/{os.path.basename(input_file_path)}"
        input_uri = upload_to_gcs(input_file_path, bucket_name, input_blob_name)
        
        # Préparation de l'URI de sortie
        output_blob_name = f"output/{os.path.basename(output_file_path)}"
        output_uri = f"gs://{bucket_name}/{output_blob_name}"
        
        # Création du job de transcodage
        job_name = create_transcode_job(input_uri, output_uri, project_id)
        
        # Attente de la fin du job
        while True:
            status = get_job_status(job_name)
            if status == video_transcoder_v1.Job.ProcessingState.SUCCEEDED:
                break
            elif status == video_transcoder_v1.Job.ProcessingState.FAILED:
                raise Exception("Le job de transcodage a échoué")
            time.sleep(10)  # Attendre 10 secondes avant de vérifier à nouveau
        
        # Téléchargement de la vidéo convertie
        download_from_gcs(bucket_name, output_blob_name, output_file_path)
        
        return True
    except Exception as e:
        print(f"Erreur lors du transcodage : {str(e)}")
        return False 