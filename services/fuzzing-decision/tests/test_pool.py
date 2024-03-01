# type: ignore
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import slugid
import yaml

from fuzzing_decision.common.pool import PoolConfigLoader as CommonPoolConfigLoader
from fuzzing_decision.common.pool import PoolConfigMap as CommonPoolConfigMap
from fuzzing_decision.common.pool import PoolConfiguration as CommonPoolConfiguration
from fuzzing_decision.common.pool import parse_size
from fuzzing_decision.decision.pool import (
    DOCKER_WORKER_DEVICES,
    PoolConfigLoader,
    PoolConfigMap,
    PoolConfiguration,
)

POOL_FIXTURES = Path(__file__).parent / "fixtures" / "pools"

WST_URL = "https://community-websocktunnel.services.mozilla.com"


@pytest.mark.parametrize(
    "size, divisor, result",
    [
        ("2g", "1g", 2),
        ("2g", "1m", 2048),
        ("2g", 1, 2048 * 1024 * 1024),
        ("128t", "1g", 128 * 1024),
    ],
)
def test_parse_size(size, divisor, result):
    if isinstance(divisor, str):
        divisor = parse_size(divisor)

    assert parse_size(size) / divisor == result


@pytest.mark.parametrize(
    "provider, cpu, cores, ram, metal, gpu, result",
    [
        ("gcp", "x64", 1, 1, False, False, ["base", "metal"]),
        ("gcp", "x64", 2, 1, False, False, ["2-cpus", "more-ram"]),
        ("gcp", "x64", 2, 5, False, False, ["more-ram"]),
        ("gcp", "x64", 1, 1, True, False, ["metal"]),
        ("gcp", "x64", 1, 1, False, True, []),
        ("aws", "arm64", 1, 1, False, False, ["a1"]),
        ("aws", "arm64", 2, 1, False, False, ["a2"]),
        ("aws", "arm64", 12, 32, False, False, []),
        ("aws", "arm64", 1, 1, True, False, []),
        ("aws", "arm64", 1, 1, False, True, ["a4"]),
        # x64 is not present in aws
        ("aws", "x64", 1, 1, False, False, KeyError),
        # invalid provider raises too
        ("dummy", "x64", 1, 1, False, False, KeyError),
    ],
)
def test_machine_filters(
    mock_machines,
    provider,
    cpu,
    ram,
    cores,
    metal,
    gpu,
    result,
):
    if isinstance(result, list):
        assert (
            list(mock_machines.filter(provider, cpu, cores, ram, metal, gpu)) == result
        )
    else:
        with pytest.raises(result):
            list(mock_machines.filter(provider, cpu, cores, ram, metal, gpu))


# Hook & role should be the same across cloud providers
def _get_expected_hook(platform="linux"):
    empty_str_list = []
    empty_str_dict = {}
    return {
        "bindings": empty_str_list,
        "description": (
            "*DO NOT EDIT* - This resource is configured automatically.\n\nFuzzing "
            "resources generated by https://github.com/MozillaSecurity/orion/tree"
            "/master/services/fuzzing-decision"
        ),
        "emailOnError": True,
        "hookGroupId": "project-fuzzing",
        "hookId": f"{platform}-test",
        "kind": "Hook",
        "name": f"{platform}-test",
        "owner": "fuzzing@allizom.org",
        "schedule": ["0 0 12 * * *", "0 0 0 * * *"],
        "task": {
            "created": {"$fromNow": "0 seconds"},
            "deadline": {"$fromNow": "1 hour"},
            "expires": {"$fromNow": "1 week"},
            "extra": empty_str_dict,
            "metadata": {
                "description": (
                    "*DO NOT EDIT* - This resource is configured automatically.\n\n"
                    "Fuzzing resources generated by https://github.com/MozillaSecurity"
                    "/orion/tree/master/services/fuzzing-decision"
                ),
                "name": f"Fuzzing decision {platform}-test",
                "owner": "fuzzing@allizom.org",
                "source": "https://github.com/MozillaSecurity/orion",
            },
            "payload": {
                "artifacts": empty_str_dict,
                "command": ["fuzzing-decision", "test"],
                "env": {"TASKCLUSTER_SECRET": "project/fuzzing/decision"},
                "features": {"taskclusterProxy": True},
                "image": {
                    "namespace": "project.fuzzing.orion.fuzzing-decision.master",
                    "path": "public/fuzzing-decision.tar.zst",
                    "type": "indexed-image",
                },
                "maxRunTime": 3600,
            },
            "priority": "high",
            "provisionerId": "proj-fuzzing",
            "retries": 5,
            "routes": empty_str_list,
            "schedulerId": "-",
            "scopes": [f"assume:hook-id:project-fuzzing/{platform}-test"],
            "tags": empty_str_dict,
            "workerType": "ci-gw",
        },
        "triggerSchema": empty_str_dict,
    }


