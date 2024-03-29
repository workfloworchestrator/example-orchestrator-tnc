"""Workflow to initially provision a node."""
import ipaddress

import structlog
from orchestrator.config.assignee import Assignee
from orchestrator.forms import FormPage, ReadOnlyField
from orchestrator.forms.validators import Accept, Choice, LongText
from orchestrator.targets import Target
from orchestrator.types import FormGenerator, State, SubscriptionLifecycle, UUIDstr
from orchestrator.workflow import StepList, begin, inputstep, step
from orchestrator.workflows.steps import set_status, store_process_subscription

from products.product_types.node import NodeInactive, NodeProvisioning
from products.services.description import description
from products.services.netbox.netbox import build_payload
from services import netbox
from workflows.shared import CUSTOMER_UUID, create_workflow

logger = structlog.get_logger(__name__)


def initial_input_form_generator(product_name: str) -> FormGenerator:
    """Generates the Node Form to display to the user."""
    logger.debug("Generating initial input form")
    devices = netbox.get_devices(status="planned")
    choices = [device.name for device in devices]
    DeviceEnum = Choice("Planned devices", zip(choices, choices))  # type: ignore

    class CreateNodeForm(FormPage):
        """FormPage for Creating a node"""

        class Config:
            """Config class for Creating a node"""

            title = product_name

        select_device_choice: DeviceEnum  # type: ignore

    user_input = yield CreateNodeForm
    device_data = next(
        device for device in devices if user_input.select_device_choice == device.name
    )

    return {
        "device_id": device_data.id,
        "device_name": device_data.name,
        "device_status": device_data.status.value
    }


@step("Construct Node model")
def construct_node_model(
    product: UUIDstr,
    device_id: int,
    device_name: str,
    device_status: str,
) -> State:
    """Creates the node model in its initial state."""
    logger.debug("Constructing Node model for node", device_name=device_name)
    subscription = NodeInactive.from_product_id(
        product_id=product,
        customer_id=CUSTOMER_UUID,
        status=SubscriptionLifecycle.INITIAL,
    )

    subscription.node.node_id = device_id
    subscription.node.node_name = device_name
    subscription.node.node_status = device_status
    subscription.description = description(subscription)

    return {
        "subscription": subscription,
        "subscription_id": subscription.subscription_id,
    }


@step("Fetch Detailed IP information")
def fetch_ip_address_information(subscription: NodeInactive) -> State:
    """Grabs the IP address information for the node and puts it on the domain model."""
    logger.debug(
        "Fetching detailed IP information for node from netbox",
        node_name=subscription.node.node_name,
    )
    device = netbox.get_device(name=subscription.node.node_name)
    subscription.node.ipv4_loopback = ipaddress.IPv4Network(device.primary_ip4.address)
    subscription.node.ipv6_loopback = ipaddress.IPv6Network(device.primary_ip6.address)

    return {"subscription": subscription}


@inputstep("Provide Config to User", assignee=Assignee.SYSTEM)
def provide_config_to_user(subscription: NodeProvisioning) -> FormGenerator:
    """Generates a configuration payload that a user can paste into a router."""
    logger.debug("Creating node payload", node_name=subscription.node.node_name)
    router_config = f"""! Paste the following config into {subscription.node.node_name}:
! to complete configuring the device
!
enable
configure terminal
!
hostname {subscription.node.node_name}
!
interface loopback 0
!
ip address {subscription.node.ipv4_loopback}
ipv6 address {subscription.node.ipv6_loopback}
!
exit
!
end
copy running-config startup-config"""

    class ConfigResults(FormPage):
        """FormPage for showing a user the config needed for a node"""

        node_config: LongText = ReadOnlyField(router_config)
        confirm_config_put_on_routers: Accept = Accept("INCOMPLETE")

    form_data = yield ConfigResults
    user_input = form_data.dict()
    return user_input


@step("Set Node to active")
def set_node_to_active(subscription: NodeProvisioning) -> State:
    """Updates a node to be Active"""
    # Oops, we should have updated the subscription here!
    return {"subscription": subscription}


@step("Update Node in Netbox")
def update_node_in_netbox(subscription: NodeProvisioning) -> State:
    """Updates a node in Netbox"""
    netbox_payload = build_payload(subscription.node, subscription)
    return {
        "netbox_payload": netbox_payload.dict(),
        "netbox_updated": netbox.update(netbox_payload),
    }


@create_workflow(
    "Create Node",
    initial_input_form=initial_input_form_generator,
    status=SubscriptionLifecycle.ACTIVE,
)
def create_node() -> StepList:
    """Workflow step list"""
    return (
        begin
        >> construct_node_model
        >> store_process_subscription(Target.CREATE)
        >> fetch_ip_address_information
        >> set_status(SubscriptionLifecycle.PROVISIONING)
        >> provide_config_to_user
        >> set_node_to_active
        >> update_node_in_netbox
    )
