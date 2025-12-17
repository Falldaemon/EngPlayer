PYTHON ?= python3
MSGFMT ?= msgfmt

prefix ?= /usr/local
bindir ?= $(prefix)/bin
sharedir ?= $(prefix)/share
sysconfdir ?= $(prefix)/etc
applicationsdir ?= $(sharedir)/applications
iconsdir ?= $(sharedir)/icons/hicolor/512x512/apps
metainfodir ?= $(sharedir)/metainfo

USER_HOME = $(HOME)
LOCAL_INSTALL_DIR = $(USER_HOME)/.local/share/engplayer
LOCAL_BIN_DIR = $(USER_HOME)/.local/bin
LOCAL_DESKTOP_DIR = $(USER_HOME)/.local/share/applications
LOCAL_ICON_DIR = $(USER_HOME)/.local/share/icons/hicolor/512x512/apps
LOCAL_SYSTEMD_DIR = $(USER_HOME)/.config/systemd/user
USER_CONFIG_DIR = $(USER_HOME)/.config/EngPlayer
USER_CACHE_DIR = $(USER_HOME)/.cache/EngPlayer

.PHONY: all install install-manual uninstall compile-locales clean

all: compile-locales

compile-locales:
	@echo "Compiling translation files..."
	@for dir in resources/locale/*/; do \
		lang=$$(basename "$$dir"); \
		if [ -f "resources/locale/$$lang/LC_MESSAGES/engplayer.po" ]; then \
			$(MSGFMT) "resources/locale/$$lang/LC_MESSAGES/engplayer.po" -o "resources/locale/$$lang/LC_MESSAGES/engplayer.mo"; \
		fi \
	done

install: all
	@echo "Starting standard system/Flatpak installation..."

	mkdir -p $(DESTDIR)$(sharedir)/engplayer
	mkdir -p $(DESTDIR)$(bindir)
	mkdir -p $(DESTDIR)$(applicationsdir)
	mkdir -p $(DESTDIR)$(iconsdir)
	mkdir -p $(DESTDIR)$(metainfodir)
	mkdir -p $(DESTDIR)$(sysconfdir)/xdg/autostart
	mkdir -p $(DESTDIR)$(sharedir)/licenses/io.github.falldaemon.engplayer

	cp -r . $(DESTDIR)$(sharedir)/engplayer
	rm -rf $(DESTDIR)$(sharedir)/engplayer/.git
	rm -rf $(DESTDIR)$(sharedir)/engplayer/venv
	rm -rf $(DESTDIR)$(sharedir)/engplayer/__pycache__

	install -m 755 engplayer.sh $(DESTDIR)$(bindir)/engplayer
	install -m 755 engplayer-daemon.sh $(DESTDIR)$(bindir)/engplayer-daemon
	install -m 644 io.github.falldaemon.engplayer.desktop.in $(DESTDIR)$(applicationsdir)/io.github.falldaemon.engplayer.desktop
	install -m 644 resources/icons/io.github.falldaemon.engplayer.png $(DESTDIR)$(iconsdir)/
	install -m 644 io.github.falldaemon.engplayer.metainfo.xml $(DESTDIR)$(metainfodir)/
	install -m 644 io.github.falldaemon.engplayer.daemon.desktop $(DESTDIR)$(sysconfdir)/xdg/autostart/io.github.falldaemon.engplayer.desktop
	install -m 644 LICENSE $(DESTDIR)$(sharedir)/licenses/io.github.falldaemon.engplayer/LICENSE

	sed -i "s|Exec=.*|Exec=$(bindir)/engplayer|g" $(DESTDIR)$(applicationsdir)/io.github.falldaemon.engplayer.desktop
	sed -i "s|Icon=.*|Icon=io.github.falldaemon.engplayer|g" $(DESTDIR)$(applicationsdir)/io.github.falldaemon.engplayer.desktop

install-manual: all
	@echo "Starting manual user installation..."
	mkdir -p $(LOCAL_INSTALL_DIR)
	mkdir -p $(LOCAL_BIN_DIR)
	mkdir -p $(LOCAL_DESKTOP_DIR)
	mkdir -p $(LOCAL_ICON_DIR)
	mkdir -p $(LOCAL_SYSTEMD_DIR)
	
	install -m 644 io.github.falldaemon.engplayer.desktop.in $(LOCAL_DESKTOP_DIR)/io.github.falldaemon.engplayer.desktop
	sed -i "s|Exec=.*|Exec=$(LOCAL_INSTALL_DIR)/venv/bin/python3 $(LOCAL_INSTALL_DIR)/main.py|g" $(LOCAL_DESKTOP_DIR)/io.github.falldaemon.engplayer.desktop
	sed -i "s|Icon=.*|Icon=io.github.falldaemon.engplayer|g" $(LOCAL_DESKTOP_DIR)/io.github.falldaemon.engplayer.desktop
	cp -r . $(LOCAL_INSTALL_DIR)/
	$(PYTHON) -m venv $(LOCAL_INSTALL_DIR)/venv
	$(LOCAL_INSTALL_DIR)/venv/bin/pip install --upgrade pip wheel
	$(LOCAL_INSTALL_DIR)/venv/bin/pip install -r requirements.txt || $(LOCAL_INSTALL_DIR)/venv/bin/pip install requests pygobject mutagen yt-dlp fuzzywuzzy python-Levenshtein wheel guessit protobuf
	install -m 755 engplayer.sh $(LOCAL_BIN_DIR)/engplayer
	sed -i "s|/app/share/engplayer|$(LOCAL_INSTALL_DIR)|g" $(LOCAL_BIN_DIR)/engplayer
	sed -i "s|exec python3|exec $(LOCAL_INSTALL_DIR)/venv/bin/python3|g" $(LOCAL_BIN_DIR)/engplayer
	install -m 644 resources/icons/io.github.falldaemon.engplayer.png $(LOCAL_ICON_DIR)/io.github.falldaemon.engplayer.png
	sed -e "s|@INSTALL_DIR@|$(LOCAL_INSTALL_DIR)|g" io.github.falldaemon.engplayer.recorder.service.in > $(LOCAL_SYSTEMD_DIR)/io.github.falldaemon.engplayer.recorder.service
	systemctl --user daemon-reload
	systemctl --user enable --now io.github.falldaemon.engplayer.recorder.service
	update-desktop-database $(LOCAL_DESKTOP_DIR) || true
	gtk-update-icon-cache -f -t $(LOCAL_ICON_DIR)/../.. || true

	@echo "Installation complete! (Run 'engplayer' to start)"

uninstall:
	@echo "Uninstalling EngPlayer (Manual Install)..."
	systemctl --user stop io.github.falldaemon.engplayer.recorder.service 2>/dev/null || true
	systemctl --user disable io.github.falldaemon.engplayer.recorder.service 2>/dev/null || true

	rm -rf $(LOCAL_INSTALL_DIR)
	rm -f $(LOCAL_BIN_DIR)/engplayer
	rm -f $(LOCAL_DESKTOP_DIR)/io.github.falldaemon.engplayer.desktop
	rm -f $(LOCAL_SYSTEMD_DIR)/io.github.falldaemon.engplayer.recorder.service
	rm -f $(LOCAL_ICON_DIR)/io.github.falldaemon.engplayer.png

	@echo "Cleaning up user data..."
	rm -rf $(USER_CONFIG_DIR)
	rm -rf $(USER_CACHE_DIR)

	systemctl --user daemon-reload
	update-desktop-database $(LOCAL_DESKTOP_DIR) || true
	gtk-update-icon-cache -f -t $(LOCAL_ICON_DIR)/../.. || true
	@echo "Uninstalled successfully."

clean:
	find . -name "*.mo" -type f -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
