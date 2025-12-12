# ==============================================================================
# EngPlayer Installation Script (User-Space)
# ==============================================================================

PYTHON = python3
PIP = pip3
MSGFMT = msgfmt

USER_HOME = $(HOME)
INSTALL_DIR = $(USER_HOME)/.local/share/engplayer
BIN_DIR = $(USER_HOME)/.local/bin
DESKTOP_DIR = $(USER_HOME)/.local/share/applications
SYSTEMD_DIR = $(USER_HOME)/.config/systemd/user
ICON_DIR = $(USER_HOME)/.local/share/icons/hicolor/scalable/apps
LOCALE_DIR = resources/locale
USER_CONFIG_DIR = $(USER_HOME)/.config/EngPlayer
USER_CACHE_DIR = $(USER_HOME)/.cache/EngPlayer

.PHONY: all install uninstall clean compile-locales

all: compile-locales

compile-locales:
	@echo "Compiling translation files..."
	@for lang in tr de fr es it; do \
		mkdir -p $(LOCALE_DIR)/$$lang/LC_MESSAGES; \
		if [ -f $(LOCALE_DIR)/$$lang/LC_MESSAGES/engplayer.po ]; then \
			$(MSGFMT) $(LOCALE_DIR)/$$lang/LC_MESSAGES/engplayer.po -o $(LOCALE_DIR)/$$lang/LC_MESSAGES/engplayer.mo; \
		fi \
	done

install: all
	@echo "Starting installation..."
	mkdir -p $(INSTALL_DIR)
	mkdir -p $(BIN_DIR)
	mkdir -p $(DESKTOP_DIR)
	mkdir -p $(SYSTEMD_DIR)
	mkdir -p $(ICON_DIR)
	
	@echo "Copying source files..."
	cp -r core data_providers playback ui utils resources *.py $(INSTALL_DIR)/
	find $(INSTALL_DIR) -name "__pycache__" -type d -exec rm -rf {} +
	
	@echo "Setting up isolated Python environment..."
	$(PYTHON) -m venv $(INSTALL_DIR)/venv
	
	@echo "Installing dependencies..."
	$(INSTALL_DIR)/venv/bin/pip install --upgrade pip wheel
	if [ -f requirements.txt ]; then \
		$(INSTALL_DIR)/venv/bin/pip install -r requirements.txt; \
	else \
		$(INSTALL_DIR)/venv/bin/pip install requests pygobject mutagen yt-dlp fuzzywuzzy python-Levenshtein wheel; \
	fi
	
	@echo "Creating launcher script..."
	install -m 755 engplayer.sh $(BIN_DIR)/engplayer
	sed -i "1i\# VENV activation added for manual installation.\nINSTALL_DIR_M=\"$(INSTALL_DIR)\"\nVENV_PATH=\"\$$INSTALL_DIR_M/venv\"\n. \"\$$VENV_PATH/bin/activate\"" $(BIN_DIR)/engplayer
	sed -i "s|/app/share/engplayer|$(INSTALL_DIR)|g" $(BIN_DIR)/engplayer
	
	@echo "Installing Desktop & Service files..."
	sed -e "s|@EXEC_PATH@|/usr/bin/env sh -c '$(BIN_DIR)/engplayer'|g" io.github.falldaemon.engplayer.desktop.in > $(DESKTOP_DIR)/io.github.falldaemon.engplayer.desktop
	chmod +x $(DESKTOP_DIR)/io.github.falldaemon.engplayer.desktop
	

	sed -e "s|@INSTALL_DIR@|$(INSTALL_DIR)|g" io.github.falldaemon.engplayer.recorder.service.in > $(SYSTEMD_DIR)/io.github.falldaemon.engplayer.recorder.service
	

	if [ -f resources/icons/io.github.falldaemon.engplayer.png ]; then \
		cp resources/icons/io.github.falldaemon.engplayer.png $(ICON_DIR)/io.github.falldaemon.engplayer.png; \
	fi

	@echo "Registering services and icons..."
	systemctl --user daemon-reload
	systemctl --user enable --now io.github.falldaemon.engplayer.recorder.service
	update-desktop-database $(DESKTOP_DIR) || true
	gtk-update-icon-cache -f -t $(ICON_DIR)/../.. || true
	
	@echo "------------------------------------------------"
	@echo "Installation Complete!"
	@echo "------------------------------------------------"

uninstall:
	@echo "Uninstalling EngPlayer..."
	systemctl --user stop io.github.falldaemon.engplayer.recorder.service || true
	systemctl --user disable io.github.falldaemon.engplayer.recorder.service || true
	
	rm -rf $(INSTALL_DIR)
	rm -f $(BIN_DIR)/engplayer
	rm -f $(DESKTOP_DIR)/io.github.falldaemon.engplayer.desktop
	rm -f $(SYSTEMD_DIR)/io.github.falldaemon.engplayer.recorder.service
	rm -f $(ICON_DIR)/io.github.falldaemon.engplayer.png
	
	@echo "Cleaning up user data..."
	rm -rf $(USER_CONFIG_DIR)
	rm -rf $(USER_CACHE_DIR)
	
	systemctl --user daemon-reload
	update-desktop-database $(DESKTOP_DIR) || true
	gtk-update-icon-cache -f -t $(ICON_DIR)/../.. || true
	@echo "Uninstalled successfully."

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find . -name "*.mo" -type f -delete