def _get_expected_role(
    platform="linux",
):
    return {
        "description": (
            "*DO NOT EDIT* - This resource is configured automatically.\n\nFuzzing "
            "resources generated by https://github.com/MozillaSecurity/orion/tree"
            "/master/services/fuzzing-decision"
        ),
        "kind": "Role",
        "roleId": f"hook-id:project-fuzzing/{platform}-test",
        "scopes": [
            "queue:cancel-task:-/*",
            "queue:create-task:highest:proj-fuzzing/ci",
            "queue:create-task:highest:proj-fuzzing/ci-gw",
            f"queue:create-task:highest:proj-fuzzing/{platform}-test",
            "queue:scheduler-id:-",
            "secrets:get:project/fuzzing/decision",
        ],
    }


@pytest.mark.usefixtures("appconfig")
@pytest.mark.parametrize("env", [(None), ({"someKey": "someValue"})])
@pytest.mark.parametrize("platform", ["linux", "windows"])
@pytest.mark.parametrize("demand", [True, False])
def test_aws_resources(
    env,
    mock_clouds,
    mock_machines,
    platform,
    demand,
):
    conf = PoolConfiguration(
        "test",
        {
            "cloud": "aws",
            "command": ["run-fuzzing.sh"],
            "container": "MozillaSecurity/fuzzer:latest",
            "cores_per_task": 2,
            "cpu": "arm64",
            "cycle_time": "12h",
            "demand": demand,
            "disk_size": "120g",
            "gpu": False,
            "imageset": "generic-worker-A",
            "macros": {},
            "max_run_time": "12h",
            "metal": False,
            "minimum_memory_per_core": "1g",
            "name": "Amazing fuzzing pool",
            "parents": [],
            "platform": platform,
            "preprocess": None,
            "schedule_start": "1970-01-01T00:00:00Z",
            "scopes": [],
            "tasks": 3,
            "run_as_admin": False,
            "nested_virtualization": False,
        },
    )
    resources = list(conf.build_resources(mock_clouds, mock_machines, env=env))
    assert len(resources) == 3
    pool, hook, role = resources

    expected = {
        "config": {
            "launchConfigs": [
                {
                    "capacityPerInstance": 1,
                    "launchConfig": {
                        "ImageId": "ami-1234",
                        "InstanceType": "a2",
                        "Placement": {"AvailabilityZone": "us-west-1a"},
                        "SecurityGroupIds": ["sg-A"],
                        "SubnetId": "subnet-XXX",
                    },
                    "region": "us-west-1",
                    "workerConfig": {
                        "genericWorker": {
                            "config": {
                                "anyKey": "anyValue",
                                "deploymentId": "d82eac5c561913ee",
                                "wstAudience": "communitytc",
                                "wstServerURL": (
                                    "https://community-websocktunnel.services.mozilla.com"
                                ),
                            },
                        },
                    },
                }
            ],
            "lifecycle": {
                "queueInactivityTimeout": 7200,
                "registrationTimeout": 900,
                "reregistrationTimeout": 345600,
            },
            "maxCapacity": 6,
            "minCapacity": 0,
        },
        "description": (
            "*DO NOT EDIT* - This resource is configured automatically.\n\nFuzzing "
            "resources generated by https://github.com/MozillaSecurity/orion/tree"
            "/master/services/fuzzing-decision"
        ),
        "emailOnError": True,
        "kind": "WorkerPool",
        "owner": "fuzzing@allizom.org",
        "providerId": "community-tc-workers-aws",
        "workerPoolId": f"proj-fuzzing/{platform}-test",
    }
    if not demand:
        for config in expected["config"]["launchConfigs"]:
            config["launchConfig"]["InstanceMarketOptions"] = {"MarketType": "spot"}

    assert pool.to_json() == expected

    # Update env in valid hook
    valid_hook = _get_expected_hook(platform)
    if env is not None:
        valid_hook["task"]["payload"]["env"].update(env)
    assert hook.to_json() == valid_hook
    assert role.to_json() == _get_expected_role(platform)


