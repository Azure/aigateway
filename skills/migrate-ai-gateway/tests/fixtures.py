"""Read-only Azure responses shared by collector tests."""

import copy
from urllib.parse import urlsplit

from core import MigrationError


SOURCE = "/subscriptions/sub/resourceGroups/source-rg/providers/Microsoft.ApiManagement/service/source"
TARGET = "/subscriptions/sub/resourceGroups/target-rg/providers/Microsoft.ApiManagement/aigateways/target"


class Azure:
    def __init__(self, sku="BasicV2"):
        self.source = {"id": SOURCE, "name": "source", "sku": {"name": sku},
                       "properties": {"provisioningState": "Succeeded"}}
        self.gateway = None
        self.calls = []
        self.collections = {}

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[:3] == ["az", "cloud", "show"]:
            return "https://management.azure.com/"
        if argv[:3] == ["az", "group", "show"]:
            return {"id": "/subscriptions/sub/resourceGroups/target-rg"}
        if argv[:2] == ["az", "rest"]:
            assert argv[argv.index("--method") + 1] == "get"
            path = urlsplit(argv[argv.index("--url") + 1]).path
            if path == SOURCE:
                return copy.deepcopy(self.source)
            response = self.collections.get(path, {"value": []})
            if path not in self.collections:
                for collection in self.collections.values():
                    if isinstance(collection, dict) and isinstance(collection.get("value"), list):
                        match = next((item for item in collection["value"] if item.get("id") == path), None)
                        if match is not None:
                            response = {**match, "properties": match.get("properties", {})}
                            break
            if isinstance(response, Exception):
                raise response
            return copy.deepcopy(response)
        if argv[:2] != ["az", "aigateway"]:
            raise AssertionError(argv)
        command = argv[2:]
        if command[0] == "show":
            if self.gateway is None:
                raise MigrationError("No AI Gateway exists at the specified scope and name.",
                                     code="ResourceNotFound")
            return copy.deepcopy(self.gateway)
        if command[1] == "list" or command[:3] == ["network", "private-endpoint-connection", "list"]:
            return []
        if command[:2] in (["identity", "show"], ["network", "show"]):
            return {}
        raise AssertionError(argv)
