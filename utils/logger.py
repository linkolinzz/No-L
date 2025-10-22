import datetime, sys

def log(message: str, tag: str = "monitoring"):
    ts = datetime.datetime.now().isoformat(" ", "seconds")
    print(f"[{tag} {ts}] {message}", file=sys.stderr)