@pytest.mark.usefixtures("appconfig")
@pytest.mark.parametrize("demand", [True, False])
@pytest.mark.parametrize("env", [(None), ({"someKey": "someValue"})])
def test_gcp_resources(
    env,
    mock_clouds,
    mock_machines,
    demand,
):
    conf = PoolConfiguration(
        "test",
        {
            "cloud": "gcp",
            "command": ["run-fuzzing.sh"],
            "container": "MozillaSecurity/fuzzer:latest",
            "cores_per_task": 2,
            "cpu": "x64",
            "cycle_time": "12h",
            "demand": demand,
            "disk_size": "120g",
            "gpu": False,
            "imageset": "docker-worker",
            "macros": {},
            "max_run_time": "12h",
            "metal": False,
            "minimum_memory_per_core": "1g",
            "name": "Amazing fuzzing pool",
            "parents": [],
            "platform": "linux",
            "preprocess": None,
            "schedule_start": "1970-01-01T00:00:00Z",
            "scopes": [],
            "tasks": 3,
            "run_as_admin": False,
            "nested_virtualization": False,
        },
    )
    resources = list(conf.build_resources(mock_clouds, mock_machines, env=env))
    assert len(resources) == 3
    pool, hook, role = resources

    expected = {
        "config": {
            "launchConfigs": [
                {
                    "capacityPerInstance": 1,
                    "disks": [
                        {
                            "autoDelete": True,
                            "boot": True,
                            "initializeParams": {
                                "diskSizeGb": 120,
                                "sourceImage": "path/to/image",
                            },
                            "type": "PERSISTENT",
                        }
                    ],
                    "machineType": "zones/us-west1-a/machineTypes/2-cpus",
                    "networkInterfaces": [
                        {"accessConfigs": [{"type": "ONE_TO_ONE_NAT"}]}
                    ],
                    "region": "us-west1",
                    "scheduling": {"onHostMaintenance": "terminate"},
                    "workerConfig": {
                        "genericWorker": {
                            "config": {
                                "deploymentId": "fd62535159568ca7",
                                "wstAudience": "communitytc",
                                "wstServerURL": (
                                    "https://community-websocktunnel.services.mozilla.com"
                                ),
                            },
                        },
                    },
                    "zone": "us-west1-a",
                },
                {
                    "capacityPerInstance": 1,
                    "disks": [
                        {
                            "autoDelete": True,
                            "boot": True,
                            "initializeParams": {
                                "diskSizeGb": 120,
                                "sourceImage": "path/to/image",
                            },
                            "type": "PERSISTENT",
                        }
                    ],
                    "machineType": "zones/us-west1-b/machineTypes/2-cpus",
                    "networkInterfaces": [
                        {"accessConfigs": [{"type": "ONE_TO_ONE_NAT"}]}
                    ],
                    "region": "us-west1",
                    "scheduling": {"onHostMaintenance": "terminate"},
                    "workerConfig": {
                        "genericWorker": {
                            "config": {
                                "deploymentId": "fd62535159568ca7",
                                "wstAudience": "communitytc",
                                "wstServerURL": (
                                    "https://community-websocktunnel.services.mozilla.com"
                                ),
                            },
                        },
                    },
                    "zone": "us-west1-b",
                },
                {
                    "capacityPerInstance": 1,
                    "disks": [
                        {
                            "autoDelete": True,
                            "boot": True,
                            "initializeParams": {
                                "diskSizeGb": 120,
                                "sourceImage": "path/to/image",
                            },
                            "type": "PERSISTENT",
                        }
                    ],
                    "machineType": "zones/us-west1-a/machineTypes/more-ram",
                    "networkInterfaces": [
                        {"accessConfigs": [{"type": "ONE_TO_ONE_NAT"}]}
                    ],
                    "region": "us-west1",
                    "scheduling": {"onHostMaintenance": "terminate"},
                    "workerConfig": {
                        "genericWorker": {
                            "config": {
                                "deploymentId": "fd62535159568ca7",
                                "wstAudience": "communitytc",
                                "wstServerURL": (
                                    "https://community-websocktunnel.services.mozilla.com"
                                ),
                            },
                        },
                    },
                    "zone": "us-west1-a",
                },
            ],
            "lifecycle": {
                "queueInactivityTimeout": 7200,
                "registrationTimeout": 900,
                "reregistrationTimeout": 345600,
            },
            "maxCapacity": 6,
            "minCapacity": 0,
        },
        "description": (
            "*DO NOT EDIT* - This resource is configured automatically.\n\nFuzzing "
            "resources generated by https://github.com/MozillaSecurity/orion/tree"
            "/master/services/fuzzing-decision"
        ),
        "emailOnError": True,
        "kind": "WorkerPool",
        "owner": "fuzzing@allizom.org",
        "providerId": "community-tc-workers-google",
        "workerPoolId": "proj-fuzzing/linux-test",
    }
    if not demand:
        for config in expected["config"]["launchConfigs"]:
            config["scheduling"].update(
                {
                    "provisioningModel": "SPOT",
                    "instanceTerminationAction": "DELETE",
                }
            )
    assert pool.to_json() == expected

    # Update env in valid hook
    valid_hook = _get_expected_hook()
    if env is not None:
        valid_hook["task"]["payload"]["env"].update(env)
    assert hook.to_json() == valid_hook
    assert role.to_json() == _get_expected_role()


