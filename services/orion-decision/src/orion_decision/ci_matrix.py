# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Build matrix for CI tasks"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from itertools import product
from json import dumps as json_dumps
from json import loads as json_loads
from logging import getLogger
from pathlib import Path
from typing import Any

from jsonschema import validate
from referencing import Registry, Resource
from yaml import safe_load as yaml_load

from . import Taskcluster

LANGUAGES = ["java", "node", "python"]
PLATFORMS = ["linux", "windows", "macos"]
VERSIONS = {
    ("java", "linux"): ["11"],
    ("node", "linux"): ["18", "20"],
    ("python", "linux"): ["3.9", "3.10", "3.11", "3.12", "3.13"],
    ("python", "windows"): ["3.9", "3.10", "3.11", "3.12", "3.13"],
    ("python", "macos"): ["3.9", "3.10", "3.11", "3.12", "3.13"],
}
IMAGES = {
    ("java", "linux", "11"): "ci-java-11",
    ("node", "linux", "18"): "ci-node-18",
    ("node", "linux", "20"): "ci-node-20",
    ("python", "linux", "3.9"): "ci-py-39",
    ("python", "linux", "3.10"): "ci-py-310",
    ("python", "linux", "3.11"): "ci-py-311",
    ("python", "linux", "3.12"): "ci-py-312",
    ("python", "linux", "3.13"): "ci-py-313",
    ("python", "windows", "3.9"): "ci-py-39-win",
    ("python", "windows", "3.10"): "ci-py-310-win",
    ("python", "windows", "3.11"): "ci-py-311-win",
    ("python", "windows", "3.12"): "ci-py-312-win",
    ("python", "windows", "3.13"): "ci-py-313-win",
    ("python", "macos", "3.9"): "ci-py-39-osx",
    ("python", "macos", "3.10"): "ci-py-310-osx",
    ("python", "macos", "3.11"): "ci-py-311-osx",
    ("python", "macos", "3.12"): "ci-py-312-osx",
    ("python", "macos", "3.13"): "ci-py-313-osx",
}
LOG = getLogger(__name__)


def _load_schema_cache() -> Registry:
    resources = []
    for path in (Path(__file__).parent / "schemas").glob("*.yaml"):
        schema = Resource.from_contents(yaml_load(path.read_text()))
        uri = schema.id()
        assert uri is not None
        resources.append((uri, schema))
    return Registry().with_resources(resources)


SCHEMA_CACHE = _load_schema_cache()


def _schema_by_name(name: str):
    for uri in SCHEMA_CACHE:
        schema = SCHEMA_CACHE[uri]
        if schema.contents["title"] == name:
            return schema.contents
    raise RuntimeError(f"Unknown schema name: {name}")  # pragma: no cover


def _validate_schema_by_name(instance: dict[str, str] | str, name: str):
    schema = _schema_by_name(name)
    return validate(instance=instance, schema=schema, registry=SCHEMA_CACHE)


