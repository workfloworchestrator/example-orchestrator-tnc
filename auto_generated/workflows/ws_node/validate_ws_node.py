# Copyright 2019-2022 SURF.
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

import structlog

from orchestrator.types import State
from orchestrator.workflow import StepList, begin, step
from orchestrator.workflows.utils import validate_workflow

from surf.products.product_types.ws_node import node

from surf.workflows.shared.crm import load_organisation_info

logger = structlog.get_logger(__name__)


@step("Load initial state")
def load_initial_state_ws_node(subscription: node) -> State:
    return {
        "subscription": subscription,
    }



@validate_workflow("Validate Node")
def validate_ws_node() -> StepList:
    return (
        begin
        >> load_initial_state_ws_node
        >> load_organisation_info
    )