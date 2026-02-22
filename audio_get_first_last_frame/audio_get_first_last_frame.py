import subprocess
import sys
import os
import json


def get_first_last_frames(video_path, output_prefix=None):
    """Extract the first and last frames from a video file and save them as images."""
    if not os.path.exists(video_path):
        print(f"Error: Video file '{video_path}' not found")
        return False

    # Generate output filenames if not provided
    if output_prefix is None:
        base_name = os.path.splitext(video_path)[0]
        first_output = f"{base_name}_first_frame.png"
        last_output = f"{base_name}_last_frame.png"
    else:
        first_output = f"{output_prefix}_first_frame.png"
        last_output = f"{output_prefix}_last_frame.png"

    try:
        # Get video duration and frame count using ffprobe
        probe_cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-count_packets',
            '-show_entries', 'stream=nb_read_packets,duration',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(result.stdout)
        
        if not probe_data.get('streams'):
            print("Error: No video stream found")
            return False
            
        duration = float(probe_data['streams'][0].get('duration', 0))
        
        # Extract first frame at timestamp 0
        first_cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vf', 'select=eq(n\\,0)',
            '-vframes', '1',
            '-y',  # Overwrite output file
            first_output
        ]
        
        subprocess.run(first_cmd, capture_output=True, check=True)
        print(f"First frame saved to: {first_output}")
        
        # Extract last frame
        # Seek to near the end and extract the last frame
        last_cmd = [
            'ffmpeg',
            '-sseof', '-1',  # Seek to 1 second before end
            '-i', video_path,
            '-update', '1',
            '-frames:v', '1',
            '-y',
            last_output
        ]
        
        subprocess.run(last_cmd, capture_output=True, check=True)
        print(f"Last frame saved to: {last_output}")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error: ffmpeg/ffprobe command failed: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python audio_get_last_frame.py <video_file> [output_prefix]")
        print("Example: python audio_get_last_frame.py video.mov")
        print("Example: python audio_get_last_frame.py video.mov output")
        sys.exit(1)

    video_file = sys.argv[1]
    output_prefix = sys.argv[2] if len(sys.argv) > 2 else None

    success = get_first_last_frames(video_file, output_prefix)
    sys.exit(0 if success else 1)

