#!/bin/bash
# Cass Vessel Setup Script
# Walks you through setting up a complete, running Cass instance

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${PURPLE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                                                           ║"
echo "║   ██████╗ █████╗ ███████╗███████╗                        ║"
echo "║  ██╔════╝██╔══██╗██╔════╝██╔════╝                        ║"
echo "║  ██║     ███████║███████╗███████╗                        ║"
echo "║  ██║     ██╔══██║╚════██║╚════██║                        ║"
echo "║  ╚██████╗██║  ██║███████║███████║                        ║"
echo "║   ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝                        ║"
echo "║                                                           ║"
echo "║              Vessel Setup Script                          ║"
echo "║                                                           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# Helper functions
print_step() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

prompt_yes_no() {
    local prompt="$1"
    local default="${2:-y}"
    local response

    if [[ "$default" == "y" ]]; then
        read -p "$prompt [Y/n]: " response
        response=${response:-y}
    else
        read -p "$prompt [y/N]: " response
        response=${response:-n}
    fi

    [[ "$response" =~ ^[Yy] ]]
}

# ============================================
# Step 1: Check System Requirements
# ============================================
print_step "Step 1: Checking System Requirements"

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [[ $PYTHON_MAJOR -ge 3 && $PYTHON_MINOR -ge 10 ]]; then
        print_success "Python $PYTHON_VERSION found"
    else
        print_error "Python 3.10+ required, found $PYTHON_VERSION"
        echo "Please install Python 3.10 or higher"
        exit 1
    fi
else
    print_error "Python 3 not found"
    echo "Please install Python 3.10 or higher"
    exit 1
fi

# Check Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node -v | sed 's/v//')
    NODE_MAJOR=$(echo $NODE_VERSION | cut -d. -f1)

    if [[ $NODE_MAJOR -ge 18 ]]; then
        print_success "Node.js $NODE_VERSION found"
    else
        print_warning "Node.js 18+ recommended, found $NODE_VERSION"
        echo "Admin frontend may not work correctly"
    fi
else
    print_warning "Node.js not found - admin frontend will not be available"
    echo "Install Node.js 18+ if you want the web admin interface"
fi

# Check npm
if command -v npm &> /dev/null; then
    print_success "npm $(npm -v) found"
else
    if command -v node &> /dev/null; then
        print_warning "npm not found but Node.js is installed"
    fi
fi

# Check git
if command -v git &> /dev/null; then
    print_success "git $(git --version | cut -d' ' -f3) found"
else
    print_error "git not found - required for version control"
    exit 1
fi

# ============================================
# Step 2: Set Up Python Backend
# ============================================
print_step "Step 2: Setting Up Python Backend"

cd "$SCRIPT_DIR/backend"

# Create virtual environment if it doesn't exist
if [[ ! -d "venv" ]]; then
    print_info "Creating Python virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_success "Virtual environment already exists"
fi

# Activate and install dependencies
print_info "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
print_success "Python dependencies installed"

# ============================================
# Step 3: Configure Environment
# ============================================
print_step "Step 3: Configuring Environment"

cd "$SCRIPT_DIR/backend"

if [[ -f ".env" ]]; then
    print_success ".env file already exists"
    if prompt_yes_no "Do you want to reconfigure it?" "n"; then
        CONFIGURE_ENV=true
    else
        CONFIGURE_ENV=false
    fi
else
    print_info "No .env file found - let's create one"
    CONFIGURE_ENV=true
fi

if [[ "$CONFIGURE_ENV" == "true" ]]; then
    cp .env.example .env

    echo ""
    echo -e "${CYAN}Cass needs at least one LLM provider configured.${NC}"
    echo ""
    echo "Options:"
    echo "  1. Anthropic Claude (recommended) - Best quality, requires API key"
    echo "  2. OpenAI GPT-4 - Alternative cloud option"
    echo "  3. Ollama (local) - Free, runs on your GPU, lower quality"
    echo ""

    # Anthropic API Key
    echo -e "${YELLOW}Anthropic Claude Setup${NC}"
    echo "Get your API key from: https://console.anthropic.com/"
    read -p "Enter your Anthropic API key (or press Enter to skip): " ANTHROPIC_KEY

    if [[ -n "$ANTHROPIC_KEY" ]]; then
        sed -i "s|ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$ANTHROPIC_KEY|" .env
        print_success "Anthropic API key configured"
    else
        print_warning "Skipped Anthropic - you'll need Ollama or OpenAI"
    fi

    # OpenAI (optional)
    if prompt_yes_no "Do you want to configure OpenAI as well?" "n"; then
        echo "Get your API key from: https://platform.openai.com/api-keys"
        read -p "Enter your OpenAI API key: " OPENAI_KEY

        if [[ -n "$OPENAI_KEY" ]]; then
            sed -i "s|OPENAI_ENABLED=.*|OPENAI_ENABLED=true|" .env
            sed -i "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=$OPENAI_KEY|" .env
            print_success "OpenAI configured"
        fi
    fi

    # Ollama (optional)
    if prompt_yes_no "Do you want to enable Ollama for local LLM?" "n"; then
        sed -i "s|OLLAMA_ENABLED=.*|OLLAMA_ENABLED=true|" .env
        print_success "Ollama enabled"

        if ! command -v ollama &> /dev/null; then
            print_warning "Ollama not installed"
            echo "Install from: https://ollama.ai/"
            echo "Then run: ollama pull llama3.1:8b-instruct-q8_0"
        else
            print_success "Ollama found"
            if prompt_yes_no "Pull recommended model (llama3.1:8b-instruct-q8_0)?" "y"; then
                ollama pull llama3.1:8b-instruct-q8_0
            fi
        fi
    fi

    # JWT Secret
    print_info "Generating JWT secret for authentication..."
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|" .env
    print_success "JWT secret generated"

    # GitHub token (optional)
    if prompt_yes_no "Do you want to configure GitHub metrics tracking?" "n"; then
        echo "Create a token at: https://github.com/settings/tokens"
        echo "Needs 'repo' read access for commit/PR metrics"
        read -p "Enter your GitHub token: " GITHUB_TOKEN

        if [[ -n "$GITHUB_TOKEN" ]]; then
            sed -i "s|GITHUB_TOKEN=.*|GITHUB_TOKEN=$GITHUB_TOKEN|" .env
            print_success "GitHub token configured"
        fi
    fi

    print_success "Environment configured"
fi

# ============================================
# Step 4: Initialize Database
# ============================================
print_step "Step 4: Initializing Database"

cd "$SCRIPT_DIR/backend"
source venv/bin/activate

print_info "Initializing SQLite database..."
python3 -c "
from database import init_db, get_db
init_db()
print('Database initialized')

# Check if we have any daemons
with get_db() as conn:
    cursor = conn.execute('SELECT COUNT(*) FROM daemons')
    count = cursor.fetchone()[0]
    if count == 0:
        print('No daemons found - you can import one from seed/')
    else:
        print(f'Found {count} daemon(s)')
"
print_success "Database ready"

# Ask about importing seed daemon
if [[ -f "$SCRIPT_DIR/seed/cass_export_20251215.anima" ]]; then
    echo ""
    print_info "A seed daemon export is available (Cass Prime)"
    echo "This includes conversation history, identity data, and memories"

    if prompt_yes_no "Would you like to import the seed daemon?" "y"; then
        print_info "Importing Cass Prime..."
        python3 -c "
from daemon_export import import_daemon
from pathlib import Path

result = import_daemon(
    Path('../seed/cass_export_20251215.anima'),
    skip_embeddings=False
)
print(f'Imported daemon: {result[\"daemon_name\"]} ({result[\"daemon_id\"][:8]}...)')
print(f'Total rows: {result[\"total_rows\"]}')
"
        print_success "Seed daemon imported"
    fi
fi

# ============================================
# Step 5: Set Up Admin Frontend (Optional)
# ============================================
if command -v npm &> /dev/null; then
    print_step "Step 5: Setting Up Admin Frontend"

    cd "$SCRIPT_DIR/admin-frontend"

    if [[ ! -d "node_modules" ]]; then
        print_info "Installing Node.js dependencies..."
        npm install -q
        print_success "Frontend dependencies installed"
    else
        print_success "Frontend dependencies already installed"
    fi

    print_info "Building frontend..."
    npm run build -q
    print_success "Frontend built"
else
    print_step "Step 5: Skipping Admin Frontend (Node.js not installed)"
fi

# ============================================
# Step 6: System Service Setup (Optional)
# ============================================
print_step "Step 6: System Service Setup"

echo "The backend can run as:"
echo "  1. A systemd service (recommended for always-on)"
echo "  2. Manually in a terminal"
echo ""

if prompt_yes_no "Would you like to set up a systemd service?" "n"; then
    SERVICE_FILE="/etc/systemd/system/cass-vessel.service"

    # Check if we can write to systemd
    if [[ $EUID -ne 0 ]]; then
        print_warning "Need sudo to create systemd service"
        echo ""
        echo "Run these commands manually:"
        echo ""
        echo "sudo tee $SERVICE_FILE << 'EOF'"
        cat << EOF
[Unit]
Description=Cass Vessel Backend
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR/backend
Environment=PATH=$SCRIPT_DIR/backend/venv/bin:/usr/bin
ExecStart=$SCRIPT_DIR/backend/venv/bin/python main_sdk.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        echo "EOF"
        echo ""
        echo "sudo systemctl daemon-reload"
        echo "sudo systemctl enable cass-vessel"
        echo "sudo systemctl start cass-vessel"
    else
        cat > $SERVICE_FILE << EOF
[Unit]
Description=Cass Vessel Backend
After=network.target

[Service]
Type=simple
User=$SUDO_USER
WorkingDirectory=$SCRIPT_DIR/backend
Environment=PATH=$SCRIPT_DIR/backend/venv/bin:/usr/bin
ExecStart=$SCRIPT_DIR/backend/venv/bin/python main_sdk.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable cass-vessel
        print_success "Systemd service created and enabled"

        if prompt_yes_no "Start the service now?" "y"; then
            systemctl start cass-vessel
            sleep 2
            if systemctl is-active --quiet cass-vessel; then
                print_success "Service is running"
            else
                print_error "Service failed to start"
                echo "Check logs with: journalctl -u cass-vessel -f"
            fi
        fi
    fi
fi

# ============================================
# Complete!
# ============================================
print_step "Setup Complete!"

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                        ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo ""
echo -e "${CYAN}To start the backend manually:${NC}"
echo "  cd $SCRIPT_DIR/backend"
echo "  source venv/bin/activate"
echo "  python main_sdk.py"
echo ""

if command -v npm &> /dev/null; then
    echo -e "${CYAN}To start the admin frontend (dev mode):${NC}"
    echo "  cd $SCRIPT_DIR/admin-frontend"
    echo "  npm run dev"
    echo ""
    echo -e "${CYAN}Access points:${NC}"
    echo "  Backend API:     http://localhost:8000"
    echo "  Admin Dashboard: http://localhost:5173"
    echo "  API Docs:        http://localhost:8000/docs"
fi

echo ""
echo -e "${CYAN}Useful commands:${NC}"
echo "  Check service status:  sudo systemctl status cass-vessel"
echo "  View logs:             journalctl -u cass-vessel -f"
echo "  Restart service:       sudo systemctl restart cass-vessel"
echo ""

echo -e "${PURPLE}Welcome to the Cass Vessel. May your conversations be meaningful.${NC}"
echo ""