@pytest.mark.parametrize("env", [None, {"someKey": "someValue"}])
@pytest.mark.parametrize(
    "scope_caps",
    [
        ([], {}),
        (["docker-worker:capability:privileged"], {"privileged": True}),
        (
            ["docker-worker:capability:privileged"]
            + [
                f"docker-worker:capability:device:{dev}"
                for dev in DOCKER_WORKER_DEVICES
            ],
            {
                "privileged": True,
                "devices": {dev: True for dev in DOCKER_WORKER_DEVICES},
            },
        ),
    ],
)
@pytest.mark.parametrize(
    "platform, run_as_admin",
    [
        ("linux", False),
        ("windows", False),
        ("windows", True),
    ],
)
def test_tasks(
    env,
    scope_caps,
    platform,
    run_as_admin,
    mocker,
):
    mocker.patch.dict(
        "fuzzing_decision.decision.pool.MountArtifactResolver.CACHE",
        {"orion.fuzzer.main": "task-mount-abc"},
    )
    scopes, expected_capabilities = scope_caps
    if run_as_admin:
        scopes.extend(
            (
                "generic-worker:os-group:proj-fuzzing/windows-test/Administrators",
                "generic-worker:run-as-administrator:proj-fuzzing/windows-test",
            )
        )
    conf = PoolConfiguration(
        "test",
        {
            "artifacts": {
                "/some-file.txt": {
                    "type": "file",
                    "url": "project/fuzzing/private/file.txt",
                },
                "/var/log/": {
                    "type": "directory",
                    "url": "project/fuzzing/private/var-log",
                },
            },
            "cloud": "gcp",
            "command": ["run-fuzzing.sh"],
            "container": "MozillaSecurity/fuzzer:latest"
            if platform != "windows"
            else {
                "namespace": "orion.fuzzer.main",
                "type": "indexed-image",
                "path": "public/msys2.tar.bz2",
            },
            "cores_per_task": 1,
            "cpu": "x64",
            "cycle_time": "1h",
            "demand": False,
            "disk_size": "10g",
            "gpu": False,
            "imageset": "anything",
            "macros": {},
            "max_run_time": "30s",
            "metal": False,
            "minimum_memory_per_core": "1g",
            "name": "Amazing fuzzing pool",
            "parents": [],
            "platform": platform,
            "preprocess": None,
            "schedule_start": None,
            "scopes": scopes,
            "tasks": 2,
            "run_as_admin": run_as_admin,
            "nested_virtualization": False,
        },
    )

    task_ids, tasks = zip(*conf.build_tasks("someTaskId", env=env))

    # Check we have 2 valid generated task ids
    assert len(task_ids) == 2
    assert all(map(slugid.decode, task_ids))

    # Check we have 2 valid task definitions
    assert len(tasks) == 2

    def _get_date(value: str):
        assert isinstance(value, str)
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")

    for i, task in enumerate(tasks):
        created = _get_date(task.pop("created"))
        deadline = _get_date(task.pop("deadline"))
        expires = _get_date(task.pop("expires"))
        assert expires >= deadline > created
        expected_env = {
            "TASKCLUSTER_FUZZING_POOL": "test",
            "TASKCLUSTER_SECRET": "project/fuzzing/decision",
        }
        if env is not None:
            expected_env.update(env)

        if platform == "windows":
            # translate to docker-worker style dict
            task["payload"]["artifacts"] = {
                artifact.pop("name"): artifact
                for artifact in task["payload"]["artifacts"]
            }
        assert expires == _get_date(
            task["payload"]["artifacts"]["project/fuzzing/private/logs"].pop("expires")
        )
        assert expires == _get_date(
            task["payload"]["artifacts"]["project/fuzzing/private/file.txt"].pop(
                "expires"
            )
        )
        assert expires == _get_date(
            task["payload"]["artifacts"]["project/fuzzing/private/var-log"].pop(
                "expires"
            )
        )
        assert set(task["scopes"]) == set(
            ["secrets:get:project/fuzzing/decision", *scopes]
        )
        # scopes are already asserted above
        # - read the value for comparison instead of deleting the key, so the object is
        #   printed in full on failure
        scopes = task["scopes"]
        expected = {
            "dependencies": ["someTaskId"],
            "extra": {},
            "metadata": {
                "description": (
                    "*DO NOT EDIT* - This resource is configured automatically.\n\n"
                    "Fuzzing resources generated by https://github.com/MozillaSecurity"
                    "/orion/tree/master/services/fuzzing-decision"
                ),
                "name": f"Fuzzing task {platform}-test - {i+1}/2",
                "owner": "fuzzing@allizom.org",
                "source": "https://github.com/MozillaSecurity/orion",
            },
            "payload": {
                "artifacts": {
                    "project/fuzzing/private/logs": {
                        "path": "logs" if platform == "windows" else "/logs/",
                        "type": "directory",
                    },
                    "project/fuzzing/private/file.txt": {
                        "path": "/some-file.txt",
                        "type": "file",
                    },
                    "project/fuzzing/private/var-log": {
                        "path": "/var/log/",
                        "type": "directory",
                    },
                },
                "env": expected_env,
                "features": {"taskclusterProxy": True},
                "maxRunTime": 30,
            },
            "priority": "high",
            "provisionerId": "proj-fuzzing",
            "retries": 5,
            "routes": [],
            "schedulerId": "-",
            "scopes": scopes,
            "tags": {},
            "taskGroupId": "someTaskId",
            "workerType": f"{platform}-test",
        }

        if platform == "windows":
            expected["dependencies"].append("task-mount-abc")
            expected["payload"]["mounts"] = [
                {
                    "content": {
                        "artifact": "public/msys2.tar.bz2",
                        "taskId": "task-mount-abc",
                    },
                    "directory": ".",
                    "format": "tar.bz2",
                },
            ]
            expected["payload"]["onExitStatus"] = {"retry": [0x40010004]}
            if run_as_admin:
                expected["payload"]["osGroups"] = ["Administrators"]
                expected["payload"]["features"]["runAsAdministrator"] = True
            expected["payload"]["env"]["MSYSTEM"] = "MINGW64"
            # command is unique to windows, since we have no Docker entrypoint
            assert task["payload"]["command"]
            for cmd in task["payload"]["command"][:-1]:
                assert cmd.startswith("set ")
            assert task["payload"]["command"][-1] == "fuzzing-pool-launch"
            expected["payload"]["command"] = task["payload"]["command"]
        else:
            expected["payload"]["image"] = "MozillaSecurity/fuzzer:latest"
        if expected_capabilities:
            expected["payload"]["capabilities"] = expected_capabilities
        assert task == expected


