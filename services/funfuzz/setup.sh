#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -e
set -x
set -o pipefail

# shellcheck source=recipes/linux/common.sh
source "${0%/*}/common.sh"

#### Bootstrap Packages

dpkg --add-architecture i386
sys-update

#### Install recipes

cd "${0%/*}"
./berglas.sh
./credstash.sh
./fluentbit.sh
./fuzzfetch.sh
./fuzzing_tc.sh
./fuzzmanager.sh
./grcov.sh
./gsutil.sh
./htop.sh
./rg.sh
./taskcluster.sh

packages=(
  apt-utils
  binutils
  bzip2
  ca-certificates
  curl
  git
  gpg-agent
  jshon
  less
  libatomic1:i386
  libc6:i386
  libstdc++6:i386
  locales
  nano
  openssh-client
  screen
  software-properties-common
  unzip
  zip
  zstd
)
package_recommends=(
  gdb
  mercurial
  wget
)

sys-embed "${packages[@]}"
# want recommends for these packages
retry apt-get install -y -qq "${package_recommends[@]}"

retry pip3 install python-dateutil
(cd ~worker
 mkdir -p trees
 (cd trees
  mkdir -p funfuzz
  (cd funfuzz
   git init .
   git remote add -t master origin https://github.com/MozillaSecurity/funfuzz
   retry git fetch --depth 1 origin master
   git reset --hard FETCH_HEAD
   retry pip3 install -r requirements.txt
   retry pip3 install -e .
  )
 )
)

#### Base System Configuration

# Generate locales
locale-gen en_US.utf8

# Ensure the machine uses core dumps with PID in the filename
# https://github.com/moby/moby/issues/11740
cat << EOF | tee /etc/sysctl.d/60-fuzzos.conf > /dev/null
# Ensure that we use PIDs with core dumps
kernel.core_uses_pid = 1
# Allow ptrace of any process
kernel.yama.ptrace_scope = 0
EOF

# Ensure we retry metadata requests in case of glitches
# https://github.com/boto/boto/issues/1868
cat << EOF | tee /etc/boto.cfg > /dev/null
[Boto]
metadata_service_num_attempts = 10
EOF

#### Base Environment Configuration

cat << 'EOF' >> /home/worker/.bashrc

# FuzzOS
export PS1='🐳  \[\033[1;36m\]\h \[\033[1;34m\]\W\[\033[0;35m\] \[\033[1;36m\]λ\[\033[0m\] '
EOF

cat << EOF > /home/worker/.hgrc
[ui]
username = funfuzz
merge = internal:merge
ssh = ssh -C -v

[extensions]
mq =
purge =
rebase =
EOF

mkdir -p /home/worker/.local/bin

# Add `cleanup.sh` to let images perform standard cleanup operations.
cp "${0%/*}/cleanup.sh" /home/worker/.local/bin/cleanup.sh

# Add shared `common.sh` to Bash
cp "${0%/*}/common.sh" /home/worker/.local/bin/common.sh
printf "source ~/.local/bin/common.sh\n" >> /home/worker/.bashrc

/home/worker/.local/bin/cleanup.sh

mkdir -p /home/worker/.ssh /root/.ssh
chmod 0700 /home/worker/.ssh /root/.ssh
cat << EOF | tee -a /root/.ssh/config >> /home/worker/.ssh/config
Host *
UseRoaming no
EOF
retry ssh-keyscan github.com | tee -a /root/.ssh/known_hosts >> /home/worker/.ssh/known_hosts

chown -R worker:worker /home/worker
