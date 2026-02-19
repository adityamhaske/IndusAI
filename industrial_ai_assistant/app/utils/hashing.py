import hashlib

def get_hash(content: str) -> str:
    return hashlib.md5(content.encode('utf-8')).hexdigest()
