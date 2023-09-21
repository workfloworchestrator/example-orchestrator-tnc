# Copyright 2019-2023 SURF.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from dataclasses import asdict, dataclass
from functools import singledispatch
from typing import Any, List, Optional

import structlog
from pynetbox import api
from pynetbox.core.endpoint import Endpoint
from pynetbox.core.query import RequestError
from pynetbox.models.dcim import Devices
from pynetbox.models.dcim import Interfaces
from pynetbox.models.dcim import Interfaces as PynetboxInterfaces
from pynetbox.models.ipam import IpAddresses, Prefixes

from utils.singledispatch import single_dispatch_base

logger = structlog.get_logger(__name__)

netbox = api(
    "http://netbox:8080",
    token="e744057d755255a31818bf74df2350c26eeabe54",
)  # fmt: skip


@dataclass
class NetboxPayload:
    id: int  # unique id of object on Netbox endpoint

    # return payload as a dict that is suitable to be used on pynetbox .create() or .updates().
    def dict(self):
        return asdict(self)


@dataclass
class DevicePayload(NetboxPayload):
    # mandatory fields to create Devices object in Netbox:
    site: int
    device_type: int
    device_role: int
    # optional fields:
    name: Optional[str]
    status: Optional[str]
    primary_ip4: Optional[int]
    primary_ip6: Optional[int]


@dataclass
class CableTerminationPayload:
    object_id: int
    object_type: str = "dcim.interface"


@dataclass
class CablePayload(NetboxPayload):
    status: str
    description: Optional[str]
    a_terminations: List[CableTerminationPayload]
    b_terminations: List[CableTerminationPayload]


@dataclass
class AvailablePrefixPayload:
    prefix_length: int
    description: str
    is_pool: Optional[bool] = False


@dataclass
class AvailableIpPayload:
    description: str
    assigned_object_id: int
    assigned_object_type: Optional[str] = "dcim.interface"
    status: Optional[str] = "active"


def get_device(name: str) -> Devices:
    """
    Get device from Netbox identified by name.
    """
    return netbox.dcim.devices.get(name=name)


def get_devices(status: Optional[str] = None) -> List[Devices]:
    """
    Get list of Devices objects from netbox, optionally filtered by status.
    """
    logger.debug("Connecting to Netbox to get list of devices")
    if status:
        node_list = list(netbox.dcim.devices.filter(status=status))
    else:
        node_list = list(netbox.dcim.devices.all())
    logger.debug("Found nodes in Netbox", amount=len(node_list))
    return node_list


# TODO: make this a more generic function
def get_available_router_ports_by_name(router_name: str) -> List[PynetboxInterfaces]:
    """
    get_available_router_ports_by_name fetches a list of available ports from netbox
        when given the name of a router. To be considered available, the port must be:
            1) A 400G interface (any media type)
            2) On the router specified.
            3) Not "occupied" from netbox's perspective.

    Args:
        router_name (str): the router that you need to find an open port from, i.e. "loc1-core".

    Returns:
        List[PynetboxInterfaces]: a list of valid interfaces from netbox.
    """
    valid_ports = list(netbox.dcim.interfaces.filter(device=router_name, occupied=False, speed=400000000))
    logger.debug("Found ports in Netbox", amount=len(valid_ports))
    return valid_ports


def get_interface_by_device_and_name(device: str, name: str) -> Interfaces:
    """
    Get Interfaces object from Netbox identified by device and name.
    """
    return next(netbox.dcim.interfaces.filter(device=device, name=name))


def get_ip_address(address: str) -> IpAddresses:
    """
    Get IpAddresses object from Netbox identified by address.
    """
    return netbox.ipam.ip_addresses.get(address=address)


def get_ip_prefix_by_id(id: int) -> Prefixes:
    """
    Get Prefixes object from Netbox identified by id.
    """
    return netbox.ipam.prefixes.get(id)


def create_available_prefix(parent_id: int, payload: AvailablePrefixPayload) -> Prefixes:
    parent_prefix = get_ip_prefix_by_id(parent_id)
    return parent_prefix.available_prefixes.create(asdict(payload))


def create_available_ip(parent_id: int, payload: AvailableIpPayload) -> IpAddresses:
    parent_prefix = get_ip_prefix_by_id(parent_id)
    return parent_prefix.available_ips.create(asdict(payload))


@singledispatch
def create(payload: NetboxPayload, **kwargs: Any) -> int:
    """Create object described by payload in Netbox (generic function).

    Specific implementations of this generic function will specify the payload types they work on.

    Args:
        payload: Netbox object specific payload.

    Returns:
        The id of the created object in Netbox, raises an exception otherwise.

    Raises:
        TypeError: in case a specific implementation could not be found. The payload it was called for will be
            part of the error message.

    """
    return single_dispatch_base(create, payload)


@singledispatch
def update(payload: NetboxPayload, **kwargs: Any) -> bool:
    """Update object described by payload in Netbox (generic function).

    Specific implementations of this generic function will specify the payload types they work on.

    Args:
        payload: Netbox object specific payload.

    Returns:
        True if the object was updated successfully in Netbox, False otherwise.

    Raises:
        TypeError: in case a specific implementation could not be found. The payload it was called for will be
            part of the error message.

    """
    return single_dispatch_base(update, payload)


@update.register
def _(payload: DevicePayload, **kwargs: Any) -> bool:
    return _update_object(payload, endpoint=netbox.dcim.devices)


@create.register
def _(payload: CablePayload, **kwargs: Any) -> bool:
    return _create_object(payload, endpoint=netbox.dcim.cables)


@update.register
def _(payload: CablePayload, **kwargs: Any) -> bool:
    return _update_object(payload, endpoint=netbox.dcim.cables)


def _create_object(payload: NetboxPayload, endpoint: Endpoint) -> bool:
    """
    Create an object in Netbox.

    Args:
        payload: values to create object
        endpoint: a Netbox Endpoint

    Returns:
         The id of the created object in Netbox, raises an exception otherwise.

    Raises:
        RequestError: the pynetbox exception that was raised.
    """
    try:
        object = endpoint.create(payload.dict())
    except RequestError as exc:
        logger.warning("Netbox create failed", payload=payload, exc=str(exc))
        raise ValueError(f"invalid NetboxPayload: {exc.message}") from exc
    else:
        return object.id


def _update_object(payload: NetboxPayload, endpoint: Endpoint) -> bool:
    """
    Create or update an object in Netbox.

    Args:
        payload: values to create or update object
        endpoint: a Netbox Endpoint

    Returns:
         True if the node was created or updated, False otherwise

    Raises:
        ValueError if object does not exist yet in Netbox.
    """
    if not (object := endpoint.get(payload.id)):
        raise ValueError(f"Netbox object with id {payload.id} on netbox {endpoint.name} endpoint not found")
    object.update(payload.dict())
    return object.save()
