from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import threading
import time


@dataclass
class DesktopState:
    application: Optional[str] = None
    window_title: Optional[str] = None

    last_action: Optional[str] = None
    last_target: Optional[str] = None
    last_query: Optional[str] = None

    active_contact: Optional[str] = None
    active_item: Optional[str] = None

    last_result: Optional[str] = None

    updated_at: float = field(default_factory=time.time)

    extra: Dict[str, Any] = field(default_factory=dict)


class DesktopStateStore:

    def __init__(self):
        self._lock = threading.RLock()
        self._state = DesktopState()

    def update(self, **kwargs):
        with self._lock:

            for key, value in kwargs.items():

                if hasattr(self._state, key):
                    setattr(
                        self._state,
                        key,
                        value
                    )

                else:
                    self._state.extra[key] = value

            self._state.updated_at = time.time()

            return self.snapshot()

    def get(self):
        return self.snapshot()

    def snapshot(self):

        with self._lock:

            return DesktopState(
                application=self._state.application,
                window_title=self._state.window_title,
                last_action=self._state.last_action,
                last_target=self._state.last_target,
                last_query=self._state.last_query,
                active_contact=self._state.active_contact,
                active_item=self._state.active_item,
                last_result=self._state.last_result,
                updated_at=self._state.updated_at,
                extra=dict(self._state.extra),
            )


STATE = DesktopStateStore()