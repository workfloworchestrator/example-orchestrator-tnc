from orchestrator.workflow import StepList, begin
from orchestrator.workflows.utils import validate_workflow
from workflows.shared import is_active
from orchestrator.types import State, UUIDstr
from orchestrator.workflow import StepList, step
from products.product_types.node import Node
from utils import netbox


@step("Load relevant Node subscription information")
def load_node_subscription_info(subscription_id: UUIDstr) -> State:
    subscription = Node.from_subscription(subscription_id)
    nodes = netbox.dcim.get_devices()
    node = next(
        node for node in nodes if node.get("name") == subscription.node.node_name
    )
    return {
        "subscription": subscription,
        "node": node,
    }


@validate_workflow("Validate Node")
def validate_node() -> StepList:
    return begin >> load_node_subscription_info >> is_active()
