#!/usr/bin/env bash
# ==================================================
#       RBWR OVERLAY LINUX EXECUTABLE COMPILER (NUITKA)
# ==================================================
set -e

echo "=================================================="
echo "      RBWR OVERLAY LINUX COMPILER (NUITKA)"
echo "=================================================="
echo ""

# Step 1: Ensure dependencies
echo "[1/3] Ensuring required packages and virtualenv..."
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    echo "[INFO] Local virtual environment [venv] detected. Activating..."
    source venv/bin/activate
fi

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install nuitka

# Step 2: Generate default custom icon
echo ""
echo "[2/3] Generating default custom icons..."
python3 -c "import rbwr_overlay; rbwr_overlay.generate_default_icon()"

# Extract version
CURRENT_VERSION=$(python3 - << 'EOF'
with open('rbwr_overlay.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('__version__'):
            print(line.split('=')[1].strip().strip('\'"'))
            break
EOF
)
echo "Current version detected: ${CURRENT_VERSION}"

# Step 3: Compile with Nuitka
echo ""
echo "[3/3] Compiling standalone Linux executable..."
CORES=$(nproc 2>/dev/null || echo 4)

python3 -m nuitka \
    --standalone \
    --onefile \
    --enable-plugin=tk-inter \
    --linux-icon=icon.png \
    --output-filename="RBWR_APRM_Calculator_linux_x86_64_v${CURRENT_VERSION}" \
    --jobs="${CORES}" \
    rbwr_overlay.py

chmod +x "RBWR_APRM_Calculator_linux_x86_64_v${CURRENT_VERSION}"
cp "RBWR_APRM_Calculator_linux_x86_64_v${CURRENT_VERSION}" "RBWR_APRM_Calculator"

echo ""
echo "=================================================="
echo "COMPILATION COMPLETED SUCCESSFULLY!"
echo "Binary created: RBWR_APRM_Calculator_linux_x86_64_v${CURRENT_VERSION}"
echo "=================================================="
