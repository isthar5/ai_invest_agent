from huggingface_hub import snapshot_download
snapshot_download(repo_id="BAAI/bge-small-zh-v1.5", local_dir="./models/bge-small-zh", local_dir_use_symlinks=False)