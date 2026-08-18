from typing import Callable
from dataclasses import dataclass


@dataclass
class Tool:
    name: str
    description: str
    parameters:dict[str, object]
    handler:Callable[[dict], dict]