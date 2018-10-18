<p align="center">
  <img src="https://github.com/posidron/posidron.github.io/raw/master/static/images/orion.png" alt="Logo" />
</p>

<p align="center">
  Monorepo for building and publishing multiple Docker containers as microservices within a single repository.
</p>
<p align="center">
<a href="https://travis-ci.org/MozillaSecurity/orion"><img src="https://travis-ci.org/MozillaSecurity/orion.svg?branch=master"></a>
<a href="https://www.irccloud.com/invite?channel=%23fuzzing&amp;hostname=irc.mozilla.org&amp;port=6697&amp;ssl=1"><img src="https://img.shields.io/badge/IRC-%23fuzzing-1e72ff.svg?style=flat" alt="IRC"></a>
<br/><br/>
FuzzOS<br>
  <a href="https://microbadger.com/images/mozillasecurity/fuzzos"><img src="https://images.microbadger.com/badges/image/mozillasecurity/fuzzos.svg"></a>
</p>

> For spawning a cluster of Docker containers at EC2 or other cloud providers, see the parent project [Laniakea](https://github.com/MozillaSecurity/laniakea/).

## Table of Contents

- [Table of Contents](#table-of-contents)
  - [FuzzOS](#fuzzos)
  - [Pre-Installed Packages](#pre-installed-packages)
  - [Run FuzzOS](#run-fuzzos)
  - [Documentation](#documentation)
  - [Architecture](#architecture)
  - [Build Instructions](#build-instructions)
    - [Usage](#usage)
    - [Testing](#testing)
    - [Login](#login)
  - [Playground](#playground)

This repository is a monorepo of various microservices and home of [FuzzOS](https://github.com/MozillaSecurity/orion/tree/master/base/fuzzos) (a multipurpose base image). CI and CD is performed autonomous with Travis and the Monorepo manager script. A build process gets initiated only if a file of a particular service has been modified and only than that service will be rebuild; other services are not affected from the build service at the time except during cron tasks where all images are rebuild. Each image is either tagged with the latest revision, nightly or latest. For further information take either a look into the Wiki or the corresponding README.md of each microservice.

### FuzzOS

Base: Ubuntu 18.04

### Pre-Installed Packages

- credstash
- fuzzfetch
- fuzzmanager
- afl
- honggfuzz
- llvm
- breakpad
- rr
- grcov
- ripgrep
- nodejs

### Run FuzzOS

```bash
docker search fuzzos
docker run -it --rm mozillasecurity/fuzzos:latest bash -li
```

### Documentation

- https://github.com/mozillasecurity/fuzzos/wiki

### Architecture

[![](docs/assets/overview.png)](https://raw.githubusercontent.com/MozillaSecurity/fuzzos/master/docs/assets/overview.png)

### Build Instructions

#### Usage

```
make help
```

#### Testing

Before a build task is initiated in Travis-CI, each Shellscript and Dockerfile undergo a linting process which may or may not abort each succeeding task.

Locally:

```bash
make lint
```

Each service folder may contain a `tests` folder in which [Container Structure Tests](https://github.com/GoogleContainerTools/container-structure-test) are defined. The Monorepo Manager will run these tests
with the `-test` flag set in Travis-CI after the build process is completed and before deploying the images to the registry.

Locally:

```bash
make test
```

#### Login

```bash
DOCKER_USER=ABC make login
```

### Playground

Play with Docker is a project sponsored by Docker Inc.

- Browse to [PWD](https://labs.play-with-docker.com)
- Login with your Docker account.
- Press `ADD NEW INSTANCE` and enter `docker run --rm -it mozillasecurity/fuzzos`
- You can optionally login via SSH and upload files via drag 'n' drop.

Keep in mind that this is only for testing purpose and to read their motd.
