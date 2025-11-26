from pytubefix import YouTube
import os


def download_video(url, output_path):
    """Download the YouTube video to the given output_path.

    output_path should be a full file path, e.g. jobs/<job_id>/video.mp4.
    """
    yt = YouTube(url)
    stream = yt.streams.filter(progressive=True, file_extension="mp4").first()

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # pytubefix expects a directory + filename
    directory = os.path.dirname(output_path)
    filename = os.path.basename(output_path)

    filepath = stream.download(output_path=directory, filename=filename)
    return filepath