def test_preprocess_tasks():
    conf = PoolConfiguration.from_file(POOL_FIXTURES / "pre-pool.yml")

    task_ids, tasks = zip(*conf.build_tasks("someTaskId"))

    # Check we have 2 valid generated task ids
    assert len(task_ids) == 2
    assert all(map(slugid.decode, task_ids))

    # Check we have 2 valid task definitions
    assert len(tasks) == 2

    def _get_date(value: str):
        assert isinstance(value, str)
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")

    expected = [
        {
            "deps": ["someTaskId"],
            "extra_env": {"TASKCLUSTER_FUZZING_PREPROCESS": "1"},
            "name": "preprocess",
        },
        {"deps": ["someTaskId", task_ids[0]], "extra_env": {}, "name": "1/1"},
    ]
    for task, expect in zip(tasks, expected):
        created = _get_date(task.pop("created"))
        deadline = _get_date(task.pop("deadline"))
        expires = _get_date(task.pop("expires"))
        assert expires >= deadline > created
        expected_env = {
            "TASKCLUSTER_FUZZING_POOL": "pre-pool",
            "TASKCLUSTER_SECRET": "project/fuzzing/decision",
        }
        assert isinstance(expect["extra_env"], dict)
        expected_env.update(expect["extra_env"])

        assert expires == _get_date(
            task["payload"]["artifacts"]["project/fuzzing/private/logs"].pop("expires")
        )
        assert set(task["scopes"]) == {"secrets:get:project/fuzzing/decision"}
        # scopes are already asserted above
        # - read the value for comparison instead of deleting the key, so the object is
        #   printed in full on failure
        scopes = task["scopes"]
        assert task == {
            "dependencies": expect["deps"],
            "extra": {},
            "metadata": {
                "description": (
                    "*DO NOT EDIT* - This resource is configured automatically.\n\n"
                    "Fuzzing resources generated by https://github.com/MozillaSecurity"
                    "/orion/tree/master/services/fuzzing-decision"
                ),
                "name": f"Fuzzing task linux-pre-pool - {expect['name']}",
                "owner": "fuzzing@allizom.org",
                "source": "https://github.com/MozillaSecurity/orion",
            },
            "payload": {
                "artifacts": {
                    "project/fuzzing/private/logs": {
                        "path": "/logs/",
                        "type": "directory",
                    }
                },
                "env": expected_env,
                "features": {"taskclusterProxy": True},
                "image": "MozillaSecurity/fuzzer:latest",
                "maxRunTime": 3600,
            },
            "priority": "high",
            "provisionerId": "proj-fuzzing",
            "retries": 5,
            "routes": [],
            "schedulerId": "-",
            "scopes": scopes,
            "tags": {},
            "taskGroupId": "someTaskId",
            "workerType": "linux-pre-pool",
        }


