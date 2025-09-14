import os
import subprocess
import yaml
import glob
from yt_dlp import YoutubeDL

def load_config(config_path='config.yaml'):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def create_dirs(*dirs):
    for d in dirs:
        os.makedirs(d, exist_ok=True)

def download_videos(config):
    ydl_opts = {
        'format': f"bestvideo[ext=mp4][height<={config['video_download']['resolution']}]+bestaudio[ext=m4a]/mp4",
        'outtmpl': os.path.join(config['video_download']['download_folder'], '%(title).70s.%(ext)s'),
        'noplaylist': True,
        'quiet': False,
        'ignoreerrors': True,
        'no_warnings': True,
    }

    create_dirs(config['video_download']['download_folder'])

    with YoutubeDL(ydl_opts) as ydl:
        for query in config['search_keywords']:
            search_url = f"ytsearch{config['video_download']['max_results_per_query']}:{query}"
            print(f"[INFO] Downloading videos for: {query}")
            ydl.download([search_url])

def extract_frames(config):
    video_dir = config['video_download']['download_folder']
    frame_root = config['frame_extraction']['output_folder']
    interval = config['frame_extraction']['interval_seconds']
    scale_width = config['frame_extraction']['scale_width']
    ffmpeg = config['ffmpeg_path']

    create_dirs(frame_root)

    for video_file in glob.glob(os.path.join(video_dir, '*.mp4')):
        video_name = os.path.splitext(os.path.basename(video_file))[0]
        output_folder = os.path.join(frame_root, video_name)
        create_dirs(output_folder)

        vf_filters = [f"fps=1/{interval}"]
        if scale_width:
            vf_filters.append(f"scale={scale_width}:-1")

        vf_string = ",".join(vf_filters)

        cmd = [
            ffmpeg,
            '-i', video_file,
            '-vf', vf_string,
            '-qscale:v', '2',
            os.path.join(output_folder, 'frame_%04d.jpg')
        ]

        print(f"[INFO] Extracting frames from: {video_name}")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    config = load_config()
    download_videos(config)
    extract_frames(config)
import os
import subprocess
from yt_dlp import YoutubeDL

# Your search terms
search_terms = [
    "mtg paper gameplay",
    "magic the gathering real life match",
    "mtg tournament match",
    "mtg EDH gameplay",
]

# Directory to store videos
DOWNLOAD_DIR = "mtg_videos"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Video options: 1080p max, mp4 format
ydl_opts = {
    'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/mp4',
    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title).70s.%(ext)s'),
    'noplaylist': True,
    'quiet': False,
    'ignoreerrors': True,
    'no_warnings': True,
}

def download_videos_from_search(query):
    with YoutubeDL(ydl_opts) as ydl:
        search_url = f"ytsearch10:{query}"  # fetch top 10 results
        ydl.download([search_url])

# Download videos for each query
for term in search_terms:
    print(f"Searching and downloading: {term}")
    download_videos_from_search(term)
