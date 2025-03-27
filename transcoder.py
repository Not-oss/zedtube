import os
import time
from google.cloud import storage
from google.cloud import video_transcoder_v1

def upload_to_gcs(local_file_path, bucket_name, destination_blob_name):
    """Upload a file to Google Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(local_file_path)
    return f"gs://{bucket_name}/{destination_blob_name}"

def download_from_gcs(bucket_name, source_blob_name, destination_file_path):
    """Download a file from Google Cloud Storage."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_path)

def create_transcode_job(input_uri, output_uri, project_id, location="us-central1"):
    """Create a transcoding job with Google Cloud Transcode."""
    client = video_transcoder_v1.TranscoderServiceClient()
    parent = f"projects/{project_id}/locations/{location}"
    
    job_config = {
        "input_uri": input_uri,
        "output_uri": output_uri,
        "job_config": {
            "elementary_streams": [
                {
                    "key": "video-stream0",
                    "video_stream": {
                        "codec": "h264",
                        "bitrate_bps": 2_500_000,
                        "frame_rate": 30,
                        "height_pixels": 720,
                        "width_pixels": 1280,
                    }
                },
                {
                    "key": "audio-stream0",
                    "audio_stream": {
                        "codec": "aac",
                        "bitrate_bps": 64_000,
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
    }
    
    job_name = f"job-{int(time.time())}"
    
    response = client.create_job(
        request={
            "parent": parent,
            "job": job_config,
            "job_id": job_name
        }
    )
    return response.name

def get_job_status(job_name, project_id, location="us-central1"):
    """Retrieve the status of a transcoding job."""
    client = video_transcoder_v1.TranscoderServiceClient()
    parent = f"projects/{project_id}/locations/{location}"
    try:
        job = client.get_job(name=f"{parent}/jobs/{job_name}")
        return job.state
    except Exception as e:
        print(f"Error getting job status: {e}")
        return None

def process_video_with_transcode(input_file_path, output_file_path, project_id, bucket_name, location="us-central1"):
    """Process a video using Google Cloud Transcode."""
    try:
        # Ensure input file exists
        if not os.path.exists(input_file_path):
            raise FileNotFoundError(f"Input file not found: {input_file_path}")

        # Upload the input video to GCS
        input_blob_name = f"input/{os.path.basename(input_file_path)}"
        input_uri = upload_to_gcs(input_file_path, bucket_name, input_blob_name)
        
        # Prepare output URI
        output_blob_name = f"output/{os.path.basename(output_file_path)}"
        output_uri = f"gs://{bucket_name}/{output_blob_name}"
        
        # Create transcoding job
        job_name = os.path.basename(job_name) if 'job_name' in locals() else f"job-{int(time.time())}"
        create_job_response = create_transcode_job(input_uri, output_uri, project_id, location)
        
        # Wait for job completion
        max_attempts = 30  # 5 minutes max wait (10s * 30)
        attempts = 0
        while attempts < max_attempts:
            status = get_job_status(job_name, project_id, location)
            
            if status == video_transcoder_v1.Job.ProcessingState.SUCCEEDED:
                # Download converted video
                download_from_gcs(bucket_name, output_blob_name, output_file_path)
                return True
            
            if status == video_transcoder_v1.Job.ProcessingState.FAILED:
                raise Exception("Transcoding job failed")
            
            time.sleep(10)
            attempts += 1
        
        raise Exception("Transcoding job timed out")
    
    except Exception as e:
        print(f"Error during transcoding: {str(e)}")
        return False