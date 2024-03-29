from orchestrator.domain.base import SubscriptionModel
from orchestrator.types import SubscriptionLifecycle

from products.product_blocks.node import NodeBlock, NodeBlockInactive, NodeBlockProvisioning

# In here, we define the values expected for a product block at each phase of the of the Subscription Lifecycle
# All resource types used by a product block need to be explicitly called out here and assigned
# expected types


class NodeInactive(SubscriptionModel, is_base=True):
    node: NodeBlockInactive


class NodeProvisioning(NodeInactive, lifecycle=[SubscriptionLifecycle.PROVISIONING]):
    node: NodeBlockProvisioning


class Node(NodeProvisioning, lifecycle=[SubscriptionLifecycle.ACTIVE]):
    node: NodeBlock