class MatrixJob:
    """Representation of a CI job.

    Attributes:
        env): Environment variables to set for `script`.
        language: The programming language under test (must be in `LANGUAGES`)
        name: The name for this job
        platform: The operating system to run test (must be in `PLATFORMS`)
        require_previous_stage_pass: This job should only run after all jobs
                                     with a lower `stage` have succeeded.
        script: The command to run (single command).
        secrets: Secrets to be fetched when the job is run.
        stage: The CI stage. Stages are scheduled sequentially in ascending order,
               with all jobs in the same stage running in parallel.
        version: Version number of `language` to run (must be in
                 `VERSIONS[(language, platform)]`)
        artifacts: Artifact files/directories defined for this job.
    """

    __slots__ = (
        "env",
        "artifacts",
        "language",
        "name",
        "platform",
        "require_previous_stage_pass",
        "script",
        "secrets",
        "stage",
        "version",
    )

    def __init__(
        self,
        name: str | None,
        language: str,
        version: str,
        platform: str,
        env: dict[str, str],
        script: list[str],
        stage: int = 1,
        previous_pass: bool = False,
    ) -> None:
        """Initialize a MatrixJob.

        Arguments:
            name: The name for this job (or `None` to auto-name based on
                  `language`/`platform`/`version`).
            language: The programming language under test (must be in `LANGUAGES`)
            version: Version number of `language` to run (must be in
                     `VERSIONS[(language, platform)]`)
            platform: The operating system to run test (must be in `PLATFORMS`)
            env: Environment variables to set for `script`.
            script: The command to run (single command).
            stage: The CI stage. Stages are scheduled sequentially in ascending
                   order, with all jobs in the same stage running in parallel.
            previous_pass: This job should only run after all jobs
                           with a lower `stage` have succeeded.
        """
        self.language = language
        self.version = version
        self.platform = platform
        if name is None:
            self.name = f"{language}/{platform}/{version}"
        else:
            self.name = name
        self.env = env
        self.script = script
        self.stage = stage
        self.require_previous_stage_pass = previous_pass
        self.secrets: list[CISecret] = []
        self.artifacts: list[CIArtifact] = []

    @property
    def image(self) -> str:
        """Get the image name to run tests for this `language`/`platform`/`version`.

        Returns:
            Orion service name to run job
        """
        return IMAGES[(self.language, self.platform, self.version)]

    def check(self) -> None:
        """Assert that all attributes are valid."""
        assert isinstance(self.name, str), "`name` must be a string"
        assert self.language in LANGUAGES, f"unknown `language`: {self.language}"
        assert self.platform in PLATFORMS, f"unknown `platform`: {self.platform}"
        assert (
            self.language,
            self.platform,
        ) in VERSIONS, (
            f"no versions for language '{self.language}', platform '{self.platform}'"
        )
        assert self.version in VERSIONS[(self.language, self.platform)], (
            f"unknown version '{self.version}' for language '{self.language}', "
            f"platform '{self.platform}'"
        )
        assert isinstance(self.env, dict), "`env` must be a dict"
        assert all(
            isinstance(key, str) for key in self.env
        ), "all `env` keys must be strings"
        assert all(
            isinstance(value, str) for value in self.env.values()
        ), "all `env` values must be strings"
        assert isinstance(self.script, list), "`script` must be a list"
        assert self.script, "`script` must not be empty"
        assert all(
            isinstance(cmd, str) for cmd in self.script
        ), "`script` must be a list of strings"
        for secret in self.secrets:
            assert isinstance(
                secret, CISecret
            ), "`secrets` must be a list of `CISecret` objects"
        assert (
            isinstance(self.stage, int) and self.stage > 0
        ), "`stage` must be a positive integer"
        assert isinstance(
            self.require_previous_stage_pass, bool
        ), "`require_previous_stage_pass` must be a boolean"
        assert (
            self.language,
            self.platform,
            self.version,
        ) in IMAGES, (
            f"no image available for language '{self.language}', "
            f"platform '{self.platform}', version '{self.version}'"
        )
        assert len(self.artifacts) == len(
            {a.src for a in self.artifacts}
        ), "`src` for all artifacts must be unique"
        assert len(self.artifacts) == len(
            {a.url for a in self.artifacts}
        ), "`url` for all artifacts must be unique"

    @classmethod
    def from_json(cls, data: str) -> MatrixJob:
        """Deserialize and create a MatrixJob from JSON.

        Arguments:
            data: JSON serialized MatrixJob. (`dict` also accepted if `data` is
                  already deserialized).

        Returns:
            Job object.
        """
        if isinstance(data, dict):
            obj = data
        else:
            obj = json_loads(data)
        _validate_schema_by_name(instance=obj, name="MatrixJob")
        result = cls(
            obj["name"],
            obj["language"],
            obj["version"],
            obj["platform"],
            obj["env"],
            obj["script"],
        )
        result.stage = obj["stage"]
        result.require_previous_stage_pass = obj["require_previous_stage_pass"]
        result.secrets.extend(CISecret.from_json(secret) for secret in obj["secrets"])
        result.artifacts.extend(
            CIArtifact.from_json(artifact) for artifact in obj.get("artifacts", [])
        )
        result.check()
        return result

    def __eq__(self, other) -> bool:
        for attr in self.__slots__:
            if attr == "secrets":
                if len(self.secrets) != len(other.secrets):
                    return False
                if not all(secret in other.secrets for secret in self.secrets):
                    return False
            if attr == "artifacts":
                if len(self.artifacts) != len(other.artifacts):
                    return False
                if not all(art in other.artifacts for art in self.artifacts):
                    return False
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True

    def __str__(self) -> str:
        return json_dumps(self.serialize())

    def serialize(self) -> dict[str, str | None]:
        """Return a JSON serializable copy of self.

        Returns:
            JSON serializeable copy of this `MatrixJob`.
        """
        obj = {attr: getattr(self, attr) for attr in self.__slots__}
        obj["secrets"] = [secret.serialize() for secret in self.secrets]
        obj["artifacts"] = [art.serialize() for art in self.artifacts]
        return obj

    def matches(
        self,
        language: str | None = None,
        version: str | None = None,
        platform: str | None = None,
        env: dict[str, str] | None = None,
        script: list[str] | None = None,
    ) -> bool:
        """Check if this object matches all given arguments.

        Arguments:
            language: If not None, check for match on `language` attribute.
            version: If not None, check for match on `version` attribute.
            platform: If not None, check for match on `platform` attribute.
            env: If not None, check that all given `env` values match self.
                 `self.env` may have other keys, only the keys passed in
                 `env` are checked.
            script: If not None, check for match on `script` attribute.

        Returns:
            True if self matches the given arguments.
        """

        if language is not None and self.language != language:
            return False

        if version is not None and self.version != version:
            return False

        if platform is not None and self.platform != platform:
            return False

        if script is not None and self.script != script:
            return False

        if env is not None:
            for var, value in env.items():
                if var not in self.env:
                    return False

                if self.env[var] != value:
                    return False

        return True


