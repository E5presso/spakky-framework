"""Error classes for the spakky-agui plugin."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractAgUiError(AbstractSpakkyFrameworkError, ABC):
    """Base class for AG-UI adapter errors."""

    ...


class AgUiApprovalDecodeError(AbstractAgUiError):
    """Raised when a resume input claims an approval decision it cannot supply.

    The AG-UI resume carries an approval decision either as a tool-result
    message addressed to the deferred ``hitl_approval`` call or as a
    ``forwardedProps.approvalDecision`` object. This error is raised when that
    payload is present but malformed: the request id is missing, the decision
    string is absent, or the decision is not a member of ``ApprovalDecision``.
    """

    message = "AG-UI approval decision payload is missing or invalid"


class AgUiPendingApprovalError(AbstractAgUiError):
    """Raised when a paused-for-approval state carries malformed approval metadata.

    The event-driven path converts ``RunPausedEvent`` to a deferred-tool approval
    request. Legacy helpers can still rebuild that request from durable
    WAIT_FOR_APPROVAL state. This error is raised when either source lacks the
    approval id, prompt, or known decision list the adapter needs to render the
    pause without guessing.
    """

    message = "AG-UI pending approval state is missing or has invalid metadata"


class AgUiRunResolutionError(AbstractAgUiError):
    """Raised when a shared AG-UI request cannot resolve to a runnable core run.

    SSE, HTTP streaming, WebSocket, and stdio use the same inbound mapper. This
    error covers invalid shared request content as well as a driver factory that
    cannot produce a runner for the requested agent/run.
    """

    message = "AG-UI run request could not be resolved to a runnable agent run"


class AgUiEndpointConflictError(AbstractAgUiError):
    """Raised when multiple AG-UI agents claim the same transport path."""

    message = "AG-UI endpoint path is claimed by more than one exposed agent"
