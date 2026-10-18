#!/bin/bash
# Prepare a fresh Vultr GPU server (x86_64 or ARM64, e.g. GH200) for the CivicLens geolocation agent.
# Runs from /root/work after gpu_run.py has pushed the code, images and the assets database.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
cd /root/work
T0=$(date +%s)
step() { echo "[setup +$(( $(date +%s) - T0 ))s] $*"; }

step "arch $(uname -m), $(nproc) cores, $(free -g | awk '/Mem/ {print $2}') GB RAM"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || step "no NVIDIA driver yet"
apt-get update -qq && apt-get install -y -qq python3-venv python3-pip git curl pciutils >/dev/null

step "installing Ollama (installs the NVIDIA driver too if missing)"
curl -fsSL https://ollama.com/install.sh | sh
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
(ollama pull "${OLLAMA_MODEL:-qwen3.8:27b}" > ollama_pull.log 2>&1; echo "pull exit $?" >> ollama_pull.log) &
PULL=$!

step "python environment"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv/bin/pip install -q duckdb pillow numpy opencv-python-headless huggingface_hub safetensors matplotlib \
  "git+https://github.com/cvg/LightGlue.git" "git+https://github.com/cvg/GeoCalib"
.venv/bin/python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"

step "map data"
mkdir -p data results
curl -sL -o data/Toronto.osm.pbf https://download.bbbike.org/osm/bbbike/Toronto/Toronto.osm.pbf
.venv/bin/python places.py --build

step "warming vision model weights"
.venv/bin/python -c "
import torch; torch.hub.load('gmberton/MegaLoc', 'get_trained_model', trust_repo=True)
from lightglue import ALIKED, LightGlue; ALIKED(); LightGlue(features='aliked')
from geocalib import GeoCalib; GeoCalib()
print('vision weights ready')"

wait $PULL
tail -2 ollama_pull.log
ollama list
step "loading the LLM onto the GPU"
curl -s http://127.0.0.1:11434/api/generate -d "{\"model\":\"${OLLAMA_MODEL:-qwen3.8:27b}\",\"prompt\":\"ok\",\"stream\":false,\"think\":false,\"keep_alive\":\"60m\"}" | head -c 200; echo
ollama ps
step "setup done"