class CIArtifact:
    """Representation of a Taskcluster artifact used by CI jobs.

    Attributes:
        type: Type of `src`, either 'file' or 'directory'.
        src: Path in the job environment.
        url: Artifact URL on the task ('public/' prefix is world readable).
    """

    def __init__(self, type_: str, src: str, url: str) -> None:
        """Initialize

        Arguments:
            type: Type of `src`, either 'file' or 'directory'.
            src: Path in the job environment.
            url: Artifact URL on the task ('public/' prefix is world readable).
        """
        self.type = type_
        self.src = src
        self.url = url

    def __str__(self) -> str:
        return json_dumps(self.serialize())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CIArtifact):
            return False
        return (
            self.type == other.type and self.src == other.src and self.url == other.url
        )

    @classmethod
    def from_json(cls, data: dict[str, str]) -> CIArtifact:
        """Deserialize and create a CIArtifact from JSON.

        Arguments:
            data: JSON serialized CIArtifact.

        Returns:
            CIArtifact: Artifact object.
        """
        _validate_schema_by_name(instance=data, name="CIArtifact")
        return cls(data["type"], data["src"], data["url"])

    def serialize(self) -> dict[str, str]:
        """Return a JSON serializable copy of self."""
        return {
            "src": self.src,
            "type": self.type,
            "url": self.url,
        }


