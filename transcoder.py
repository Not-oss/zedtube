import os
import time
import ffmpeg
from google.cloud import storage
from google.cloud.video.transcoder_v1 import TranscoderServiceClient
from google.cloud.video.transcoder_v1 import Job

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

def get_video_info(file_path):
    """Get video information using ffmpeg."""
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
        print(f"Error getting video info: {e}")
        # Valeurs par défaut si l'analyse échoue
        return {
            'width': 1920,
            'height': 1080,
            'fps': 30,
            'bitrate': 2500000,
            'audio_bitrate': 64000,
            'audio_channels': 2,
            'audio_sample_rate': 48000
        }

def create_transcode_job(input_uri, output_uri, project_id, video_info, location="us-central1"):
    """Create a transcoding job with Google Cloud Transcode."""
    client = TranscoderServiceClient()
    parent = f"projects/{project_id}/locations/{location}"
    
    job_config = {
        "input_uri": input_uri,
        "output_uri": output_uri,
        "elementary_streams": [
            {
                "key": "video-stream0",
                "video_stream": {
                    "codec": "h264",
                    "bitrate_bps": video_info['bitrate'],
                    "frame_rate": video_info['fps'],
                    "height_pixels": video_info['height'],
                    "width_pixels": video_info['width'],
                }
            },
            {
                "key": "audio-stream0",
                "audio_stream": {
                    "codec": "aac",
                    "bitrate_bps": video_info['audio_bitrate'],
                    "sample_rate_hertz": video_info['audio_sample_rate'],
                    "channel_count": video_info['audio_channels'],
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
    client = TranscoderServiceClient()
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

        # Get video information
        video_info = get_video_info(input_file_path)
        print(f"Video info: {video_info}")

        # Upload the input video to GCS
        input_blob_name = f"input/{os.path.basename(input_file_path)}"
        input_uri = upload_to_gcs(input_file_path, bucket_name, input_blob_name)
        
        # Prepare output URI
        output_blob_name = f"output/{os.path.basename(output_file_path)}"
        output_uri = f"gs://{bucket_name}/{output_blob_name}"
        
        # Create transcoding job with original video info
        job_name = os.path.basename(job_name) if 'job_name' in locals() else f"job-{int(time.time())}"
        create_job_response = create_transcode_job(input_uri, output_uri, project_id, video_info, location)
        
        # Wait for job completion
        max_attempts = 30  # 5 minutes max wait (10s * 30)
        attempts = 0
        while attempts < max_attempts:
            status = get_job_status(job_name, project_id, location)
            
            if status == Job.ProcessingState.SUCCEEDED:
                # Download converted video
                download_from_gcs(bucket_name, output_blob_name, output_file_path)
                return True
            
            if status == Job.ProcessingState.FAILED:
                raise Exception("Transcoding job failed")
            
            time.sleep(10)
            attempts += 1
        
        raise Exception("Transcoding job timed out")
    
    except Exception as e:
        print(f"Error during transcoding: {str(e)}")
        return False