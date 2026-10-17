"""Public reusable presentation widgets."""

from apps.desktop.widgets.content_placeholder import ContentPlaceholderWidget
from apps.desktop.widgets.header import HeaderWidget
from apps.desktop.widgets.phase_two import (
    ActivityRail,
    NavigationRail,
    VirgoCoreWidget,
    WorkflowStepper,
)
from apps.desktop.widgets.status_bar import StatusBarWidget

__all__ = (
    "ActivityRail",
    "ContentPlaceholderWidget",
    "HeaderWidget",
    "NavigationRail",
    "StatusBarWidget",
    "VirgoCoreWidget",
    "WorkflowStepper",
)