class CISecret(ABC):
    """Representation of a Taskcluster secret used by CI jobs.

    The value is never contained in the object, it is only used as a pointer to the
    secret in Taskcluster, and to fetch/return it.

    Attributes:
        secret: Taskcluster namespace where the secret is held.
                eg. `project/fuzzing/secret123`
        key: Sub-key in the Taskcluster secret that contains the value.
             eg. Taskcluster might contain:

                 {
                     "key": "-----BEGIN OPENSSH PRIVATE KEY-----\n..."
                 }

             Then passing `key="key"` will extract the value of the key
             instead of the dict.
    """

    __slots__ = ("secret", "key")

    def __init__(self, secret: str, key: str | None = None) -> None:
        """Initialize CISecret object.

        Arguments:
            secret: Taskcluster namespace where the secret is held.
            key: Sub-key in the Taskcluster secret that contains the value.
        """
        self.secret = secret
        self.key = key

    def __eq__(self, other: object) -> bool:
        if type(self) is not type(other):
            return False
        for cls in type(self).__mro__:
            for attr in getattr(cls, "__slots__", ()):
                if getattr(self, attr) != getattr(other, attr):
                    return False
        return True

    def is_alias(self, other: object) -> bool:
        """True if other aliases self.

        This currently means type is equal and type-specific fields
        (defined in `__slots__`) are exactly the same.
        """
        if type(self) is not type(other):
            return False
        # intentionally only look at self.__slots__, not super().__slots__
        return all(
            getattr(self, attr) == getattr(other, attr) for attr in self.__slots__
        )

    def get_secret_data(self):
        """Fetch the value of the secret from Taskcluster.

        Note: the secret is JSON deserialized.

        Returns:
            str/list/dict/number: Deserialized value referenced in `secret`
                                  (or `secret[key]`).
        """
        result = Taskcluster.get_service("secrets").get(self.secret)
        assert "secret" in result, "Missing secret value"
        if self.key is not None:
            assert self.key in result["secret"], f"Missing secret key: {self.key}"
            return result["secret"][self.key]
        return result["secret"]

    def __str__(self) -> str:
        return json_dumps(self.serialize())

    @abstractmethod
    def serialize(self) -> dict[str, bool | str | None]:
        """Return a JSON serializable copy of self."""

    @staticmethod
    def from_json(data: str) -> CISecret:
        """Deserialize and create a CISecret from JSON.

        Arguments:
            data: JSON serialized CISecret. (`dict` also accepted if `data` is
                  already deserialized).

        Returns:
            CISecret: Secret object.
        """
        if isinstance(data, dict):
            obj = data
        else:
            obj = json_loads(data)  # pragma: no cover
        _validate_schema_by_name(instance=obj, name="CISecret")
        if obj["type"] == "env":
            return CISecretEnv(obj["secret"], obj["name"], key=obj.get("key"))
        if obj["type"] == "file":
            return CISecretFile(
                obj["secret"],
                obj["path"],
                key=obj.get("key"),
                append=obj.get("append", False),
                mask=obj.get("mask"),
            )
        return CISecretKey(
            obj["secret"], hostname=obj.get("hostname"), key=obj.get("key")
        )


class CISecretEnv(CISecret):
    """Representation of a Taskcluster secret used by CI jobs as an env variable.

    Attributes:
        name: name of the environment variable (eg. `TOKEN`)

        (see CISecret for attributes defined there)
    """

    __slots__ = ("name",)

    def __init__(self, secret: str, name: str, key: str | None = None) -> None:
        """Initialize CISecretEnv object.

        Arguments:
            secret: Taskcluster namespace where the secret is held.
            name: name of the environment variable (eg. `TOKEN`)
            key: Sub-key in the Taskcluster secret that contains the value.
        """
        super().__init__(secret, key)
        self.name = name

    def serialize(self) -> dict[str, bool | str | None]:
        """Return a JSON serializable copy of self.

        Returns:
            dict: JSON serializeable copy of this `CISecretEnv`.
        """
        return {
            "type": "env",
            "key": self.key,
            "secret": self.secret,
            "name": self.name,
        }