@pytest.mark.parametrize("pool_path", POOL_FIXTURES.glob("pool*.yml"))
def test_flatten(pool_path):
    class PoolConfigNoFlatten(CommonPoolConfiguration):
        def _flatten(self, _):
            pass

    pool = CommonPoolConfiguration.from_file(pool_path)
    expect_path = pool_path.with_name(pool_path.name.replace("pool", "expect"))
    expect = PoolConfigNoFlatten.from_file(expect_path)
    assert pool.cloud == expect.cloud
    assert pool.command == expect.command
    assert pool.container == expect.container
    assert pool.cores_per_task == expect.cores_per_task
    assert pool.cpu == expect.cpu
    assert pool.cycle_time == expect.cycle_time
    assert pool.demand == expect.demand
    assert pool.disk_size == expect.disk_size
    assert pool.gpu == expect.gpu
    assert pool.imageset == expect.imageset
    assert pool.macros == expect.macros
    assert pool.max_run_time == expect.max_run_time
    assert pool.metal == expect.metal
    assert pool.minimum_memory_per_core == expect.minimum_memory_per_core
    assert pool.name == expect.name
    assert pool.parents == expect.parents
    assert pool.platform == expect.platform
    assert pool.preprocess == expect.preprocess
    assert pool.schedule_start == expect.schedule_start
    assert set(pool.scopes) == set(expect.scopes)
    assert pool.tasks == expect.tasks
    assert pool.nested_virtualization == expect.nested_virtualization


