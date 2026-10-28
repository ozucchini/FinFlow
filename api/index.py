import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app import app  # noqa: E402  (a Vercel procura o objeto "app")
