# Filename: setup.ps1

# Exit immediately on errors
$ErrorActionPreference = "Stop"

$ENV_NAME = "superpixel_labeling"
$VENV_DIR = ".venv"

# --- Check if Python is installed ---
try {
    $pythonVersionOutput = & python --version 2>&1
} catch {
    Write-Host "Error: Python is not installed or not found in PATH."
    Write-Host "Please install Python 3.12 and try again."
    exit 1
}

# --- Extract Python version number ---
if ($pythonVersionOutput -match 'Python (\d+)\.(\d+)') {
    $major = [int]$matches[1]
    $minor = [int]$matches[2]
    $PYTHON_VERSION = "$major.$minor"
} else {
    Write-Host "Could not parse Python version."
    exit 1
}

$REQUIRED_VERSION = "3.12"

# --- Compare Python versions ---
function VersionCompare($v1, $v2) {
    $parts1 = $v1.Split('.')
    $parts2 = $v2.Split('.')
    for ($i = 0; $i -lt [Math]::Max($parts1.Length, $parts2.Length); $i++) {
        $p1 = if ($i -lt $parts1.Length) { [int]$parts1[$i] } else { 0 }
        $p2 = if ($i -lt $parts2.Length) { [int]$parts2[$i] } else { 0 }
        if ($p1 -lt $p2) { return -1 }
        elseif ($p1 -gt $p2) { return 1 }
    }
    return 0
}

if (VersionCompare $PYTHON_VERSION $REQUIRED_VERSION -lt 0) {
    Write-Host "Warning: Detected Python $PYTHON_VERSION. This project is tested with Python $REQUIRED_VERSION."
    Write-Host "    Proceeding anyway, but results may vary."
}

# --- Create virtual environment ---
Write-Host "Creating virtual environment in '$VENV_DIR'..."
python -m venv $VENV_DIR

# --- Activate virtual environment ---
Write-Host "Activating virtual environment..."
$activateScript = Join-Path $VENV_DIR "Scripts\Activate.ps1"
if (-Not (Test-Path $activateScript)) {
    Write-Host "Could not find virtual environment activation script at $activateScript"
    exit 1
}
# Dot-source the activation script to activate virtual env in current session
. $activateScript

# --- Upgrade pip ---
Write-Host "Upgrading pip..."
pip install --upgrade pip

# --- Install dependencies ---
Write-Host "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# --- Register Jupyter kernel ---
Write-Host "Registering Jupyter kernel..."
python -m ipykernel install --user --name $ENV_NAME --display-name "Python ($ENV_NAME)"

# --- Final message ---
Write-Host "Setup complete."
Write-Host "To activate the environment in future, run:"
Write-Host "  .\$VENV_DIR\Scripts\Activate.ps1"
