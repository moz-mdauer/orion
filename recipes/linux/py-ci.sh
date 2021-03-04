#!/bin/sh
#########################################################
#   N.B. this may run under MSYS or Linux, sh or bash!  #
#########################################################

# retry command 10x
# usage: retry COMMAND [ARGS...]
retry () {
  i=0
  while [ $i -lt 9 ]
  do
    if "$@"
    then
      return
    fi
    sleep 30
    i="${i+1}"
  done
  "$@"
}

# get a secret from TC and print the given key from the result object
# usage: get_tc_secret SECRET_NAME RESULT_KEY
get_tc_secret () {
  python <<- EOF
	try:
	  from urllib.request import urlopen
	except ImportError:
	  from urllib2 import urlopen
	import json
	url = "http://taskcluster/secrets/v1/secret/project/fuzzing/$1"
	with urlopen(url) as req:
	  data = json.load(req)
	print(data["secret"]["$2"])
EOF
}

# safely checkout a git commit for CI
# usage: clone [URL] [DEST]
# required env: FETCH_REF (ref to fetch), FETCH_REV (commit to checkout)
# optional env: CLONE_URL (default url), DEST (default dest dir)
clone () {
  url="${1-$CLONE_REPO}"
  path="${2-${DEST-$(basename "$url" .git)}}"
  git init "$path"
  cd "$path" || exit 1
  git remote add origin "$url"
  retry git fetch -q --depth=1 origin "${FETCH_REF}"
  git -c advice.detachedHead=false checkout "${FETCH_REV}"
}

# setup credentials and submit coverage to codecov
# usage: tox_codecov
# required env: CODECOV_SECRET (secret name in TC)
tox_codecov () {
  # setup codecov secret
  set +x
  CODECOV_TOKEN="$(get-tc-secret "${CODECOV_SECRET}" token)"
  export CODECOV_TOKEN
  set -x

  # report to codecov
  retry tox -e codecov
}
