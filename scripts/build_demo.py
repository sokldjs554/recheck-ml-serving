"""Build the TypeScript demo and copy its immutable export for Python hosting."""
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
subprocess.run(["npm", "ci"], cwd=root / "demo", check=True)
subprocess.run(["npm", "run", "build"], cwd=root / "demo", check=True)
destination = root / "web_static"
if destination.exists():
    shutil.rmtree(destination)
shutil.copytree(root / "demo" / "dist", destination)
print("Built demo copied to web_static/")
