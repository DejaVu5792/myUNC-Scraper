# Install both the CLI and all completions
install: install-cli install-completions

# Install the CLI binary globally via uv
install-cli:
    @echo "Installing myunc-scraper CLI..."
    uv tool install . --force
    @echo "CLI installed. You can now use 'myunc-scraper' from anywhere."

# Install bash completions
install-completions-bash:
    @echo "Installing bash completions..."
    mkdir -p ~/.local/share/bash-completion/completions
    cp completions/myunc-scraper.bash ~/.local/share/bash-completion/completions/myunc-scraper
    @echo "Bash completions installed. You may need to restart your shell."

# Install fish completions
install-completions-fish:
    @echo "Installing fish completions..."
    mkdir -p ~/.config/fish/completions
    cp completions/myunc-scraper.fish ~/.config/fish/completions/myunc-scraper.fish
    @echo "Fish completions installed. You may need to restart your shell."

# Install all completions
install-completions: install-completions-bash install-completions-fish

# Generate bash completions
generate-completions-bash:
    mkdir -p completions
    uv run register-python-argcomplete --shell bash myunc-scraper > completions/myunc-scraper.bash
    @echo "Bash completions generated in completions/ directory."

# Generate fish completions
generate-completions-fish:
    mkdir -p completions
    uv run register-python-argcomplete --shell fish myunc-scraper > completions/myunc-scraper.fish
    @echo "Fish completions generated in completions/ directory."

# Generate all completions
generate-completions: generate-completions-bash generate-completions-fish
