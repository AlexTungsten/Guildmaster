"""
event_bus.py — Central publish/subscribe message bus for Guildmaster.

All game systems communicate through events rather than direct references.
Subscribers register handlers for named event types; publishers fire events
without needing to know who is listening.  This keeps every module decoupled
and independently testable.
"""

from collections import defaultdict
from typing import Any, Callable


class EventBus:
    def __init__(self):
        # Maps event_type string -> list of handler callables
        self._subscribers: dict = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Register a callable to be invoked whenever event_type is published."""
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Remove a previously registered handler; no-op if not found."""
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event_type: str, data: Any = None) -> None:
        """
        Fire event_type to all registered handlers, passing data as the sole argument.

        A snapshot copy of the handler list is iterated so that a handler may
        safely subscribe/unsubscribe during dispatch without skipping entries.
        """
        # Copy to allow safe mutation during iteration
        handlers = list(self._subscribers.get(event_type, []))
        for handler in handlers:
            handler(data)
