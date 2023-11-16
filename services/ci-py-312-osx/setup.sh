#!/bin/sh
set -e -x

retry () { i=0; while [ "$i" -lt 9 ]; do if "$@"; then return; else sleep 30; fi; i="${i+1}"; done; "$@"; }
retry_curl () { curl -sSL --connect-timeout 25 --fail --retry 5 -w "%{stderr}[downloaded %{url_effective}]\n" "$@"; }

retry brew install --force-bottle openssl@3 python@3.12
# shellcheck disable=SC2016
sed -i '' 's,export PATH=\\",&${HOMEBREW_PREFIX}/opt/python@3.12/libexec/bin:${HOMEBREW_PREFIX}/opt/python@3.12/bin:${HOMEBREW_PREFIX}/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/bin:,' homebrew/Library/Homebrew/cmd/shellenv.sh
PATH="$HOMEBREW_PREFIX/opt/python@3.12/libexec/bin:$HOMEBREW_PREFIX/opt/python@3.12/bin:$HOMEBREW_PREFIX/opt/python@3.12/Frameworks/Python.framework/Versions/3.12/bin:$PATH"

# remove PEP-668 marker
find "$HOMEBREW_PREFIX" -type f -name "EXTERNALLY-MANAGED" -delete

# configure pip
mkdir -p pip
cat << EOF > pip/pip.ini
[global]
disable-pip-version-check = true
no-cache-dir = false

[list]
format = columns

[install]
upgrade-strategy = only-if-needed
progress-bar = off
EOF
export PIP_CONFIG_FILE="$PWD/pip/pip.ini"

# install utils to match linux ci images
retry python -m pip install tox
retry python -m pip install poetry
retry python -m pip install pre-commit
retry_curl https://uploader.codecov.io/latest/macos/codecov -o homebrew/bin/codecov
chmod +x homebrew/bin/codecov

rm -rf homebrew/docs
cp -r orion/services/orion-decision orion-decision
cp orion/scripts/relocate_homebrew homebrew/bin/
python -m pip install ./orion-decision
cp orion/recipes/linux/py-ci.sh .
relocate_homebrew
tar -jcvf homebrew.tar.bz2 homebrew py-ci.sh pip