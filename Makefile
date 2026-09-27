# Qué va a dónde. Lo usan install.sh (PREFIX=~/.local) y el paquete .deb (PREFIX=/usr).
PREFIX ?= /usr/local
DESTDIR ?=
APP_ID := io.github.notitas.Notitas
VERSION := $(shell python3 -c "import notitas; print(notitas.VERSION)")

LIB := $(DESTDIR)$(PREFIX)/lib/notitas
SHARE := $(DESTDIR)$(PREFIX)/share

.PHONY: all install uninstall test deb deb-local clean

all:
	@true

install:
	install -d $(LIB)/notitas/icons $(DESTDIR)$(PREFIX)/bin
	install -m 644 notitas/*.py $(LIB)/notitas/
	install -m 644 notitas/icons/*.svg $(LIB)/notitas/icons/
	install -m 755 bin/notitas $(LIB)/notitas-launcher
	ln -sf ../lib/notitas/notitas-launcher $(DESTDIR)$(PREFIX)/bin/notitas
	install -Dm 644 data/$(APP_ID).desktop $(SHARE)/applications/$(APP_ID).desktop
	install -Dm 644 data/$(APP_ID).svg $(SHARE)/icons/hicolor/scalable/apps/$(APP_ID).svg
	install -Dm 644 data/$(APP_ID).metainfo.xml $(SHARE)/metainfo/$(APP_ID).metainfo.xml
	install -Dm 644 data/notitas.1 $(SHARE)/man/man1/notitas.1

uninstall:
	rm -rf $(LIB)
	rm -f $(DESTDIR)$(PREFIX)/bin/notitas \
	      $(SHARE)/applications/$(APP_ID).desktop \
	      $(SHARE)/icons/hicolor/scalable/apps/$(APP_ID).svg \
	      $(SHARE)/metainfo/$(APP_ID).metainfo.xml \
	      $(SHARE)/man/man1/notitas.1

test:
	python3 -m unittest discover -s tests -t . -v

# Paquete oficial (necesita debhelper: sudo apt install debhelper). Es lo que usa GitHub Actions.
deb:
	dpkg-buildpackage -us -uc -b
	mkdir -p dist
	mv ../notitas_$(VERSION)_all.deb dist/
	rm -f ../notitas_$(VERSION)_*.buildinfo ../notitas_$(VERSION)_*.changes

# Mismo contenido, armado sin debhelper (sólo dpkg-deb). Para probar en una máquina sin herramientas.
deb-local:
	packaging/build-deb-local.sh

clean:
	rm -rf dist build debian/notitas debian/.debhelper debian/files debian/*.substvars debian/debhelper-build-stamp
	find . -name __pycache__ -prune -exec rm -rf {} +