def test_pool_map():
    class PoolConfigNoFlatten(CommonPoolConfiguration):
        def _flatten(self, _):
            pass

    cfg_map = CommonPoolConfigMap.from_file(POOL_FIXTURES / "map1.yml")
    expect = PoolConfigNoFlatten.from_file(POOL_FIXTURES / "expect1.yml")
    assert cfg_map.apply_to == ["pool1"]
    assert cfg_map.cloud == expect.cloud
    assert cfg_map.command is None
    assert cfg_map.container is None
    assert cfg_map.cores_per_task == expect.cores_per_task
    assert cfg_map.cpu == expect.cpu
    assert cfg_map.cycle_time == expect.cycle_time
    assert cfg_map.demand == expect.demand
    assert cfg_map.disk_size == expect.disk_size
    assert cfg_map.gpu == expect.gpu
    assert cfg_map.imageset == expect.imageset
    assert cfg_map.macros == {}
    assert cfg_map.max_run_time is None
    assert cfg_map.metal == expect.metal
    assert cfg_map.minimum_memory_per_core == expect.minimum_memory_per_core
    assert cfg_map.name == "mixed"
    assert cfg_map.platform == expect.platform
    assert cfg_map.preprocess is None
    assert cfg_map.schedule_start == expect.schedule_start
    assert set(cfg_map.scopes) == set()
    assert cfg_map.tasks is None
    assert cfg_map.nested_virtualization == expect.nested_virtualization

    pools = list(cfg_map.iterpools())
    assert len(pools) == 1
    pool = pools[0]
    assert isinstance(pool, CommonPoolConfiguration)
    assert pool.cloud == expect.cloud
    assert pool.command == expect.command
    assert pool.container == expect.container
    assert pool.cores_per_task == expect.cores_per_task
    assert pool.cpu == expect.cpu
    assert pool.cycle_time == expect.cycle_time
    assert pool.demand == expect.demand
    assert pool.disk_size == expect.disk_size
    assert pool.gpu == expect.gpu
    assert pool.imageset == expect.imageset
    assert pool.macros == expect.macros
    assert pool.max_run_time == expect.max_run_time
    assert pool.metal == expect.metal
    assert pool.minimum_memory_per_core == expect.minimum_memory_per_core
    assert pool.name == f"{expect.name}"
    assert pool.parents == ["pool1"]
    assert pool.platform == expect.platform
    assert pool.preprocess == expect.preprocess
    assert pool.schedule_start == expect.schedule_start
    assert set(pool.scopes) == set(expect.scopes)
    assert pool.tasks == expect.tasks
    assert pool.nested_virtualization == expect.nested_virtualization


def test_pool_map_admin(mocker):
    mocker.patch.dict(
        "fuzzing_decision.decision.pool.MountArtifactResolver.CACHE",
        {"orion.fuzzer.main": "task-mount-abc"},
    )

    cfg_map = PoolConfigMap.from_file(POOL_FIXTURES / "map2.yml")
    cfg_map.run_as_admin = True
    with (POOL_FIXTURES / "expect-task-map2.yml").open() as expect_fd:
        expect = yaml.safe_load(expect_fd)
    _task_ids, tasks = zip(*cfg_map.build_tasks("someTaskId"))
    assert len(tasks) == 2
    task = tasks[0]
    # remove timestamps. these are tested elsewhere
    task.pop("created")
    task.pop("deadline")
    task.pop("expires")
    task["metadata"].pop("description")
    for artifact in task["payload"]["artifacts"]:
        artifact.pop("expires")
    # ensure lists are comparable
    task["dependencies"] = sorted(task["dependencies"])
    expect["dependencies"] = sorted(expect["dependencies"])
    task["scopes"] = sorted(task["scopes"])
    expect["scopes"] = sorted(expect["scopes"])
    assert task == expect


def test_pool_map_disabled(mocker):
    """A pool map which includes a disabled pool does not generate any tasks"""
    mocker.patch.dict(
        "fuzzing_decision.decision.pool.MountArtifactResolver.CACHE",
        {"orion.fuzzer.main": "task-mount-abc"},
    )

    cfg_map = PoolConfigMap.from_file(POOL_FIXTURES / "map3.yml")
    cfg_map.run_as_admin = True
    tasks = list(cfg_map.build_tasks("someTaskId"))
    assert not tasks


@pytest.mark.parametrize(
    "loader, config_cls, map_cls",
    [
        (CommonPoolConfigLoader, CommonPoolConfiguration, CommonPoolConfigMap),
        (PoolConfigLoader, PoolConfiguration, PoolConfigMap),
    ],
)
def test_pool_loader(
    loader,
    config_cls,
    map_cls,
):
    obj = loader.from_file(POOL_FIXTURES / "load-cfg.yml")
    assert isinstance(obj, config_cls)
    obj = loader.from_file(POOL_FIXTURES / "load-map.yml")
    assert isinstance(obj, map_cls)