class CISecretFile(CISecret):
    """Representation of a Taskcluster secret used by CI jobs as a file.

    Attributes:
        path: Path where secret should be written to.

        (see CISecret for attributes defined there)
    """

    __slots__ = ("path", "append", "mask")

    def __init__(
        self,
        secret: str,
        path: str,
        key: str | None = None,
        append: bool = False,
        mask: str | None = None,
    ) -> None:
        """Initialize CISecretFile object.

        Arguments:
            secret: Taskcluster namespace where the secret is held.
            path: Path where secret should be written to.
            key: Sub-key in the Taskcluster secret that contains the value.
            append: Whether the file should be appended to, if it already exists.
            mask: Permission mask to apply after writing file.
        """
        super().__init__(secret, key)
        self.path = path
        self.append = append or False
        self.mask = int(mask, 8) if mask is not None else None

    def serialize(self) -> dict[str, bool | str | None]:
        """Return a JSON serializable copy of self.

        Returns:
            JSON serializeable copy of this `CISecretFile`.
        """
        return {
            "type": "file",
            "key": self.key,
            "secret": self.secret,
            "path": self.path,
            "append": self.append,
            # serialize back to octal string as expected by schema
            "mask": f"{self.mask:o}" if self.mask is not None else None,
        }

    def write(self) -> None:
        """Write the secret to disk.

        If the secret contains a complex type (list/dict), it will be JSON serialized.
        """
        data = self.get_secret_data()
        if not isinstance(data, str):
            data = json_dumps(data)
        dest = Path(self.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("a" if self.append else "w") as secret_fp:
            secret_fp.write(data)
        if self.mask is not None:
            dest.chmod(self.mask)


class CISecretKey(CISecret):
    """Representation of a Taskcluster secret used by CI jobs as an SSH key.

    Attributes:
        hostname: Hostname alias to configure for using this key.

        (see CISecret for attributes defined there)
    """

    __slots__ = ("hostname",)

    def __init__(
        self, secret: str, key: str | None = None, hostname: str | None = None
    ) -> None:
        """Initialize CISecretKey object.

        Arguments:
            secret: Taskcluster namespace where the secret is held.
            key: Sub-key in the Taskcluster secret that contains the value.
            hostname: Hostname alias to configure for using this key.
        """
        super().__init__(secret, key)
        self.hostname = hostname

    def serialize(self) -> dict[str, bool | str | None]:
        """Return a JSON serializable copy of self.

        Returns:
            JSON serializeable copy of this `CISecretKey`.
        """
        return {
            "type": "key",
            "key": self.key,
            "secret": self.secret,
            "hostname": self.hostname,
        }

    def write(self) -> None:
        """Write the key to `~/.ssh`.

        The key is created as `~/.ssh/id_rsa`, unless `hostname` is set, then
        `~/.ssh/id_rsa.{hostname}` is used. In that case the `hostname` alias to
        `github.com` is also created in `~/.ssh/config`.
        """
        (Path.home() / ".ssh").mkdir(exist_ok=True)
        if self.hostname is not None:
            dest = Path.home() / ".ssh" / f"id_rsa.{self.hostname}"
            with (Path.home() / ".ssh" / "config").open("a") as cfg:
                print(f"Host {self.hostname}", file=cfg)
                print("HostName github.com", file=cfg)
                print(f"IdentityFile ~/.ssh/id_rsa.{self.hostname}", file=cfg)
        else:
            dest = Path.home() / ".ssh" / "id_rsa"
        key = self.get_secret_data()
        assert isinstance(key, str), f"key has type {type(key).__name__}, expected str"
        with dest.open("w", newline="\n") as fp:
            fp.write(key)
        dest.chmod(0o400)


class CIMatrix:
    """CI Job Matrix.

    See the jsonschema specification.

    *NB* despite being superficially very similar to Travis syntax,
         the semantics are different!

    Matrix expansion has 3 steps:
     - cartesian product of language/version/platform/env/script
     - exclude jobs using jobs.exclude
     - include jobs using jobs.include

     Attributes:
        jobs: CI jobs to run.
        secrets: Secrets to be fetched when each job is run.
        artifacts: Artifact files/directories defined for all jobs.
    """

    __slots__ = ("jobs", "secrets", "artifacts")

    def __init__(
        self,
        matrix: dict[str, Any],
        branch: str | None,
        event_type: bool | str,
    ) -> None:
        """Initialize a CIMatrix object.

        Arguments:
            matrix: Matrix representation matching the CIMatrix jsonschema.
            branch: Git branch name (for matching `when` expressions)
            event_type: Git event type (for `when` expressions)
        """
        # matrix is language/platform/version
        self.jobs: list[MatrixJob] = []
        self.secrets: list[CISecret] = []
        self.artifacts: list[CIArtifact] = []
        self._parse_matrix(matrix, branch, event_type)

    def _parse_matrix(
        self,
        matrix: dict[str, Any],
        branch: str | None,
        event_type: bool | str,
    ) -> None:
        _validate_schema_by_name(instance=matrix, name="CIMatrix")

        given = set()
        used = set()

        default_language = None
        if "language" in matrix:
            default_language = matrix["language"]
            given.add("language")

        specified_versions = []
        if "version" in matrix:
            # some language versions are specified
            specified_versions.extend(matrix["version"])
            given.add("version")

        if "platform" in matrix:
            specified_platforms = matrix["platform"]
            given.add("platform")
        else:
            specified_platforms = _schema_by_name("CIMatrix")["properties"]["platform"][
                "default"
            ]

        global_env = {}
        specified_envs = []
        env_name = "env"
        if "env" in matrix:
            envs = matrix["env"]
            if isinstance(envs, dict):
                if "global" in envs:
                    global_env.update(envs["global"])
                envs = envs.get("jobs", [])
                env_name = "env.jobs"
            for env in envs:
                specified_envs.append(env.copy())
            if envs:
                given.add(env_name)

        specified_scripts = []
        if "script" in matrix:
            if all(isinstance(cmd, str) for cmd in matrix["script"]):
                specified_scripts.append(matrix["script"].copy())
            else:
                for idx, script in enumerate(matrix["script"]):
                    specified_scripts.append(script.copy())
            given.add("script")

        # cartesian product of everything specified so far
        if default_language is not None and specified_versions and specified_scripts:
            for platform, version, env, script in product(
                specified_platforms,
                specified_versions,
                specified_envs or [{}],
                specified_scripts,
            ):
                local_env = global_env.copy()
                local_env.update(env)
                self.jobs.append(
                    MatrixJob(
                        None, default_language, version, platform, local_env, script
                    )
                )
            LOG.debug("product created %d jobs", len(self.jobs))
            used |= {"language", "version", "platform", "script", env_name}

        if "secrets" in matrix:
            self.secrets.extend(self._parse_secrets(matrix["secrets"]))

        if "artifacts" in matrix:
            self.artifacts.extend(self._parse_artifacts(matrix["artifacts"]))

        if "jobs" in matrix:
            # exclude jobs
            if "exclude" in matrix["jobs"]:
                for exclude in matrix["jobs"]["exclude"]:
                    self.jobs = [job for job in self.jobs if not job.matches(**exclude)]
                    LOG.debug("%d jobs after exclude", len(self.jobs))

            # include jobs
            if "include" in matrix["jobs"]:
                for idx, include in enumerate(matrix["jobs"]["include"]):
                    name = include.get("name")

                    if "when" in include:
                        assert isinstance(event_type, str)
                        if include["when"].get("release") is (event_type != "release"):
                            continue

                        elif include["when"].get("branch") is not None:
                            if (
                                include["when"]["branch"] != branch
                                or event_type != "push"
                            ):
                                continue

                    assert "script" in include or len(specified_scripts) == 1
                    if "script" in include:
                        script = include["script"].copy()
                    else:
                        script = specified_scripts[0]
                        used.add("script")

                    assert "language" in include or default_language is not None
                    if "language" in include:
                        language = include["language"]
                    else:
                        language = default_language
                        used.add("language")

                    assert "platform" in include or len(specified_platforms) == 1
                    if "platform" in include:
                        platform = include["platform"]
                    else:
                        platform = specified_platforms[0]
                        used.add("platform")

                    assert "version" in include or len(specified_versions) == 1
                    if "version" in include:
                        version = include["version"]
                    else:
                        version = specified_versions[0]
                        used.add("version")

                    env = global_env.copy()
                    if "env" in include:
                        env.update(include["env"])

                    job = MatrixJob(
                        name,
                        language,
                        version,
                        platform,
                        env,
                        script,
                    )
                    assert not any(
                        exist.matches(
                            language=job.language,
                            version=job.version,
                            platform=job.platform,
                            env=job.env,
                            script=job.script,
                        )
                        for exist in self.jobs
                    ), f"included job #{idx} already exists"

                    if "secrets" in include:
                        job.secrets.extend(self._parse_secrets(include["secrets"]))

                    if "artifacts" in include:
                        job.artifacts.extend(
                            self._parse_artifacts(include["artifacts"])
                        )

                    if include.get("when", {}).get("all_passed") is not None:
                        job.stage = 2
                        job.require_previous_stage_pass = include["when"]["all_passed"]

                    self.jobs.append(job)

        # check for any unused matrix values and print a warning
        unused = given - used
        if unused:
            missing = {"language", "version", "script"} - given
            if len(unused) > 1:
                keys = "values '" + "', '".join(sorted(unused)) + "were"
            else:
                keys = f"value '{unused.pop()} was"
            LOG.warning(
                "Top-level %s given, but will have no effect without '%s'.",
                keys,
                "', '".join(sorted(missing)),
            )

        artifact_srcs = {a.src for a in self.artifacts}
        artifact_urls = {a.url for a in self.artifacts}

        assert len(self.artifacts) == len(
            artifact_srcs
        ), "`src` for all artifacts must be unique"
        assert len(self.artifacts) == len(
            artifact_urls
        ), "`url` for all artifacts must be unique"

        for job in self.jobs:
            job.check()
            assert not any(
                artifact_srcs & {a.src for a in job.artifacts}
            ), "job artifact src redefines matrix artifact"
            assert not any(
                artifact_urls & {a.url for a in job.artifacts}
            ), "job artifact url redefines matrix artifact"

    def _parse_secrets(self, secrets: str) -> Iterator[CISecret]:
        for secret in secrets:
            result = CISecret.from_json(secret)
            assert not any(result.is_alias(secret) for secret in self.secrets)
            yield result

    def _parse_artifacts(self, artifacts: list[dict[str, str]]) -> Iterator[CIArtifact]:
        for data in artifacts:
            yield CIArtifact.from_json(data)


def _validate_globals() -> None:
    # validate VERSIONS
    valid_image_keys: list[tuple[str, str, str]] = []
    for (language, platform), versions in VERSIONS.items():
        assert language in LANGUAGES, f"unknown language in VERSIONS: {language}"
        assert platform in PLATFORMS, f"unknown platform in VERSIONS: {platform}"
        valid_image_keys.extend((language, platform, version) for version in versions)
    # validate IMAGES
    missing_images = ["/".join(img) for img in set(valid_image_keys) - set(IMAGES)]
    assert not missing_images, (
        "IMAGES: missing images for: " f"[{', '.join(missing_images)}]"
    )
    extra_images = ["/".join(img) for img in set(IMAGES) - set(valid_image_keys)]
    assert not extra_images, (
        "IMAGES: unnecessary images given: " f"[{', '.join(extra_images)}]"
    )


_validate_globals()
del _validate_globals