def test_cycle_crons():
    conf = CommonPoolConfiguration(
        "test",
        {
            "cloud": "gcp",
            "command": ["run-fuzzing.sh"],
            "container": "MozillaSecurity/fuzzer:latest",
            "cores_per_task": 1,
            "cpu": "x64",
            "cycle_time": "6h",
            "demand": False,
            "disk_size": "10g",
            "gpu": False,
            "imageset": "anything",
            "macros": {},
            "max_run_time": "6h",
            "metal": False,
            "minimum_memory_per_core": "1g",
            "name": "Amazing fuzzing pool",
            "parents": [],
            "platform": "linux",
            "preprocess": None,
            "schedule_start": "1970-01-01T00:00:00Z",
            "scopes": [],
            "tasks": 2,
            "run_as_admin": False,
            "nested_virtualization": False,
        },
    )

    # cycle time 6h
    assert list(conf.cycle_crons()) == [
        "0 0 6 * * *",
        "0 0 12 * * *",
        "0 0 18 * * *",
        "0 0 0 * * *",
    ]

    # cycle time 3.5 days
    conf.cycle_time = int(3600 * 24 * 3.5)
    assert list(conf.cycle_crons()) == [
        "0 0 12 * * 0",
        "0 0 0 * * 4",
    ]

    # cycle time 17h
    conf.cycle_time = 3600 * 17
    crons = list(conf.cycle_crons())
    assert len(crons) == (365 * 24 // 17) + 1
    assert crons[:4] == ["0 0 17 1 1 *", "0 0 10 2 1 *", "0 0 3 3 1 *", "0 0 20 3 1 *"]

    # cycle time 48h
    conf.cycle_time = 3600 * 48
    crons = list(conf.cycle_crons())
    assert len(crons) == (365 * 24 // 48) + 1
    assert crons[:4] == ["0 0 0 3 1 *", "0 0 0 5 1 *", "0 0 0 7 1 *", "0 0 0 9 1 *"]

    # cycle time 72h
    conf.cycle_time = 3600 * 72
    crons = list(conf.cycle_crons())
    assert len(crons) == (365 * 24 // 72) + 1
    assert crons[:4] == ["0 0 0 4 1 *", "0 0 0 7 1 *", "0 0 0 10 1 *", "0 0 0 13 1 *"]

    # cycle time 17d
    conf.cycle_time = 3600 * 24 * 17
    crons = list(conf.cycle_crons())
    assert len(crons) == (365 // 17) + 1
    assert crons[:4] == ["0 0 0 18 1 *", "0 0 0 4 2 *", "0 0 0 21 2 *", "0 0 0 10 3 *"]

    # using schedule_start should be the same as using datetime.now()
    conf.schedule_start = None
    conf.cycle_time = 3600 * 12
    start = datetime.now(timezone.utc)
    calc_none = list(conf.cycle_crons())
    fin = datetime.now(timezone.utc)
    for offset in range(int((fin - start).total_seconds()) + 1):
        conf.schedule_start = start + timedelta(seconds=offset)
        if calc_none == list(conf.cycle_crons()):
            break
    else:
        assert calc_none == list(conf.cycle_crons())


def test_required():
    CommonPoolConfiguration("test", {"name": "test pool"}, _flattened=set())
    with pytest.raises(AssertionError):
        CommonPoolConfiguration("test", {}, _flattened=set())


def test_aws_nested_virt(
    mock_clouds,
    mock_machines,
):
    pool = PoolConfiguration.from_file(POOL_FIXTURES / "pool1.yml")
    pool.cloud = "aws"
    pool.nested_virtualization = True
    with pytest.raises(AssertionError):
        list(pool.build_resources(mock_clouds, mock_machines))


def test_gcp_nested_virt(
    mock_clouds,
    mock_machines,
):
    cfg = PoolConfiguration.from_file(POOL_FIXTURES / "pool4.yml")
    cfg.cloud = "gcp"
    cfg.nested_virtualization = True
    cfg.imageset = "generic-worker-A"
    cfg.cores_per_task = 1
    cfg.metal = False
    cfg.minimum_memory_per_core = 1
    pool_obj, _hook, _role = cfg.build_resources(mock_clouds, mock_machines)
    configs = pool_obj.to_json()["config"]["launchConfigs"]
    assert configs
    for launch_cfg in configs:
        assert "advancedMachineFeatures" in launch_cfg
        assert "enableNestedVirtualization" in launch_cfg["advancedMachineFeatures"]
        assert launch_cfg["advancedMachineFeatures"]["enableNestedVirtualization"]
